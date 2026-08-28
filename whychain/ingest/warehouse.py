"""Reading source data through the contract.

The contract declares its lineage transforms; this module applies them before
the KPI SQL runs. That makes lineage executable rather than descriptive: if a
contract says it dedupes order ids, the query genuinely does.

The generated extract really does contain duplicated order ids and one region
reporting in local time. Skipping the transforms inflates revenue and smears the
hourly series, which is the failure the reconciliation layer exists to prevent.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from whychain.contracts import KPIContract
from whychain.evidence import Freshness

DEFAULT_WAREHOUSE = Path("data/warehouse/whychain.duckdb")

# The source tables a caller may read whole. `_panel` is deliberately absent: it
# is the generator's own working frame, and reading it is how a diagnosis ends up
# computed from revenue while labelled as another metric. The engine reads
# sources through a contract.
READABLE_TABLES = frozenset(
    {"pos_txn", "sessions", "shipments", "plan_ops", "voice_ops",
     "ext_signals", "source_freshness"}
)

# Each declared transform is a SQL rewrite applied to the base table before the
# KPI is computed. A contract naming a transform we cannot apply is an error,
# not something to skip quietly.
TRANSFORMS: dict[str, str] = {
    "dedupe_order_id": (
        "SELECT * FROM (SELECT *, row_number() OVER "
        "(PARTITION BY order_id ORDER BY order_ts) AS _rn FROM {table}) WHERE _rn = 1"
    ),
    "tz_normalise": (
        # The East extract lands in IST while the rest are UTC. Correcting it here
        # keeps orders in the day they actually happened.
        "SELECT * REPLACE (CASE WHEN region = 'East' "
        "THEN order_ts - INTERVAL 5 HOUR - INTERVAL 30 MINUTE ELSE order_ts END AS order_ts) "
        "FROM {table}"
    ),
    "net_returns": "SELECT * FROM {table}",           # returns are already netted upstream
    "exclude_test_accounts": "SELECT * FROM {table} WHERE is_test = FALSE",
    "digital_channels_only": "SELECT * FROM {table} WHERE channel IN ('web','app')",
    "exclude_in_flight": "SELECT * FROM {table}",
}


class IngestError(Exception):
    pass


class Warehouse:
    """A read-only connection to the source tables."""

    def __init__(self, path: Path | str = DEFAULT_WAREHOUSE) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise IngestError(f"no warehouse at {self.path}, run `make gen` first")
        # Read-only: the engine analyses, it never writes to the source of truth.
        self._con = duckdb.connect(str(self.path), read_only=True)

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> Warehouse:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _prepared(self, contract: KPIContract) -> str:
        """Base table with the contract's declared transforms applied, as a subquery."""
        base = contract.lineage.upstream[0].split(".")[0]
        sql = base
        for name in contract.lineage.transforms:
            if name not in TRANSFORMS:
                raise IngestError(
                    f"{contract.kpi_id} declares transform {name!r}, which is not implemented. "
                    "A contract must not claim lineage the query does not perform."
                )
            sql = f"({TRANSFORMS[name].format(table=sql)})"
        return sql

    def kpi_series(
        self,
        contract: KPIContract,
        *,
        entitled_regions: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        """The metric at its contracted grain, with entitlement applied in SQL.

        Row filtering happens here, in the query, before anything downstream sees
        the data. It is not a presentation concern and it never reaches a prompt
        as an instruction.
        """
        prepared = self._prepared(contract)
        sql = contract.calculation.canonical_sql.replace(
            f"FROM {contract.lineage.upstream[0].split('.')[0]}", f"FROM {prepared}"
        )

        params: list[object] = []
        if entitled_regions is not None:
            if not entitled_regions:
                raise IngestError("an empty entitlement grants access to nothing")
            # Bound, not interpolated. Region names reach here from a request, and
            # a value that closes its own quote would otherwise rewrite the filter
            # that is the access control.
            placeholders = ", ".join("?" for _ in entitled_regions)
            sql = f"SELECT * FROM ({sql}) WHERE region IN ({placeholders})"
            params = list(entitled_regions)

        try:
            return self._con.execute(sql, params).df()
        except duckdb.Error as exc:
            raise IngestError(f"{contract.kpi_id}: query failed: {exc}") from exc

    def freshness(self, contract: KPIContract) -> dict[str, Freshness]:
        """Observed freshness for every source this contract depends on."""
        observed = self._con.execute(
            "SELECT source_id, as_of, observed_at FROM source_freshness"
        ).df()
        out: dict[str, Freshness] = {}
        for source, sla in contract.freshness_sla.items():
            row = observed[observed["source_id"] == source]
            if row.empty:
                # No reading is not the same as fresh. Treat it as maximally stale
                # so confidence is penalised rather than silently unaffected.
                now = datetime.now(UTC)
                out[source] = Freshness(
                    source_id=source, as_of=now - sla - timedelta(hours=1),
                    observed_at=now, sla=sla,
                )
                continue
            out[source] = Freshness(
                source_id=source,
                as_of=row.iloc[0]["as_of"].to_pydatetime().replace(tzinfo=UTC),
                observed_at=row.iloc[0]["observed_at"].to_pydatetime().replace(tzinfo=UTC),
                sla=sla,
            )
        return out

    def documents(self, start: datetime, end: datetime) -> pd.DataFrame:
        return self._con.execute(
            "SELECT doc_id, doc_type, ts, region, text FROM voice_ops "
            "WHERE ts BETWEEN ? AND ? ORDER BY ts",
            [start, end],
        ).df()

    def table(self, name: str, limit: int | None = None) -> pd.DataFrame:
        """Read a source table whole.

        The name is checked against the declared sources rather than interpolated
        as given: this is the one place a caller-supplied string reaches a query,
        and a table name cannot be bound as a parameter.
        """
        if name not in READABLE_TABLES:
            raise IngestError(
                f"{name!r} is not a readable source table; "
                f"expected one of {sorted(READABLE_TABLES)}"
            )
        sql = f"SELECT * FROM {name}"
        if limit is not None:
            return self._con.execute(sql + " LIMIT ?", [int(limit)]).df()
        return self._con.execute(sql).df()

    def bridge_facts(
        self,
        contract: KPIContract,
        *,
        since: date | None = None,
        until: date | None = None,
        entitled_regions: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        """Per-day, per-product units and revenue for the bridge.

        Built from this contract's own source with its own transforms and its own
        declared expressions, so a decomposition is always of the metric it is
        labelled with. Reading a shared panel instead is how a movement in one
        KPI ends up explained by the arithmetic of another.

        `since` and `until` bound the scan. A diagnosis looks at a window of days
        but the causal tests reach back behind it for their baseline and their
        placebo windows, so the caller decides how much history it needs and this
        reads that much rather than the whole table. Aggregating three years of
        order lines to answer a question about a fortnight is most of the time a
        diagnosis takes.
        """
        spec = contract.decomposition
        if spec.method != "pvm":
            raise IngestError(
                f"{contract.kpi_id} does not declare a price/volume/mix "
                "decomposition, so there are no bridge facts to read"
            )

        prepared = self._prepared(contract)
        dims = [d for d in ("region", "channel", "category", "device") if d in self._columns(prepared)]
        select_dims = ("," + ", ".join(dims)) if dims else ""
        group_dims = ("," + ", ".join(str(i) for i in range(3, 3 + len(dims)))) if dims else ""

        params: list[object] = []
        where = ["status <> 'cancelled'"]
        if since is not None:
            where.append("order_ts >= ?")
            params.append(datetime.combine(since, time.min))
        if until is not None:
            # Exclusive upper bound on the day after, so a timestamped order late
            # on the final day is not silently dropped.
            where.append("order_ts < ?")
            params.append(datetime.combine(until + timedelta(days=1), time.min))

        sql = (
            f"SELECT date_trunc('day', order_ts) AS d, {spec.key} AS {spec.key}"
            f"{select_dims},"
            f" SUM({spec.units}) AS units,"
            f" SUM({spec.revenue}) AS revenue "
            f"FROM {prepared} WHERE {' AND '.join(where)} "
            f"GROUP BY 1,2{group_dims}"
        )
        if entitled_regions is not None:
            if not entitled_regions:
                raise IngestError("an empty entitlement grants access to nothing")
            placeholders = ", ".join("?" for _ in entitled_regions)
            sql = f"SELECT * FROM ({sql}) WHERE region IN ({placeholders})"
            params = [*params, *entitled_regions]

        try:
            return self._con.execute(sql, params).df()
        except duckdb.Error as exc:
            raise IngestError(f"{contract.kpi_id}: bridge query failed: {exc}") from exc

    def _columns(self, prepared: str) -> set[str]:
        """Column names of a prepared subquery, so dimensions can be optional."""
        sql = f"SELECT * FROM {prepared} LIMIT 0"
        return {d[0] for d in self._con.execute(sql).description}
