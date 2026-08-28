"""Answer 2 must be able to say four things, and must decline three of them.

The failure mode this file exists to catch is a stage that always finds a gap.
Such a stage passes every happy-path test, produces confident output, and is
worthless; it is asserting its premise rather than testing it. So most of what
follows is about the refusals.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from whychain.contracts import ContractRegistry
from whychain.signalgap import (
    MIN_ACTIONABLE_LEAD_HOURS,
    GapVerdict,
    WarningSignal,
    assess,
    find_gap,
    find_precedents,
    read_signals,
)
from whychain.signalgap.gap import causes_are_internal, signal_types_for

WINDOW = (date(2026, 7, 8), date(2026, 7, 12))


@pytest.fixture(scope="module")
def registry():
    return ContractRegistry.from_directory("contracts")


@pytest.fixture
def registered(registry):
    """A contract with a process document behind its signals_consumed."""
    return registry.get("net_revenue")


@pytest.fixture
def unregistered(registry):
    """A contract with no process document. Answer 2 must decline for it."""
    contract = next(
        (c for c in registry if c.signals_consumed.derived_from is None), None
    )
    if contract is None:
        pytest.skip("every contract now carries a process document")
    return contract


def signal(**kw) -> WarningSignal:
    base = {
        "signal_id": "wx-1", "signal_type": "severe_weather", "city": "Mumbai",
        "region": "West", "severity": "amber",
        "issued_at": datetime(2026, 7, 5, tzinfo=UTC),
        "valid_from": datetime(2026, 7, 8, tzinfo=UTC),
        "valid_to": datetime(2026, 7, 9, tzinfo=UTC),
        "lead_time_hours": 72.0, "is_public": True,
        "publisher": "India Meteorological Department", "source": "generated",
    }
    return WarningSignal(**{**base, **kw})


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestTheFourVerdicts:
    """All four are reachable. A stage with one reachable verdict detects nothing."""

    def test_gap_found_when_an_actionable_warning_is_not_consumed(self, registered):
        gap = assess(registered, [signal()], window=WINDOW, region="West")
        assert gap.verdict is GapVerdict.GAP_FOUND
        assert gap.best_lead_time_hours == 72.0
        assert gap.monitoring is not None

    def test_no_gap_when_nothing_was_published(self, registered):
        gap = assess(registered, [], window=WINDOW, region="West")
        assert gap.verdict is GapVerdict.NO_GAP
        assert "not foreseeable from an external feed" in gap.reason

    def test_not_foreseeable_when_the_lead_time_is_too_short(self, registered):
        """The counter-case, and the one that makes the finding credible.

        A warning that landed forty minutes ahead is real, public and severe,
        and reporting it as a process failure would be manufacturing blame in
        hindsight.
        """
        gap = assess(
            registered, [signal(lead_time_hours=0.67, severity="red")],
            window=WINDOW, region="West",
        )
        assert gap.verdict is GapVerdict.NOT_FORESEEABLE
        assert "under the" in gap.reason

    def test_coverage_unknown_when_no_process_document_is_registered(self, unregistered):
        gap = assess(unregistered, [signal()], window=WINDOW, region="West")
        assert gap.verdict is GapVerdict.COVERAGE_UNKNOWN

    def test_coverage_unknown_outranks_everything(self, unregistered):
        """Not knowing what a process reads settles nothing else.

        Even with a perfect actionable warning in hand, an unregistered process
        cannot be said to have missed it.
        """
        gap = assess(
            unregistered, [signal(lead_time_hours=96.0, severity="red")],
            window=WINDOW, region="West",
        )
        assert gap.verdict is GapVerdict.COVERAGE_UNKNOWN


class TestForeseeabilityGates:
    def test_a_private_warning_is_not_a_gap(self, registered):
        gap = assess(registered, [signal(is_public=False)], window=WINDOW, region="West")
        assert gap.verdict is GapVerdict.NOT_FORESEEABLE
        assert "public" in gap.reason

    def test_an_advisory_below_amber_is_not_a_gap(self, registered):
        gap = assess(registered, [signal(severity="yellow")], window=WINDOW, region="West")
        assert gap.verdict is GapVerdict.NOT_FORESEEABLE
        assert "amber" in gap.reason

    @pytest.mark.invariant
    def test_the_lead_time_boundary_is_not_off_by_one(self, registered):
        """Exactly at the threshold is actionable; a whisker under is not."""
        at = assess(
            registered, [signal(lead_time_hours=MIN_ACTIONABLE_LEAD_HOURS)],
            window=WINDOW, region="West",
        )
        under = assess(
            registered, [signal(lead_time_hours=MIN_ACTIONABLE_LEAD_HOURS - 0.1)],
            window=WINDOW, region="West",
        )
        assert at.verdict is GapVerdict.GAP_FOUND
        assert under.verdict is GapVerdict.NOT_FORESEEABLE

    def test_a_consumed_signal_is_not_a_gap(self, registered):
        """The process already reads it, so receiving it was never the failure."""
        consumed = next(iter(registered.signals_consumed.signal_ids))
        gap = assess(
            registered, [signal(signal_type=consumed)],
            window=WINDOW, region="West", signal_type=consumed,
        )
        assert gap.verdict is GapVerdict.NO_GAP
        assert "already consumed" in gap.reason


class TestScopedToTheCause:
    """A warning that merely shares a window with the cause is a coincidence.

    Weather warnings are in the feed most weeks of the monsoon. An engine that
    checks the window rather than the cause reports a signal gap on a release
    regression, well-evidenced, entirely wrong, and the most damaging thing
    this stage could output.
    """

    def test_an_internal_cause_consults_no_external_feed(self, registered):
        rows = frame([{
            "signal_id": "wx-1", "signal_type": "severe_weather", "city": "Mumbai",
            "region": "West", "severity": "red",
            "issued_at": datetime(2026, 7, 4, tzinfo=UTC),
            "valid_from": datetime(2026, 7, 8, tzinfo=UTC),
            "valid_to": datetime(2026, 7, 12, tzinfo=UTC),
            "lead_time_hours": 96.0, "is_public": True,
            "publisher": "IMD", "source": "generated",
        }])
        gap = find_gap(
            registered, rows,
            event_start=WINDOW[0], event_end=WINDOW[1], region="West",
            causes=["Release 4.05 broke card entry on the Android checkout flow."],
        )
        assert gap.verdict is GapVerdict.NO_GAP
        assert "internal" in gap.reason

    def test_an_external_cause_selects_the_matching_feed(self):
        assert signal_types_for(["Flooding closed two distribution centres."]) == (
            "severe_weather",
        )
        assert signal_types_for(["A regional carrier suspended operations."]) == (
            "carrier_disruption",
        )

    def test_internal_detection_needs_every_cause_to_be_internal(self):
        assert causes_are_internal(["Release 4.05 broke checkout"])
        assert not causes_are_internal(
            ["Release 4.05 broke checkout", "Heavy rainfall suppressed footfall"]
        )
        assert not causes_are_internal([])


class TestReadingTheFeed:
    def test_overlap_not_containment(self):
        """A warning that opened before the window was still available in it."""
        rows = frame([{
            "signal_id": "wx-early", "signal_type": "severe_weather", "city": "Pune",
            "region": "West", "severity": "amber",
            "issued_at": datetime(2026, 7, 1, tzinfo=UTC),
            "valid_from": datetime(2026, 7, 6, tzinfo=UTC),
            "valid_to": datetime(2026, 7, 9, tzinfo=UTC),
            "lead_time_hours": 120.0, "is_public": True,
            "publisher": "IMD", "source": "generated",
        }])
        assert len(read_signals(rows, window=WINDOW, region="West")) == 1

    def test_another_region_does_not_cover_this_slice(self):
        rows = frame([{
            "signal_id": "wx-s", "signal_type": "severe_weather", "city": "Chennai",
            "region": "South", "severity": "red",
            "issued_at": datetime(2026, 7, 4, tzinfo=UTC),
            "valid_from": datetime(2026, 7, 8, tzinfo=UTC),
            "valid_to": datetime(2026, 7, 9, tzinfo=UTC),
            "lead_time_hours": 96.0, "is_public": True,
            "publisher": "IMD", "source": "generated",
        }])
        assert read_signals(rows, window=WINDOW, region="West") == ()

    def test_an_empty_feed_is_not_an_error(self):
        assert read_signals(pd.DataFrame(), window=WINDOW) == ()


class TestRecurrence:
    @pytest.mark.invariant
    def test_consecutive_days_are_one_episode(self):
        """A five-day cyclone is one precedent, not five.

        Counting rows would inflate recurrence by exactly the length of the
        weather, and recurrence is the number the finding rests on.
        """
        rows = frame([
            {
                "signal_id": f"wx-{i}", "signal_type": "severe_weather",
                "city": "Mumbai", "region": "West", "severity": "amber",
                "issued_at": datetime(2026, 1, 1, tzinfo=UTC),
                "valid_from": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i),
                "valid_to": datetime(2026, 1, 2, tzinfo=UTC) + timedelta(days=i),
                "lead_time_hours": 48.0, "is_public": True,
                "publisher": "IMD", "source": "generated",
            }
            for i in range(5)
        ])
        found = find_precedents(
            rows, before=date(2026, 7, 1), region="West", signal_type="severe_weather"
        )
        assert len(found) == 1
        assert found[0].signal_count == 5

    def test_only_actionable_episodes_count(self):
        rows = frame([{
            "signal_id": "wx-y", "signal_type": "severe_weather", "city": "Mumbai",
            "region": "West", "severity": "yellow",
            "issued_at": datetime(2026, 1, 1, tzinfo=UTC),
            "valid_from": datetime(2026, 1, 2, tzinfo=UTC),
            "valid_to": datetime(2026, 1, 3, tzinfo=UTC),
            "lead_time_hours": 30.0, "is_public": True,
            "publisher": "IMD", "source": "generated",
        }])
        assert find_precedents(
            rows, before=date(2026, 7, 1), region="West", signal_type="severe_weather"
        ) == ()


class TestAgainstTheRealFeed:
    """The verdicts must be reachable from the generated warehouse, not only
    from hand-built frames. A state the data can never produce is a state the
    demo does not have."""

    @pytest.fixture(scope="class")
    def ext(self):
        duckdb = pytest.importorskip("duckdb")
        from pathlib import Path
        path = Path("data/warehouse/whychain.duckdb")
        if not path.exists():
            pytest.skip("run `make gen` first")
        with duckdb.connect(str(path), read_only=True) as con:
            return con.execute("SELECT * FROM ext_signals").fetchdf()

    def test_gap_found_is_reachable(self, registry, ext):
        gap = find_gap(
            registry.get("on_time_delivery"), ext,
            event_start=date(2026, 7, 8), event_end=date(2026, 7, 15), region="West",
            causes=["Flooding closed two distribution centres in the West."],
        )
        assert gap.verdict is GapVerdict.GAP_FOUND
        assert gap.recurrence >= 1

    def test_not_foreseeable_is_reachable(self, registry, ext):
        gap = find_gap(
            registry.get("on_time_delivery"), ext,
            event_start=date(2026, 5, 18), event_end=date(2026, 5, 25), region="South",
            causes=["A regional carrier suspended operations without notice."],
        )
        assert gap.verdict is GapVerdict.NOT_FORESEEABLE
