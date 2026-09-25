"""Deciding which candidates could plausibly explain *this* movement.

Verification answers whether a candidate had an effect. It does not answer
whether that effect explains the movement in front of us, and the two questions
are easy to confuse.

A supplier shortfall in the East is a real event that really moved the East. If
it happens to fall inside the window while we are looking at a quiet week in the
West, verification will pass it, and an engine that stops there reports a cause
for a movement that never happened. That is where false alarms come from: not
from testing badly, but from testing candidates that were never relevant.

Two gates, both cheap and both deterministic. A candidate must overlap the
movement in time, and it must touch the part of the business the movement
occurred in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# How far outside the movement window a candidate may start and still be a
# plausible cause of it. An event a fortnight earlier whose effect only appears
# now is possible but rare, and treating it as plausible admits most of the
# calendar.
LEAD_TOLERANCE_DAYS = 7
LAG_TOLERANCE_DAYS = 2


@dataclass(frozen=True)
class Relevance:
    relevant: bool
    reason: str


def overlaps_window(
    candidate, window_start: date, window_end: date
) -> Relevance:
    """Did the candidate's period touch the movement's period?"""
    earliest = window_start - timedelta(days=LEAD_TOLERANCE_DAYS)
    latest = window_end + timedelta(days=LAG_TOLERANCE_DAYS)
    if candidate.end < earliest:
        return Relevance(False, "ended before the movement began")
    if candidate.start > latest:
        return Relevance(False, "began after the movement ended")
    return Relevance(True, "overlaps the movement in time")


def touches_region(candidate, region: str | None) -> Relevance:
    """Did it happen where the movement happened?

    A candidate with no region recorded applies everywhere and is left in: an
    unrecorded scope is missing information, not evidence of irrelevance.
    """
    if region is None or not candidate.exposed_regions:
        return Relevance(True, "no regional scope to exclude it")
    if region in candidate.exposed_regions:
        return Relevance(True, f"was present in {region}")
    return Relevance(
        False,
        f"was confined to {', '.join(candidate.exposed_regions)}, "
        f"and the movement is in {region}",
    )


def touches_scope(candidate, slice_: dict[str, str] | None) -> Relevance:
    """Did it happen in the part of the business the movement is sliced to?

    The same argument as `touches_region`, one level finer. A release regression
    recorded against the app on mobile is a real event that really moved the
    app. Asked about the store channel it is not a weak candidate, it is not a
    candidate at all, and an engine that tests it anyway will sometimes pass it
    and report a cause that could not have produced the movement in front of it.

    This gate exists because the reader can now narrow by channel and device. A
    filter that changes what is decomposed without changing what is considered
    is how a false explanation gets in.

    Unrecorded is not excluded, for the reason `touches_region` gives: a
    candidate whose channel was never extracted from the note is missing
    information, not evidence of irrelevance.
    """
    for dimension, value in (slice_ or {}).items():
        recorded = getattr(candidate, dimension, None)
        if recorded and recorded != value:
            return Relevance(
                False,
                f"was confined to {dimension} {recorded}, "
                f"and the movement is in {value}",
            )
    return Relevance(True, "no finer scope to exclude it")


def is_relevant(
    candidate,
    window_start: date,
    window_end: date,
    region: str | None,
    slice_: dict[str, str] | None = None,
) -> Relevance:
    """Every gate. A candidate must pass each to be worth testing."""
    for gate in (
        overlaps_window(candidate, window_start, window_end),
        touches_region(candidate, region),
        touches_scope(candidate, slice_),
    ):
        if not gate.relevant:
            return gate
    return Relevance(True, "overlaps the movement in time and place")


def filter_relevant(
    candidates,
    window_start: date,
    window_end: date,
    region: str | None,
    slice_: dict[str, str] | None = None,
) -> tuple[list, list[tuple[object, str]]]:
    """Split candidates into those worth testing and those set aside.

    The set-aside ones are returned rather than dropped, because "this was
    considered and ruled out before testing" is information a reader may want,
    and silently discarding candidates is how an engine starts looking more
    certain than it is.
    """
    keep, aside = [], []
    for candidate in candidates:
        verdict = is_relevant(candidate, window_start, window_end, region, slice_)
        if verdict.relevant:
            keep.append(candidate)
        else:
            aside.append((candidate, verdict.reason))
    return keep, aside
