"""Detection behaviour: what must be found, and what must be ignored."""

import warnings
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from whychain.contracts import ContractRegistry
from whychain.detect import (
    decompose,
    decompose_for,
    find_anomalies,
    material,
    seasonal_periods,
)
from whychain.detect.calendar import festival_factor

warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")


def synthetic(days: int = 500, level: float = 200_000.0, noise: float = 0.04, seed: int = 3):
    """A clean multiplicative series with weekly rhythm and mild growth."""
    rng = np.random.default_rng(seed)
    start = date(2024, 1, 1)
    d = pd.date_range(start, periods=days, freq="D")
    weekday = np.array([(0.94, 0.92, 0.95, 0.99, 1.08, 1.18, 1.12)[x.weekday()] for x in d])
    trend = (1.08) ** (np.arange(days) / 365.25)
    value = level * weekday * trend * rng.normal(1.0, noise, days)
    return pd.DataFrame({"d": d, "value": value})


class TestCalendar:
    def test_diwali_lifts_then_depresses(self):
        d = pd.Series(pd.date_range("2025-10-01", "2025-11-01", freq="D"))
        f = festival_factor(d)
        assert f.max() > 1.8, "the festival peak should be unmistakable"
        assert f.min() < 0.85, "and the day after should fall below baseline"

    def test_ordinary_month_is_flat(self):
        f = festival_factor(pd.Series(pd.date_range("2026-06-01", "2026-06-25", freq="D")))
        assert np.allclose(f, 1.0), "June has no shopping festival"


class TestDecomposition:
    def test_needs_enough_history(self):
        with pytest.raises(ValueError, match="at least 60 days"):
            decompose(synthetic(days=30))

    def test_components_reconstruct_the_expectation(self):
        d = decompose(synthetic())
        assert np.allclose(d.expected, d.trend + d.seasonal, rtol=1e-9)

    def test_residual_is_the_gap_from_expectation(self):
        d = decompose(synthetic())
        assert np.allclose(d.residual, d.observed - d.expected, rtol=1e-9)

    def test_band_brackets_the_expectation(self):
        d = decompose(synthetic())
        assert np.all(d.band_low < d.expected) and np.all(d.expected < d.band_high)


@pytest.mark.invariant
class TestFalseAlarms:
    """A detector that fires on ordinary variation is one people switch off."""

    def test_quiet_series_is_quiet(self):
        d = decompose(synthetic(days=700))
        flagged = find_anomalies(d, threshold=3.0)
        assert len(flagged) / 700 < 0.02, (
            f"{len(flagged)} flags on a series with nothing in it"
        )

    def test_festival_weeks_are_not_anomalies(self):
        """The whole point: a Diwali collapse is large and completely normal."""
        frame = synthetic(days=700)
        frame["d"] = pd.date_range("2025-01-01", periods=700, freq="D")
        frame["value"] = frame["value"].to_numpy() * festival_factor(frame["d"])

        flagged = find_anomalies(decompose(frame), threshold=3.0)
        peak = date(2025, 10, 20)
        window = {peak + timedelta(days=i) for i in range(-18, 8)}
        caught = [a for a in flagged if a.day in window]
        assert not caught, f"flagged {[str(a.day) for a in caught]} around Diwali"


@pytest.mark.invariant
class TestDetection:
    def test_finds_a_planted_drop(self):
        frame = synthetic(days=600)
        hit = slice(500, 507)
        frame.loc[hit, "value"] *= 0.80  # a twenty per cent fall for a week

        flagged = find_anomalies(decompose(frame), threshold=3.0)
        days = {a.day for a in flagged}
        planted = {frame.loc[i, "d"].date() for i in range(500, 507)}
        assert len(days & planted) >= 4, "most of a week-long twenty per cent fall should surface"
        assert all(a.direction == "drop" for a in flagged if a.day in planted)

    def test_proportional_noise_does_not_inflate_busy_days(self):
        """Retail variation is proportional; an additive model flags every peak."""
        frame = synthetic(days=600, noise=0.06)
        frame["value"] *= np.linspace(1.0, 3.0, 600)  # level triples across the series

        z = decompose(frame).robust_z
        early, late = np.abs(z[:200]).mean(), np.abs(z[-200:]).mean()
        assert late < early * 2.0, (
            "deviation should not grow with the level once decomposed in log space"
        )


class TestMateriality:
    def test_both_tests_must_pass(self):
        from whychain.contracts import ContractRegistry
        from whychain.detect.anomaly import Anomaly

        contract = ContractRegistry.from_directory("contracts").get("net_revenue")
        floor = contract.materiality.min_abs_delta_inr

        significant_but_small = Anomaly(date(2026, 1, 1), 100.0, 200.0, -100.0, -9.0, "drop")
        large_but_insignificant = Anomaly(date(2026, 1, 2), 1.0, floor * 3, -floor * 2, -1.0, "drop")
        both = Anomaly(date(2026, 1, 3), 1.0, floor * 3, -floor * 2, -9.0, "drop")

        kept = material([significant_but_small, large_but_insignificant, both], contract)
        assert [a.day for a in kept] == [date(2026, 1, 3)]


def hourly(hours: int = 24 * 200, rate: float = 0.043, seed: int = 5):
    """An hourly rate with nothing wrong with it, on a realistic volume curve.

    The *rate* is constant, deliberately. What swings is the number of sessions
    behind it: about 50 at midnight against 900 in the evening, which is the
    shape the real feed has. Everything the detector then finds in this series
    is a false alarm by construction, and how many it finds depends entirely on
    whether it knows a rate read off 50 trials is a softer number than the same
    rate read off 900.
    """
    rng = np.random.default_rng(seed)
    h = pd.date_range("2025-01-01", periods=hours, freq="h")
    curve = np.array([49, 30, 25, 24, 28, 38, 61, 122, 219, 316, 414, 511, 584,
                      535, 462, 438, 487, 584, 730, 876, 925, 779, 462, 195])
    n = np.maximum(curve[h.hour] * rng.normal(1.0, 0.12, hours), 20.0).round()
    converted = rng.binomial(n.astype(int), rate).astype(float)
    return pd.DataFrame({"d": h, "value": converted / n, "n": n})


@pytest.mark.invariant
class TestGrainAwareness:
    """B-018. A constant that is right at one grain is wrong at another."""

    def test_periods_are_the_grain_s_own_rhythms(self):
        assert seasonal_periods("day") == (7,), "day of week"
        assert seasonal_periods("hour") != seasonal_periods("day"), (
            "seven means 'day of week' on a daily series and 'seven hours' on an "
            "hourly one, which is not a cycle anything has"
        )

    def test_an_unknown_grain_refuses_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="no seasonal periods configured"):
            seasonal_periods("minute")

    def test_contract_supplies_the_grain_and_the_denominator(self):
        contract = ContractRegistry.from_directory("contracts").get("checkout_conversion")
        assert contract.grain.time == "hour", "the fixture this test rests on"
        frame = hourly()
        assert np.allclose(
            decompose_for(frame, contract).robust_z,
            decompose(frame, periods=seasonal_periods("hour"), denominator=frame["n"],
                      grain="hour", proportion=True).robust_z,
        ), "decompose_for must read the grain, the denominator and the unit off the contract"

    def test_history_is_required_in_the_series_own_units(self):
        """Sixty rows of hourly data is two and a half days, not sixty days."""
        with pytest.raises(ValueError, match="hours"):
            decompose(hourly(hours=80), periods=(24,), grain="hour")


@pytest.mark.invariant
class TestVolumeWeightedNoise:
    """A rate off fifty trials and one off nine hundred are not equally certain."""

    def test_quiet_hours_do_not_flag_more_than_busy_ones(self):
        frame = hourly()
        d = decompose_for(
            frame, ContractRegistry.from_directory("contracts").get("checkout_conversion")
        )
        flagged = np.abs(d.robust_z) >= 3.0
        thin = frame["n"] <= frame["n"].quantile(0.1)
        busy = frame["n"] >= frame["n"].quantile(0.9)
        assert flagged[thin].mean() < 4 * max(flagged[busy].mean(), 1e-4), (
            f"thin hours flag at {flagged[thin].mean():.1%} against "
            f"{flagged[busy].mean():.1%} for busy ones; the detector is reporting "
            f"session counts rather than checkout behaviour"
        )

    def test_a_clean_rate_series_is_quiet_at_every_volume(self):
        frame = hourly()
        d = decompose_for(
            frame, ContractRegistry.from_directory("contracts").get("checkout_conversion")
        )
        rate = float((np.abs(d.robust_z) >= 3.0).mean())
        assert rate < 0.01, (
            f"{rate:.2%} of a series with nothing in it flagged; z>=3 on a "
            f"calibrated scale should be well under one per cent"
        )

    def test_an_empty_hour_is_not_automatically_an_anomaly(self):
        """At a 4.3% rate over fifty sessions, no conversions is one hour in nine."""
        frame = hourly()
        d = decompose_for(
            frame, ContractRegistry.from_directory("contracts").get("checkout_conversion")
        )
        empty = frame["value"].to_numpy() == 0.0
        assert empty.sum() > 20, "the fixture should contain empty hours to test"
        assert (np.abs(d.robust_z)[empty] >= 3.0).mean() < 0.2, (
            "flooring a zero rate to take its logarithm makes every empty period "
            "an extreme outlier; the half-count correction exists to stop that"
        )

    def test_the_band_widens_where_the_reading_is_thinner(self):
        frame = hourly()
        d = decompose_for(
            frame, ContractRegistry.from_directory("contracts").get("checkout_conversion")
        )
        width = (d.band_high - d.band_low) / d.expected
        thin = frame["n"] <= frame["n"].quantile(0.1)
        busy = frame["n"] >= frame["n"].quantile(0.9)
        assert width[thin].mean() > width[busy].mean(), (
            "a chart that draws one band width over a twentyfold swing in volume "
            "is telling the reader the thin hours are more certain than they are"
        )

    def test_the_same_fall_is_an_event_when_busy_and_noise_when_quiet(self):
        """This pair is the whole argument for weighting rather than raising z.

        One gateway outage, the same sixty per cent fall in conversion over six
        consecutive hours, planted twice: once across the evening peak and once
        across the small hours. In the peak it is roughly 150 orders that did
        not happen and the detector should say so. At three in the morning it is
        about one order on twenty-six sessions, which is indistinguishable from
        an ordinary quiet night and the detector should keep quiet.

        Raising the z threshold would have silenced both. That is the difference
        between calibrating a detector and turning it down.
        """
        contract = ContractRegistry.from_directory("contracts").get("checkout_conversion")
        frame = hourly()
        day = frame["d"].dt.date == frame["d"].dt.date.iloc[24 * 120]

        def outage(lo: int, hi: int):
            hit = frame.index[day & frame["d"].dt.hour.between(lo, hi)]
            struck = frame.copy()
            struck.loc[hit, "value"] = struck.loc[hit, "value"] * 0.4
            z = decompose_for(struck, contract).robust_z[hit]
            return int((np.abs(z) >= 3.0).sum()), struck.loc[hit, "n"].median()

        peak_flags, peak_sessions = outage(17, 22)
        night_flags, night_sessions = outage(1, 6)

        assert peak_sessions > 10 * night_sessions, "the fixture this test rests on"
        assert peak_flags >= 2, (
            f"a sixty per cent fall over six hours at ~{peak_sessions:.0f} sessions "
            f"an hour surfaced on {peak_flags} of them"
        )
        assert night_flags == 0, (
            f"the same proportional fall at ~{night_sessions:.0f} sessions an hour "
            f"is about one order; flagging it {night_flags} times is reporting "
            f"binomial noise as a checkout incident"
        )
