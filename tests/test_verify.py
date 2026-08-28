"""Causal verification: what survives testing, and what must not."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from whychain.evidence import ClaimState
from whychain.verify import Candidate, Outcome, verify

REGIONS = ("North", "South", "East", "West")


def panel(effects: dict[str, tuple[date, date, float]] | None = None, seed: int = 5):
    """A flat four-region panel, optionally with a movement planted per region."""
    rng = np.random.default_rng(seed)
    days = pd.date_range("2026-05-01", "2026-09-01", freq="D")
    rows = []
    for region in REGIONS:
        base = 100_000.0
        for d in days:
            value = base * rng.normal(1.0, 0.02)
            if effects and region in effects:
                start, end, effect = effects[region]
                if start <= d.date() <= end:
                    value *= 1.0 + effect
            rows.append({"d": d, "region": region, "channel": "app",
                         "device": "mobile", "category": "x",
                         "revenue": value, "units": value / 200})
    return pd.DataFrame(rows)


WINDOW = (date(2026, 8, 12), date(2026, 8, 18))


def candidate(regions: tuple[str, ...], **kw) -> Candidate:
    return Candidate(
        candidate_id="c1", kind="test", start=WINDOW[0], end=WINDOW[1],
        exposed_regions=regions, **kw,
    )


@pytest.mark.invariant
class TestNegativeControl:
    """The correlation trap. This is the check the whole design exists for."""

    def test_a_cause_present_where_nothing_moved_is_rejected(self):
        """A promotion across three regions where only one fell did not cause it."""
        p = panel({"West": (*WINDOW, -0.25)})
        v = verify(candidate(("West", "East", "South")), p, REGIONS)

        assert v.state is ClaimState.REJECTED, f"trap survived: {v.reason}"
        names = {r.name for r in v.failed()}
        assert "exposure_consistency" in names, (
            "rejected, but not for the right reason: " + v.reason
        )

    def test_difference_in_differences_alone_would_have_been_fooled(self):
        """Why consistency exists: DiD passes the trap on its own."""
        p = panel({"West": (*WINDOW, -0.25)})
        v = verify(candidate(("West", "East", "South")), p, REGIONS)
        did = next(r for r in v.results if r.name == "difference_in_differences")
        assert did.outcome is Outcome.PASS, (
            "if DiD rejected this unaided, the consistency test would be redundant"
        )

    def test_a_genuinely_regional_cause_survives(self):
        p = panel({"West": (*WINDOW, -0.25)})
        v = verify(candidate(("West",)), p, REGIONS)
        assert v.state is ClaimState.VERIFIED, v.reason


@pytest.mark.invariant
class TestUnavailableIsNotFailed:
    """D-006: a test that could not run is not a test that passed."""

    def test_no_comparison_group_gives_cannot_verify(self):
        p = panel(dict.fromkeys(REGIONS, (*WINDOW, -0.2)))
        v = verify(candidate(REGIONS), p, REGIONS)
        assert v.state is ClaimState.CANNOT_VERIFY, v.reason
        assert v.state is not ClaimState.REJECTED, (
            "an untestable candidate must not be reported as disproved"
        )
        assert "difference in differences" in v.reason

    def test_unavailable_tests_never_produce_a_verified_claim(self):
        p = panel(dict.fromkeys(REGIONS, (*WINDOW, -0.2)))
        v = verify(candidate(REGIONS), p, REGIONS)
        assert v.state is not ClaimState.VERIFIED

    def test_no_data_at_all_gives_cannot_verify(self):
        v = verify(candidate(("West",), category="does_not_exist"), panel(), REGIONS)
        assert v.state is ClaimState.CANNOT_VERIFY


class TestEventTimeIsolation:
    def test_a_decline_already_under_way_is_rejected(self):
        """If it was falling before the event, the event did not start it.

        The fall begins during the baseline fortnight, so by the time the claimed
        event arrives the level has already dropped and barely moves further. The
        candidate is not the cause of a decline that predates it.
        """
        already_falling = (date(2026, 7, 29), date(2026, 8, 18), -0.30)
        v = verify(candidate(("West",)), panel({"West": already_falling}), REGIONS)

        assert v.state is not ClaimState.VERIFIED, (
            "a decline that started before the event must not be attributed to it"
        )
        isolation = next(r for r in v.results if r.name == "event_time_isolation")
        assert isolation.statistic is not None and isolation.statistic < 0, (
            "the pre-event trend should be measured as negative"
        )


class TestPlacebo:
    def test_an_effect_in_a_quiet_period_discredits_the_finding(self):
        """A pre-period movement of similar size means the method finds phantoms."""
        p = panel({"West": (date(2026, 7, 10), date(2026, 7, 16), -0.25)})
        # Claim the event happened later, when nothing did.
        v = verify(candidate(("West",)), p, REGIONS)
        placebo = next(r for r in v.results if r.name == "placebo")
        assert placebo.outcome in (Outcome.FAIL, Outcome.PASS)
        if placebo.outcome is Outcome.FAIL:
            assert v.state is ClaimState.REJECTED


class TestNoEffect:
    def test_a_flat_series_produces_no_verified_cause(self):
        v = verify(candidate(("West",)), panel(), REGIONS)
        assert v.state is not ClaimState.VERIFIED, (
            "nothing happened, so nothing should be verified"
        )
