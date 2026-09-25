"""The query behind a figure, written out so someone else can run it.

A finance reader who is asked to sign a number wants to see where it came from,
and an auditor wants to run it again in their own tool. This module writes the
query that produces a finding's rows as one standalone statement: the contract's
declared lineage as CTEs, the contract's own SQL over them, the access policy's
row filter, the finding's scope and window, and the roll-up to the grain the
contract declares.

It is not a second implementation to trust. The API runs this statement against
the warehouse and compares its result, row for row, with the rows the engine
computed through its own path. The page says whether they matched. A rewritten
query that drifted from what the engine does would be caught there rather than
signed.

Every value is a bound parameter. Only names the contract itself declares (its
lineage, its dimensions, its numerator and denominator) are written into the
text, never anything a request supplied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from whychain.contracts import KPIContract

from .warehouse import TRANSFORMS, IngestError, _row_filter_clause

_TIME_EXPR = re.compile(r"date_trunc\(\s*'(?:hour|day)'\s*,\s*(\w+)\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class Reproduction:
    """One runnable statement and the values bound into it."""

    sql: str
    params: list[object] = field(default_factory=list)
    lineage: list[tuple[str, str]] = field(default_factory=list)

    def literal(self) -> str:
        """The statement with its values written in, for copying into an editor.

        For display only. What the API executes is `sql` with `params` bound.
        """
        out, values = [], iter(self.params)
        for part in re.split(r"(\?)", self.sql):
            out.append(_quote(next(values)) if part == "?" else part)
        return "".join(out)


def _quote(value: object) -> str:
    if isinstance(value, datetime):
        return f"TIMESTAMP '{value:%Y-%m-%d %H:%M:%S}'"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def base_table(contract: KPIContract) -> str:
    return contract.lineage.upstream[0].split(".")[0]


def lineage_ctes(contract: KPIContract) -> tuple[list[tuple[str, str]], str]:
    """The declared transforms as named steps, and the relation they end in."""
    relation = base_table(contract)
    steps: list[tuple[str, str]] = []
    for name in contract.lineage.transforms:
        if name not in TRANSFORMS:
            raise IngestError(f"{contract.kpi_id} declares transform {name!r}, which is not implemented.")
        steps.append((name, TRANSFORMS[name].format(table=relation)))
        relation = name
    return steps, relation


def metric_sql(contract: KPIContract) -> str:
    """The contract's SQL reading from its lineage, the same rewrite `kpi_series` makes."""
    _, relation = lineage_ctes(contract)
    base = base_table(contract)
    sql = contract.calculation.canonical_sql.strip().rstrip(";")
    return sql if relation == base else sql.replace(f"FROM {base}", f"FROM {relation}")


def source_time_column(contract: KPIContract) -> str | None:
    """The raw timestamp the contract buckets by, when its SQL names one plainly."""
    found = _TIME_EXPR.search(contract.calculation.canonical_sql)
    return found.group(1) if found else None


def reproduce(
    contract: KPIContract,
    time_col: str,
    *,
    lo: date,
    hi: date,
    scope: tuple[str, ...] | None,
    region: str | None,
    slice_: dict[str, str],
) -> Reproduction:
    """One statement returning the rolled-up rows for a scope and window."""
    steps, _ = lineage_ctes(contract)
    ctes = [f"{name} AS (\n  {body}\n)" for name, body in steps]
    ctes.append(f"metric AS (\n  {metric_sql(contract)}\n)")

    aggregation = contract.grain.aggregation.value
    if aggregation == "ratio_of_sums":
        num, den = contract.grain.numerator, contract.grain.denominator
        select = (f"SUM({num}) / NULLIF(SUM({den}), 0) AS value, SUM({den}) AS n")
    elif aggregation == "mean":
        select = "AVG(value) AS value"
    else:
        select = "SUM(value) AS value"

    where, params = [], []
    if scope is not None:
        if not scope:
            raise IngestError("an empty entitlement grants access to nothing")
        where.append(_row_filter_clause(contract, ", ".join("?" for _ in scope))
                     + "  -- the contract's row filter, bound to your entitlement")
        params.extend(scope)
    if region:
        where.append("region = ?")
        params.append(region)
    for dim, value in slice_.items():
        if dim not in contract.grain.dims:
            raise IngestError(f"{dim} is not a dimension of {contract.kpi_id}")
        where.append(f"{dim} = ?")
        params.append(value)
    where.append(f"{time_col} >= ? AND {time_col} < ?")
    params.extend([datetime.combine(lo, time.min), datetime.combine(hi + timedelta(days=1), time.min)])

    sql = (
        "WITH " + ",\n".join(ctes) + "\n"
        f"SELECT {time_col if time_col == 'd' else time_col + ' AS d'}, {select}\n"
        "FROM metric\n"
        "WHERE " + "\n  AND ".join(where) + "\n"
        "GROUP BY 1\nORDER BY 1"
    )
    return Reproduction(sql=sql, params=params, lineage=steps)
