"""Two tracks, kept apart on purpose.

Ranking is where most explanation tools quietly stop being honest. They fit a
model against the metric, sort the coefficients, and present the top of that
list as the reason. The list is a correlation ranking wearing a causal label,
and nothing in the output tells the reader which it is.

This stage produces both rankings and refuses to merge them.

**Track A is exact.** Contributions come from the price/volume/mix bridge and
the dimensional split, which are identities: the parts add back to the movement
with no residual. A slice at the top of track A is not a hypothesis about what
happened, it is arithmetic about what happened. It carries `ClaimState.VERIFIED`
without a causal test because there is nothing to test; no counterfactual is
being claimed, only accounting.

**Track B is associational, and says so in every row it emits.** A ridge fit
over daily driver series tells you which drivers moved with the metric. That is
genuinely useful for generating candidates nobody thought to look at, and it is
worthless as an answer, because the strongest coefficient in a small sample is
routinely a decoy that happens to share a window. Track B rows are
`ClaimState.HYPOTHESIS`, are labelled `CORRELATIONAL` in the evidence record,
and are barred from becoming a stated cause: they are inputs to `verify`, not
outputs of it.

**The two are never summed and never interleaved.** A combined score would let
a strong correlation top a weak identity, which is precisely the substitution
this project exists to prevent. The UI renders them as separate columns for the
same reason.

One consequence worth stating: a candidate that `verify` has already rejected
cannot re-enter through track B. Once rejected, always rejected within a run
(BUGS.md T-12), and `rank_associational` takes the rejected set so it can drop
them rather than leaving that to the caller's discipline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from whychain.decompose.contribution import Contribution
from whychain.evidence import (
    ClaimState,
    Evidence,
    EvidenceKind,
    MethodClass,
    Provenance,
    Unit,
)

# Ridge rather than OLS: driver series in a short window are collinear, and OLS
# answers that with enormous opposite-signed coefficients that mean nothing.
RIDGE_ALPHA = 1.0

# An absolute standardised coefficient below this is not worth a row. It exists
# to keep the list readable, not to make a claim; everything here is a
# hypothesis regardless of size.
MIN_ABS_COEFFICIENT = 0.02

# Fewer observations than this and the fit is not reported at all. A ridge over
# eight days produces a confident-looking ranking of noise.
MIN_OBSERVATIONS = 14


class Track(StrEnum):
    EXACT = "exact"
    ASSOCIATIONAL = "associational"


@dataclass(frozen=True)
class RankedCause:
    """One row of either ranking.

    `track` is not decoration. It determines what a reader is entitled to
    conclude from the row, and it is carried into the evidence record and the
    API response unchanged.
    """

    rank: int
    track: Track
    label: str
    dimension: str
    value: float
    unit: Unit
    share: float | None
    state: ClaimState
    method: str
    basis: str

    @property
    def is_causal_claim(self) -> bool:
        """Whether this row may be stated as a reason. Track B never may."""
        return self.track is Track.EXACT

    def as_dict(self) -> dict:
        return {
            "rank": self.rank,
            "track": self.track.value,
            "label": self.label,
            "dimension": self.dimension,
            "value": round(self.value, 4),
            "unit": self.unit.value,
            "share": round(self.share, 4) if self.share is not None else None,
            "state": self.state.value,
            "method": self.method,
            "basis": self.basis,
            "is_causal_claim": self.is_causal_claim,
        }


@dataclass(frozen=True)
class Ranking:
    """Both tracks, side by side and never merged."""

    exact: tuple[RankedCause, ...]
    associational: tuple[RankedCause, ...]
    total_change: float
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "exact": [r.as_dict() for r in self.exact],
            "associational": [r.as_dict() for r in self.associational],
            "total_change": round(self.total_change, 2),
            "notes": list(self.notes),
            "disclaimer": (
                "The associational track is a candidate generator. No row in it "
                "is a stated cause until a causal test promotes it."
            ),
        }


def rank_exact(
    contributions: list[Contribution], *, top_n: int = 8
) -> tuple[RankedCause, ...]:
    """Track A, straight off the identity.

    The share is signed against the total movement, so a slice that moved the
    other way reads as a negative share rather than as a small positive one.
    """
    rows: list[RankedCause] = []
    for contribution in contributions:
        contribution.assert_reconciles()
        for slice_ in contribution.ranked()[:top_n]:
            rows.append(
                RankedCause(
                    rank=0,
                    track=Track.EXACT,
                    label=f"{contribution.dimension} · {str(slice_.value).replace('_', ' ')}",
                    dimension=contribution.dimension,
                    value=slice_.delta,
                    unit=Unit.INR,
                    share=contribution.share_of(slice_),
                    state=ClaimState.VERIFIED,
                    method="dimensional_contribution",
                    basis=(
                        "exact: this slice's movement is part of the identity "
                        "and the slices sum to the total with no residual"
                    ),
                )
            )

    # Largest mover in the direction the total moved, first. For a fall that is
    # the most negative slice; for a rise, the most positive. Sorting by the raw
    # value would put the slices that moved *against* the total at the top of a
    # list of reasons it fell, which is the opposite of what the column means.
    sign = -1.0 if (contributions and contributions[0].total_change < 0) else 1.0
    rows.sort(key=lambda r: sign * r.value, reverse=True)
    return tuple(
        RankedCause(**{**r.__dict__, "rank": i + 1}) for i, r in enumerate(rows[:top_n])
    )


def rank_associational(
    metric: pd.Series,
    drivers: pd.DataFrame,
    *,
    rejected: frozenset[str] = frozenset(),
    top_n: int = 6,
    alpha: float = RIDGE_ALPHA,
) -> tuple[tuple[RankedCause, ...], tuple[str, ...]]:
    """Track B: a standardised ridge fit over the driver series.

    Standardised because the raw coefficients are in incomparable units, a
    rupee of price and a unit of stock cover cannot be ranked against each other
    without it. The returned value is therefore a z-scale sensitivity, unitless,
    and it is reported as a ratio rather than dressed up as rupees.

    Returns the rows and any notes explaining what was dropped, because a driver
    silently missing from a ranking is indistinguishable from a driver that did
    not matter.
    """
    from sklearn.linear_model import Ridge

    notes: list[str] = []
    frame = drivers.copy()
    frame = frame.loc[:, [c for c in frame.columns if c not in rejected]]
    dropped = sorted(set(drivers.columns) & rejected)
    if dropped:
        notes.append(
            f"excluded from the fit because a causal test already rejected them: "
            f"{', '.join(dropped)}"
        )

    joined = pd.concat([metric.rename("_y"), frame], axis=1).dropna()
    if len(joined) < MIN_OBSERVATIONS:
        notes.append(
            f"not fitted: {len(joined)} usable observations, under the "
            f"{MIN_OBSERVATIONS} this ranking requires to mean anything"
        )
        return (), tuple(notes)

    y = joined["_y"].to_numpy(dtype=float)
    x = joined.drop(columns="_y")
    constant = [c for c in x.columns if float(x[c].std()) == 0.0]
    if constant:
        notes.append(f"dropped, no variation in the window: {', '.join(constant)}")
        x = x.drop(columns=constant)
    if x.empty or float(np.std(y)) == 0.0:
        notes.append("not fitted: nothing in the window varies")
        return (), tuple(notes)

    xz = (x - x.mean()) / x.std()
    yz = (y - y.mean()) / np.std(y)
    fit = Ridge(alpha=alpha).fit(xz.to_numpy(dtype=float), yz)

    rows = [
        RankedCause(
            rank=0,
            track=Track.ASSOCIATIONAL,
            label=name.replace("_", " "),
            dimension="driver",
            value=float(coefficient),
            unit=Unit.RATIO,
            share=None,
            state=ClaimState.HYPOTHESIS,
            method="ridge",
            basis=(
                "correlational: a standardised ridge coefficient over "
                f"{len(joined)} days. It says this driver moved with the metric, "
                "not that it moved the metric"
            ),
        )
        for name, coefficient in zip(x.columns, fit.coef_, strict=True)
        if abs(float(coefficient)) >= MIN_ABS_COEFFICIENT
    ]
    rows.sort(key=lambda r: abs(r.value), reverse=True)
    ranked = tuple(
        RankedCause(**{**r.__dict__, "rank": i + 1}) for i, r in enumerate(rows[:top_n])
    )
    return ranked, tuple(notes)


def rank(
    contributions: list[Contribution],
    metric: pd.Series | None = None,
    drivers: pd.DataFrame | None = None,
    *,
    rejected: frozenset[str] = frozenset(),
    top_n: int = 8,
) -> Ranking:
    """Both tracks. Track B is skipped rather than faked when there is no data."""
    exact = rank_exact(contributions, top_n=top_n)
    total = contributions[0].total_change if contributions else 0.0

    if metric is None or drivers is None or drivers.empty:
        return Ranking(
            exact=exact,
            associational=(),
            total_change=total,
            notes=("associational track not run: no driver series was supplied",),
        )

    associational, notes = rank_associational(
        metric, drivers, rejected=rejected, top_n=max(top_n // 2, 3)
    )
    return Ranking(
        exact=exact, associational=associational, total_change=total, notes=notes
    )


def as_evidence(ranking: Ranking, run_id: str, source_id: str, query: str) -> list[Evidence]:
    """Both tracks as records, each carrying the state its track allows.

    The evidence kind differs by track, CONTRIBUTION against ASSOCIATION, so
    a downstream consumer that only wants stateable facts can filter on kind
    and cannot pick up a correlation by accident.
    """
    out: list[Evidence] = []
    for row in ranking.exact:
        out.append(
            Evidence(
                id=f"{run_id}-rank-a-{row.rank}",
                kind=EvidenceKind.CONTRIBUTION,
                claim=f"{row.label} moved {row.value:,.0f} rupees",
                value=row.value,
                unit=row.unit,
                method=row.method,
                method_class=MethodClass.DETERMINISTIC,
                state=row.state,
                provenance=Provenance(source_id=source_id, query=query),
                run_id=run_id,
                extra={"track": row.track.value, "share": row.share},
            )
        )
    for row in ranking.associational:
        out.append(
            Evidence(
                id=f"{run_id}-rank-b-{row.rank}",
                kind=EvidenceKind.ASSOCIATION,
                claim=f"{row.label} moved with the metric (correlational)",
                value=row.value,
                unit=row.unit,
                method=row.method,
                method_class=MethodClass.STATISTICAL,
                state=row.state,
                provenance=Provenance(source_id=source_id, query=query),
                run_id=run_id,
                extra={"track": row.track.value, "correlational": True},
            )
        )
    return out
