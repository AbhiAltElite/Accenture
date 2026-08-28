"""Where the movement happened.

The bridge says what kind of change occurred. Contribution says which part of the
business it occurred in. Both are arithmetic: a slice's contribution is simply
its own movement, and the slices of any one dimension sum to the total.

Reported as signed rupees and as a share, because a slice can move against the
overall direction and hiding that would misrepresent the picture. A region that
grew while revenue fell is worth knowing about.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from whychain.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceStore,
    MethodClass,
    Provenance,
    Unit,
)

RECONCILE_TOLERANCE = 0.10


@dataclass(frozen=True)
class SliceContribution:
    dimension: str
    value: str
    base: float
    current: float

    @property
    def delta(self) -> float:
        return self.current - self.base

    @property
    def pct_change(self) -> float | None:
        return (self.current / self.base - 1.0) if self.base else None


@dataclass(frozen=True)
class Contribution:
    dimension: str
    total_change: float
    slices: tuple[SliceContribution, ...]

    def share_of(self, slice_: SliceContribution) -> float:
        """Signed share of the total movement.

        Undefined when the total is zero, which happens when offsetting slices
        cancel out. Returning zero there would imply nothing moved.
        """
        return slice_.delta / self.total_change if self.total_change else 0.0

    def ranked(self) -> tuple[SliceContribution, ...]:
        """Largest contributor to the movement first, in its direction."""
        sign = -1.0 if self.total_change < 0 else 1.0
        return tuple(sorted(self.slices, key=lambda s: sign * s.delta, reverse=True))

    def concentration(self, top_n: int = 1) -> float:
        """Share of the movement carried by the largest contributors.

        High concentration means the problem is localised and worth drilling
        into. Low concentration means it is broad, and a slice-level explanation
        will not be the answer.
        """
        if not self.total_change:
            return 0.0
        top = self.ranked()[:top_n]
        return sum(s.delta for s in top) / self.total_change

    def assert_reconciles(self) -> None:
        summed = sum(s.delta for s in self.slices)
        if abs(summed - self.total_change) > RECONCILE_TOLERANCE:
            raise ValueError(
                f"{self.dimension}: slices sum to {summed:,.2f} but the total moved "
                f"{self.total_change:,.2f}"
            )


def contribution_by(
    base: pd.DataFrame, current: pd.DataFrame, dimension: str, measure: str = "revenue"
) -> Contribution:
    """Movement attributed across the values of one dimension."""
    if dimension not in base.columns:
        raise KeyError(f"{dimension!r} is not a dimension of this data")

    b = base.groupby(dimension)[measure].sum()
    c = current.groupby(dimension)[measure].sum()
    merged = pd.concat([b.rename("base"), c.rename("current")], axis=1).fillna(0.0)

    slices = tuple(
        SliceContribution(dimension, str(value), float(row["base"]), float(row["current"]))
        for value, row in merged.iterrows()
    )
    result = Contribution(
        dimension=dimension,
        total_change=float(merged["current"].sum() - merged["base"].sum()),
        slices=slices,
    )
    result.assert_reconciles()
    return result


def record_contributions(
    contributions: list[Contribution],
    store: EvidenceStore,
    source_id: str,
    query: str,
    top_n: int = 3,
) -> list[Evidence]:
    """Record the leading contributors on each dimension.

    Only the leaders are written as evidence. A row per slice would bury the
    finding under arithmetic that is available on demand anyway.
    """
    out: list[Evidence] = []
    for contribution in contributions:
        for slice_ in contribution.ranked()[:top_n]:
            if slice_.delta == 0:
                continue
            share = contribution.share_of(slice_)
            out.append(
                store.add(
                    Evidence(
                        id=store.next_id(),
                        kind=EvidenceKind.CONTRIBUTION,
                        claim=(
                            f"{contribution.dimension} {slice_.value} accounts for "
                            f"{abs(share):.0%} of the movement, "
                            f"{'down' if slice_.delta < 0 else 'up'} "
                            f"{abs(slice_.delta):,.0f}."
                        ),
                        value=float(slice_.delta),
                        unit=Unit.INR,
                        method="dimensional_contribution",
                        method_class=MethodClass.DETERMINISTIC,
                        provenance=Provenance(source_id=source_id, query=query),
                        run_id=store.run_id,
                        extra={
                            "dimension": contribution.dimension,
                            "slice": slice_.value,
                            "share_of_movement": share,
                            "base": slice_.base,
                            "current": slice_.current,
                            "pct_change": slice_.pct_change,
                        },
                    )
                )
            )
    return out
