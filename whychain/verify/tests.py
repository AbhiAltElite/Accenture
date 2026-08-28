"""Causal verification.

Ranking produces candidates. This decides which of them survive being tested,
and candidates that fail never become claims. Four tests, and a candidate must
pass every one that can be run:

**Event-time isolation.** Did the effect begin only after the event? If revenue
was already falling a fortnight before the release shipped, the release did not
cause it.

**Difference in differences.** Compare the change in exposed slices against the
change in unexposed ones over the same period. Whatever moved both is
background: weather everyone had, a national holiday, a market-wide shift.

**Exposure consistency.** If a cause is real, the effect should appear roughly
wherever the cause was present. This is the test that catches a coincidence: a
promotion that ran across three regions while only one of them fell is not what
made that one fall. Correlation in a single slice looks identical to causation
until you check the other slices where the same thing happened.

**Placebo.** Run the same comparison repeatedly over periods when the cause was
absent, and compare the real effect against that spread. One quiet window is not
enough: in a growing, seasonal series any two adjacent periods differ, so a
single placebo comparison fails real causes about as often as false ones. What
matters is whether the measured effect stands outside the range the method
produces when nothing is happening.

A test that cannot run is not a test that passed. Where there is no unexposed
comparison group, or not enough history, the verdict is CANNOT_VERIFY and the
engine abstains rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

import numpy as np
import pandas as pd

from whychain.evidence import ClaimState


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNAVAILABLE = "unavailable"   # the test could not be run at all


@dataclass(frozen=True)
class TestResult:
    name: str
    outcome: Outcome
    detail: str
    statistic: float | None = None


@dataclass(frozen=True)
class Candidate:
    """A hypothesis, taken from the operational record.

    The engine cannot tell a real cause from a coincidence at this point, and
    must not try: everything recorded in the sources arrives here identically.
    """

    candidate_id: str
    kind: str
    start: date
    end: date
    exposed_regions: tuple[str, ...]
    description: str = ""
    channel: str | None = None
    device: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class Verification:
    candidate: Candidate
    results: tuple[TestResult, ...]
    effect_pct: float | None
    state: ClaimState
    reason: str
    per_region: dict[str, float] = field(default_factory=dict)

    def failed(self) -> tuple[TestResult, ...]:
        return tuple(r for r in self.results if r.outcome is Outcome.FAIL)

    def unavailable(self) -> tuple[TestResult, ...]:
        return tuple(r for r in self.results if r.outcome is Outcome.UNAVAILABLE)


# A slice has to move by at least this much for the movement to count as an
# effect rather than ordinary week-to-week variation.
EFFECT_FLOOR = 0.04
# Exposed slices must move together: if fewer than this share of them respond,
# the exposure is not what produced the response in the one that did.
CONSISTENCY_FLOOR = 0.5
# How many quiet windows to sample for the placebo distribution. Each is the same
# length as the real event and separated from it, so none overlaps the effect.
PLACEBO_WINDOWS = 6
# The real effect must exceed every placebo comparison by this much. At 1.0 it
# merely has to be the largest; above that it has to stand clearly apart.
PLACEBO_MARGIN = 1.25

# Every gate that must have actually run and passed before a candidate becomes a
# claim. Exposure consistency is deliberately absent: it is only meaningful where
# a cause was present in more than one place, and a single-region event is a
# normal case rather than an untestable one. The other three always apply where
# there is history and a comparison group, so an UNAVAILABLE among them means the
# candidate could not be tested, not that it passed.
#
# SECURITY-LOGIC-CHECKLIST §1.1 specifies all of these. Requiring only
# difference-in-differences let a candidate reach VERIFIED with its placebo never
# run, which is the failure T-11 and D-006 exist to prevent.
MANDATORY_GATES = frozenset(
    {"event_time_isolation", "difference_in_differences", "placebo"}
)


def _daily_by_region(panel: pd.DataFrame) -> pd.DataFrame:
    """Collapse the panel to one row per day and region, once.

    Every window comparison below is a sum over a date range. Doing that against
    the full row-level panel means filtering hundreds of thousands of rows for
    each of the thirty-odd windows a single verification needs, which dominates
    the runtime and computes the same daily totals over and over.
    """
    out = panel.groupby(
        [pd.to_datetime(panel["d"]).dt.date, "region"], as_index=False
    )["revenue"].sum()
    out.columns = ["day", "region", "revenue"]
    return out


def _mean(daily: pd.DataFrame, lo: date, hi: date, regions=None) -> float:
    frame = daily[(daily["day"] >= lo) & (daily["day"] <= hi)]
    if regions is not None:
        frame = frame[frame["region"].isin(regions)]
    if frame.empty:
        return float("nan")
    days = max((hi - lo).days + 1, 1)
    return float(frame["revenue"].sum()) / days


def _change(daily, candidate: Candidate, regions, baseline_days: int) -> float:
    """Proportional change from the baseline into the event window."""
    base_lo = candidate.start - timedelta(days=baseline_days)
    before = _mean(daily, base_lo, candidate.start - timedelta(days=1), regions)
    during = _mean(daily, candidate.start, candidate.end, regions)
    if not np.isfinite(before) or before == 0 or not np.isfinite(during):
        return float("nan")
    return during / before - 1.0


def _placebo_distribution(
    daily: pd.DataFrame,
    candidate: Candidate,
    exposed: tuple[str, ...],
    control: tuple[str, ...],
    baseline_days: int,
) -> list[float]:
    """The same comparison run over windows when nothing was happening.

    Each placebo sits entirely before the event and is spaced a fortnight apart,
    so none of them touches the effect being tested. What comes back is the range
    of answers this method gives on quiet data, which is what the real effect has
    to beat.
    """
    length = max((candidate.end - candidate.start).days, 1)
    out: list[float] = []
    for step in range(1, PLACEBO_WINDOWS + 1):
        end = candidate.start - timedelta(days=baseline_days + 1 + step * 14)
        window = Candidate(
            candidate_id=f"{candidate.candidate_id}-placebo-{step}",
            kind=candidate.kind, start=end - timedelta(days=length), end=end,
            exposed_regions=exposed, channel=candidate.channel,
            device=candidate.device, category=candidate.category,
        )
        treated = _change(daily, window, exposed, baseline_days)
        comparison = _change(daily, window, control, baseline_days)
        if np.isfinite(treated) and np.isfinite(comparison):
            out.append(treated - comparison)
    return out


def verify(
    candidate: Candidate,
    panel: pd.DataFrame,
    all_regions: tuple[str, ...],
    baseline_days: int = 14,
) -> Verification:
    """Run every applicable test and decide the candidate's state."""
    scoped = panel
    for column, value in (
        ("channel", candidate.channel),
        ("device", candidate.device),
        ("category", candidate.category),
    ):
        if value is not None:
            scoped = scoped[scoped[column] == value]

    daily = _daily_by_region(scoped)
    exposed = tuple(candidate.exposed_regions)
    control = tuple(r for r in all_regions if r not in exposed)

    results: list[TestResult] = []

    # --- effect in the exposed group -------------------------------------
    treated_change = _change(daily, candidate, exposed, baseline_days)
    if not np.isfinite(treated_change):
        return Verification(
            candidate, (TestResult("effect", Outcome.UNAVAILABLE, "no data in the window"),),
            None, ClaimState.CANNOT_VERIFY, "no data for the exposed slices",
        )

    # --- event-time isolation --------------------------------------------
    pre_lo = candidate.start - timedelta(days=baseline_days * 2)
    pre_hi = candidate.start - timedelta(days=baseline_days + 1)
    earlier = _mean(daily, pre_lo, pre_hi, exposed)
    baseline = _mean(daily, candidate.start - timedelta(days=baseline_days),
                     candidate.start - timedelta(days=1), exposed)
    if not np.isfinite(earlier) or earlier == 0:
        results.append(TestResult("event_time_isolation", Outcome.UNAVAILABLE,
                                  "not enough history before the event"))
    else:
        pre_trend = baseline / earlier - 1.0
        # The fall must be sharper after the event than the drift before it,
        # otherwise the event arrived in the middle of something already moving.
        already_falling = pre_trend < 0 and abs(pre_trend) > abs(treated_change) * 0.6
        results.append(
            TestResult(
                "event_time_isolation",
                Outcome.FAIL if already_falling else Outcome.PASS,
                f"movement in the fortnight before was {pre_trend:+.1%}, "
                f"during was {treated_change:+.1%}",
                pre_trend,
            )
        )

    # --- difference in differences ---------------------------------------
    if not control:
        results.append(TestResult("difference_in_differences", Outcome.UNAVAILABLE,
                                  "the cause was present everywhere, so no comparison group exists"))
        did = None
    else:
        control_change = _change(daily, candidate, control, baseline_days)
        if not np.isfinite(control_change):
            results.append(TestResult("difference_in_differences", Outcome.UNAVAILABLE,
                                      "no data for the comparison group"))
            did = None
        else:
            did = treated_change - control_change
            results.append(
                TestResult(
                    "difference_in_differences",
                    Outcome.PASS if abs(did) >= EFFECT_FLOOR else Outcome.FAIL,
                    f"exposed {treated_change:+.1%} against comparison "
                    f"{control_change:+.1%}, difference {did:+.1%}",
                    did,
                )
            )

    # --- exposure consistency --------------------------------------------
    per_region = {
        region: _change(daily, candidate, (region,), baseline_days) for region in exposed
    }
    usable = {r: v for r, v in per_region.items() if np.isfinite(v)}
    if len(usable) < 2:
        results.append(TestResult("exposure_consistency", Outcome.UNAVAILABLE,
                                  "the cause was present in only one place, so consistency "
                                  "cannot be checked"))
    else:
        direction = -1.0 if treated_change < 0 else 1.0
        # A region counts as responding if it moved in the same direction as the
        # overall effect, by at least the floor.
        responded = [r for r, v in usable.items() if v * direction >= EFFECT_FLOOR]
        share = len(responded) / len(usable)
        results.append(
            TestResult(
                "exposure_consistency",
                Outcome.PASS if share >= CONSISTENCY_FLOOR else Outcome.FAIL,
                f"present in {len(usable)} regions, {len(responded)} moved "
                f"({', '.join(f'{r} {v:+.1%}' for r, v in usable.items())})",
                share,
            )
        )

    # --- placebo ----------------------------------------------------------
    if did is None or not control:
        results.append(TestResult("placebo", Outcome.UNAVAILABLE,
                                  "no comparison group, so there is nothing to permute"))
    else:
        placebos = _placebo_distribution(
            daily, candidate, exposed, control, baseline_days
        )
        if len(placebos) < 3:
            results.append(TestResult("placebo", Outcome.UNAVAILABLE,
                                      f"only {len(placebos)} quiet windows available; "
                                      "not enough history to establish a spread"))
        else:
            worst = max(abs(p) for p in placebos)
            stands_apart = abs(did) >= worst * PLACEBO_MARGIN
            results.append(
                TestResult(
                    "placebo",
                    Outcome.PASS if stands_apart else Outcome.FAIL,
                    f"across {len(placebos)} quiet windows the same comparison ranged "
                    f"{min(placebos):+.1%} to {max(placebos):+.1%}; the measured "
                    f"{did:+.1%} is {abs(did) / worst:.1f} times the largest of them",
                    worst,
                )
            )

    return _decide(candidate, tuple(results), treated_change, per_region)


def _decide(
    candidate: Candidate,
    results: tuple[TestResult, ...],
    effect: float,
    per_region: dict[str, float],
) -> Verification:
    """Turn test outcomes into a state.

    Any failure rejects. Otherwise every mandatory test must have actually run:
    an unavailable test leaves the candidate unverifiable, never verified by
    default. See DECISIONS.md D-006.
    """
    failures = [r for r in results if r.outcome is Outcome.FAIL]
    if failures:
        return Verification(
            candidate, results, effect, ClaimState.REJECTED,
            "failed " + ", ".join(r.name.replace("_", " ") for r in failures),
            per_region,
        )

    ran = {r.name for r in results if r.outcome is Outcome.PASS}
    missing = MANDATORY_GATES - ran
    if missing:
        return Verification(
            candidate, results, effect, ClaimState.CANNOT_VERIFY,
            "could not run " + ", ".join(sorted(m.replace("_", " ") for m in missing)),
            per_region,
        )

    return Verification(
        candidate, results, effect, ClaimState.VERIFIED,
        "passed every test that could be run", per_region,
    )
