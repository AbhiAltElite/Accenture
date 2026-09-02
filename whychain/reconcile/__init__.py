"""Do the two systems that report this number agree about it.

The brief asks for reconciliation across heterogeneous sources and, separately,
for the engine to abstain when evidence is **contradictory**. Those were being
answered by the same thing -- six tables at different grains, reconciled into
one series -- and they are not the same thing. Grain is a shape problem and the
engine solved it. Contradiction is a disagreement between two independent
postings of one quantity, and until a second system existed there was nothing
here capable of disagreeing.

There is one now, and this is what reads it.

**Three states, and the middle one is the useful one.** Two systems that post
the same trade under different policies are never identical, so equality is the
wrong test and any threshold that treats a 2% gap as a fault will be switched
off within a week. `agreed` is the ordinary day. `drift` is further apart than
policy explains, which lowers confidence and gets said out loud without stopping
anything. `contradicted` is far enough apart that the quantity itself is in
question.

**A contradiction stops the diagnosis rather than annotating it.** This is the
whole reason the stage earns its place. A movement the two systems disagree
about is not a movement with lower confidence -- it is a movement that may not
have happened, and every stage downstream will do its job correctly on it and
arrive at a confident, well-evidenced, completely false explanation. Detection
flags it because the series really does fall. Ranking finds the slice, because
that slice really is missing. The causal tests confirm the fall is isolated,
because it is. Nothing downstream can catch this, and nothing downstream should
have to: the check belongs before the explanation, not after it.

**It is scoped to the window being explained, not to the history.** A feed that
broke last March is not a reason to refuse a question about August, and a
reconciliation stage that reports every historical breach is one nobody reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import pandas as pd

from whychain.contracts import KPIContract
from whychain.evidence import Evidence, EvidenceKind, MethodClass, Provenance, Unit


class Agreement(StrEnum):
    """What the second system says about the first."""

    AGREED = "agreed"
    DRIFT = "drift"
    CONTRADICTED = "contradicted"
    # No second system is declared for this metric. Distinct from `agreed`,
    # loudly: "nobody checked" and "two systems checked and concur" are
    # different states and only one of them is reassuring.
    NOT_RECONCILED = "not_reconciled"


@dataclass(frozen=True)
class DayGap:
    """One day on which the two systems were compared."""

    day: date
    primary: float
    secondary: float

    @property
    def residual(self) -> float:
        """Signed, as a share of the second system's figure."""
        if not self.secondary:
            return 0.0
        return (self.primary - self.secondary) / self.secondary

    def as_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "primary": round(self.primary, 2),
            "secondary": round(self.secondary, 2),
            "residual": round(self.residual, 4),
        }


@dataclass(frozen=True)
class Reconciliation:
    """The verdict, and everything it rests on."""

    state: Agreement
    source: str | None
    tolerance_pct: float
    days: tuple[DayGap, ...]
    reason: str
    # The days that breached, worst first. The evidence a reader argues with.
    breaches: tuple[DayGap, ...] = ()

    @property
    def blocks_diagnosis(self) -> bool:
        return self.state is Agreement.CONTRADICTED

    @property
    def worst_residual(self) -> float:
        return max((abs(d.residual) for d in self.days), default=0.0)

    def as_dict(self) -> dict:
        return {
            "state": self.state.value,
            "source": self.source,
            "tolerance_pct": self.tolerance_pct,
            "reason": self.reason,
            "days_compared": len(self.days),
            "worst_residual": round(self.worst_residual, 4),
            "breaches": [d.as_dict() for d in self.breaches[:20]],
            "blocks_diagnosis": self.blocks_diagnosis,
        }


def reconcile(
    contract: KPIContract,
    primary: pd.DataFrame,
    secondary: pd.DataFrame | None,
    *,
    window: tuple[date, date],
) -> Reconciliation:
    """Compare the two systems over the window being explained.

    `primary` is the KPI's own series, already at day grain with a `d` and a
    `value`. `secondary` is the declared source, read raw. Both are the caller's
    job to scope to the same region, because the entitlement that decides which
    regions a reader may see has already been applied to one of them.
    """
    spec = contract.reconciliation
    if not spec.declared or secondary is None or secondary.empty:
        return Reconciliation(
            state=Agreement.NOT_RECONCILED,
            source=spec.source,
            tolerance_pct=spec.tolerance_pct,
            days=(),
            reason=(
                f"No second system is declared for {contract.kpi_id}, so nothing "
                f"independent confirms this movement. That is not the same as "
                f"two systems agreeing about it."
                if not spec.declared else
                f"{spec.source} carries no rows for this window, so the "
                f"comparison could not be made."
            ),
        )

    lo, hi = window
    left = primary.copy()
    left["_d"] = pd.to_datetime(left["d"]).dt.date
    left = left[(left["_d"] >= lo) & (left["_d"] <= hi)]

    right = secondary.copy()
    right["_d"] = pd.to_datetime(right[spec.date_column]).dt.date
    right = right[(right["_d"] >= lo) & (right["_d"] <= hi)]

    merged = (
        left.groupby("_d", as_index=False)["value"].sum()
        .merge(
            right.groupby("_d", as_index=False)[spec.compare_column].sum(),
            on="_d", how="inner",
        )
    )
    days = tuple(
        DayGap(day=row["_d"], primary=float(row["value"]),
               secondary=float(row[spec.compare_column]))
        for _, row in merged.iterrows()
    )
    if not days:
        return Reconciliation(
            state=Agreement.NOT_RECONCILED, source=spec.source,
            tolerance_pct=spec.tolerance_pct, days=(),
            reason=(
                f"{spec.source} and {contract.kpi_id} share no days in this "
                f"window, so there was nothing to compare."
            ),
        )

    hard = spec.tolerance_pct * spec.contradiction_multiple
    breaches = tuple(sorted(
        (d for d in days if abs(d.residual) > spec.tolerance_pct),
        key=lambda d: abs(d.residual), reverse=True,
    ))
    worst = max(abs(d.residual) for d in days)

    if worst > hard:
        bad = [d for d in days if abs(d.residual) > hard]
        state, reason = Agreement.CONTRADICTED, (
            f"{contract.kpi_id} and {spec.source} disagree about this window by "
            f"up to {worst:.1%}, against a {spec.tolerance_pct:.0%} tolerance. "
            f"{len(bad)} of {len(days)} day(s) are past the point where posting "
            f"policy explains the gap, so the movement itself is in question and "
            f"no cause is proposed for it. The first thing to check is whether "
            f"the extract is complete, not what the business did."
        )
    elif breaches:
        state, reason = Agreement.DRIFT, (
            f"{contract.kpi_id} and {spec.source} are further apart than usual on "
            f"{len(breaches)} of {len(days)} day(s), by up to {worst:.1%} against "
            f"a {spec.tolerance_pct:.0%} tolerance. Not enough to doubt the "
            f"movement, enough to lower confidence in the size of it."
        )
    else:
        state, reason = Agreement.AGREED, (
            f"{spec.source} independently posts the same movement to within "
            f"{worst:.1%}, inside the {spec.tolerance_pct:.0%} the two systems' "
            f"posting policies account for."
        )

    return Reconciliation(
        state=state, source=spec.source, tolerance_pct=spec.tolerance_pct,
        days=days, reason=reason, breaches=breaches,
    )


def as_evidence(result: Reconciliation, contract: KPIContract, run_id: str) -> Evidence:
    """The verdict as a citable record, so the narrative can reference it."""
    return Evidence(
        id=f"{run_id}-reconciliation",
        kind=EvidenceKind.RECONCILIATION,
        claim=result.reason,
        value=round(result.worst_residual, 4) if result.days else None,
        unit=Unit.RATIO if result.days else Unit.NONE,
        method="cross_source_reconciliation",
        method_class=MethodClass.DETERMINISTIC,
        provenance=Provenance(
            source_id=result.source or "none",
            query=(
                f"compare {contract.kpi_id} against "
                f"{contract.reconciliation.source}."
                f"{contract.reconciliation.compare_column} by business date"
            ),
            row_count=len(result.days),
            row_ids=[d.day.isoformat() for d in result.breaches[:20]],
        ),
    )


__all__ = [
    "Agreement",
    "DayGap",
    "Reconciliation",
    "as_evidence",
    "reconcile",
]
