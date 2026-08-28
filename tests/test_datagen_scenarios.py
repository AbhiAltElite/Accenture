"""Scenario definitions: the properties that make the benchmark trustworthy."""

from datetime import date

import pytest

from datagen.calendar import festival_peaks, festival_uplift, weekday_uplift
from datagen.catalog import CHANNEL_DEVICES, CITIES, PRODUCTS, cities_in, region_of
from datagen.demo_cases import DEMO_SCENARIOS, MULTI_FACTOR, NOT_FORESEEABLE, SIGNAL_GAP
from datagen.scenarios import ExpectedVerdict, Slice


class TestCalendar:
    def test_diwali_2025_is_found(self):
        """Dates come from the holidays package; a wrong one moves the decoy."""
        peaks = festival_peaks(date(2025, 10, 1), date(2025, 10, 31))
        assert date(2025, 10, 20) in peaks
        assert peaks[date(2025, 10, 20)] == pytest.approx(0.85)

    def test_demand_builds_then_collapses(self):
        """The shape is the point — a one-day bump would be a trivial decoy."""
        uplift = festival_uplift(date(2025, 10, 1), date(2025, 11, 5))
        peak, day_after = uplift[date(2025, 10, 20)], uplift[date(2025, 10, 21)]
        assert peak > 1.8, "Diwali should roughly double demand at its peak"
        assert day_after < 0.85, "and collapse below baseline immediately after"
        assert uplift[date(2025, 10, 14)] < uplift[date(2025, 10, 19)], "build-up rises"

    def test_weekend_outsells_midweek(self):
        assert weekday_uplift(date(2026, 8, 15)) > weekday_uplift(date(2026, 8, 11))


class TestCatalog:
    def test_regional_weights_sum_to_one(self):
        for region in ("North", "South", "East", "West"):
            assert sum(c.weight for c in cities_in(region)) == pytest.approx(1.0)

    def test_stores_have_no_browser(self):
        """A device/channel join that ignores this invents desktop store sales."""
        assert CHANNEL_DEVICES["store"] == ("pos",)
        assert "pos" not in CHANNEL_DEVICES["web"]

    def test_coordinates_are_plausible_for_india(self):
        """Weather is pulled against these, so a wrong sign fetches the wrong hemisphere."""
        for city in CITIES:
            assert 6 < city.lat < 37, f"{city.name} latitude outside India"
            assert 68 < city.lon < 98, f"{city.name} longitude outside India"

    def test_one_sku_has_sparse_history(self):
        late = [p for p in PRODUCTS if p.launched_month > 0]
        assert len(late) == 1 and late[0].sku == "PC-1099"

    def test_region_lookup(self):
        assert region_of("Pune") == "West"
        with pytest.raises(KeyError):
            region_of("Atlantis")


class TestSlice:
    def test_none_means_all(self):
        assert Slice().matches(region="West", device="mobile")

    def test_narrows_on_every_named_dimension(self):
        s = Slice(region="West", device="mobile")
        assert s.matches(region="West", device="mobile", channel="app")
        assert not s.matches(region="East", device="mobile")
        assert not s.matches(region="West", device="desktop")


@pytest.mark.invariant
class TestNegativeControl:
    """The trap is what converts "you planted it" into a measurable claim."""

    def test_decoy_has_no_effect(self):
        decoy = MULTI_FACTOR.decoys[0]
        assert decoy.effect == 0.0, "a decoy that moves the metric is not a decoy"
        assert decoy.is_decoy

    def test_decoy_also_runs_where_nothing_happened(self):
        """Without this, difference-in-differences has nothing to reject it with."""
        decoy = MULTI_FACTOR.decoys[0]
        assert decoy.also_in, "a decoy confined to the affected region is untestable"
        assert decoy.target.region not in decoy.also_in

    def test_decoy_overlaps_the_real_cause_in_time(self):
        """It has to correlate, or a naive method would not fall for it."""
        bug = next(c for c in MULTI_FACTOR.causes if c.event_id == "rel-4.05")
        decoy = MULTI_FACTOR.decoys[0]
        assert decoy.start == bug.start, "the trap must fire with the real cause"

    def test_sources_cannot_distinguish_a_decoy(self):
        """If a decoy looked different in the data, the engine could cheat."""
        kinds = {type(e) for e in MULTI_FACTOR.events}
        assert len(kinds) == 1
        assert len(MULTI_FACTOR.events) == len(MULTI_FACTOR.causes) + len(MULTI_FACTOR.decoys)


@pytest.mark.invariant
class TestForeseeability:
    """Available before the event is not the same as actionable."""

    def test_gap_case_has_a_usable_warning(self):
        signal = SIGNAL_GAP.signals[0]
        assert signal.is_public and signal.lead_time_hours >= 24
        assert signal.covers.region == "West", "a national alert would not be specific enough"

    def test_refusal_case_warning_is_technically_public_but_useless(self):
        signal = NOT_FORESEEABLE.signals[0]
        assert signal.is_public, "the point is that it existed"
        assert signal.lead_time_hours < 1, "and still was not actionable"


class TestDemoCoverage:
    def test_every_expected_verdict_is_exercised(self):
        """A demo that only shows success proves nothing about the failure paths."""
        assert {s.expected for s in DEMO_SCENARIOS} == set(ExpectedVerdict)

    def test_case_ids_unique(self):
        ids = [s.case_id for s in DEMO_SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_windows_leave_room_for_a_baseline(self):
        for scenario in DEMO_SCENARIOS:
            assert scenario.window_days() >= 14, f"{scenario.case_id}: window too short"

    def test_seasonal_decoy_plants_nothing(self):
        decoy = next(s for s in DEMO_SCENARIOS if s.expected is ExpectedVerdict.NO_ANOMALY)
        assert not decoy.causes and not decoy.decoys
