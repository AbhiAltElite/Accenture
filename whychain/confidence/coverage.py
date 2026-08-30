"""How much of a movement the verified causes actually account for.

A cause moves the slice it touched, not the whole business. A checkout
regression confined to one channel on one device explains its share of the fall,
and treating its percentage as if it applied everywhere overstates coverage
badly, which in turn overstates confidence.

So each verified cause is converted to rupees on its own slice, using that
slice's revenue in the baseline period. Overlapping causes are capped rather than
summed past the movement itself: two causes cannot explain a hundred and forty
per cent of a fall.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from whychain.evidence import ClaimState


def _slice_revenue(
    panel: pd.DataFrame, candidate, lo: date, hi: date
) -> float:
    """Daily revenue of the slice a candidate touched, over a period."""
    day = pd.to_datetime(panel["d"]).dt.date
    frame = panel[(day >= lo) & (day <= hi)]
    if candidate.exposed_regions:
        frame = frame[frame["region"].isin(candidate.exposed_regions)]
    for column, value in (
        ("channel", candidate.channel),
        ("device", candidate.device),
        ("category", candidate.category),
    ):
        if value is not None:
            frame = frame[frame[column] == value]
    if frame.empty:
        return 0.0
    return float(frame["revenue"].sum()) / max((hi - lo).days + 1, 1)


def explained_movement(
    verifications,
    panel: pd.DataFrame,
    event_start: date,
    event_end: date,
    baseline_days: int = 14,
    total_movement: float | None = None,
) -> tuple[float, dict[str, float], float]:
    """Rupees per day accounted for by verified causes, and the split between them.

    Returns the total, a per-cause breakdown so a reader can see which cause
    carried what rather than being handed one number, and how far the causes
    overlap.

    That third number used to be computed and thrown away, which was the defect.
    Capping the total at the movement is right -- three causes cannot account
    for a hundred and eighty-eight per cent of a fall -- but *silently* capping
    it reported perfect coverage in exactly the case where the split between the
    causes is least trustworthy, and perfect coverage is worth the largest single
    component of the confidence score. The cap stays; what it concealed is now
    returned with it.

    The ratio is gross attribution over actual movement: 1.0 when the causes do
    not overlap at all, 1.88 when they sum to nearly twice what happened. It is
    never below 1.0, so a caller can treat it as a multiplier without checking.
    """
    base_lo = event_start - timedelta(days=baseline_days)
    base_hi = event_start - timedelta(days=1)

    per_cause: dict[str, float] = {}
    for v in verifications:
        if v.state is not ClaimState.VERIFIED or v.effect_pct is None:
            continue
        slice_base = _slice_revenue(panel, v.candidate, base_lo, base_hi)
        per_cause[v.candidate.candidate_id] = slice_base * v.effect_pct

    total = sum(per_cause.values())

    # Causes can overlap: a weather event and a release both hit the same days.
    # Explaining more of the movement than occurred is a sign of double counting,
    # not of unusually complete understanding.
    overlap = 1.0
    if total_movement is not None and total_movement != 0 and total:
        overlap = max(abs(total) / abs(total_movement), 1.0)
    if overlap > 1.0:
        total = total_movement

    return total, per_cause, overlap
