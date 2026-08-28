"""Detection behaviour: what must be found, and what must be ignored."""

import warnings
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from whychain.detect import decompose, find_anomalies, material
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
