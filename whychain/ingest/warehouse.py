"""Reading source data through the contract.

The contract declares its lineage transforms; this module applies them before
the KPI SQL runs. That makes lineage executable rather than descriptive: if a
contract says it dedupes order ids, the query genuinely does.

The generated extract really does contain duplicated order ids and one region
reporting in local time. Skipping the transforms inflates revenue and smears the
hourly series, which is the failure the reconciliation layer exists to prevent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from whychain.contracts import KPIContract
from whychain.evidence import Freshness

DEFAULT_WAREHOUSE = Path("data/warehouse/whychain.duckdb")

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
            raise IngestError(f"no warehouse at {self.path} — run `make gen` first")
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

        if entitled_regions is not None:
            if not entitled_regions:
                raise IngestError("an empty entitlement grants access to nothing")
            allowed = ", ".join(f"'{r}'" for r in entitled_regions)
            sql = f"SELECT * FROM ({sql}) WHERE region IN ({allowed})"

        try:
            return self._con.execute(sql).df()
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
        sql = f"SELECT * FROM {name}" + (f" LIMIT {limit}" if limit else "")
        return self._con.execute(sql).df()
