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


def is_relevant(
    candidate, window_start: date, window_end: date, region: str | None
) -> Relevance:
    """Both gates. A candidate must pass each to be worth testing."""
    for gate in (
        overlaps_window(candidate, window_start, window_end),
        touches_region(candidate, region),
    ):
        if not gate.relevant:
            return gate
    return Relevance(True, "overlaps the movement in time and place")


def filter_relevant(
    candidates, window_start: date, window_end: date, region: str | None
) -> tuple[list, list[tuple[object, str]]]:
    """Split candidates into those worth testing and those set aside.

    The set-aside ones are returned rather than dropped, because "this was
    considered and ruled out before testing" is information a reader may want,
    and silently discarding candidates is how an engine starts looking more
    certain than it is.
    """
    keep, aside = [], []
    for candidate in candidates:
        verdict = is_relevant(candidate, window_start, window_end, region)
        if verdict.relevant:
            keep.append(candidate)
        else:
            aside.append((candidate, verdict.reason))
    return keep, aside
