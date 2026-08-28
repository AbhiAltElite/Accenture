"""Bridge and contribution: the identity must hold, or nothing may be reported."""

import numpy as np
import pandas as pd
import pytest

from whychain.decompose import (
    Bridge,
    BridgeError,
    compute_bridge,
    contribution_by,
)


def frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


BASE = frame(sku=["A", "B"], units=[100.0, 100.0], revenue=[1000.0, 2000.0])


@pytest.mark.invariant
class TestIdentity:
    """I-17: the bridge reconciles, and says so rather than being trusted."""

    def test_effects_sum_to_the_movement(self):
        current = frame(sku=["A", "B"], units=[85.0, 70.0], revenue=[900.0, 1500.0])
        b = compute_bridge(BASE, current)
        assert b.explained == pytest.approx(b.total_change, abs=1e-9)
        b.assert_reconciles()

    def test_a_broken_bridge_refuses_to_report(self):
        broken = Bridge(
            base_revenue=1000.0, current_revenue=900.0,
            volume_effect=-10.0, mix_effect=0.0, price_effect=0.0,
            base_units=10.0, current_units=9.0, products=1,
        )
        with pytest.raises(BridgeError, match="does not reconcile"):
            broken.assert_reconciles()

    def test_holds_across_random_movements(self):
        """Property check: a hundred random period pairs must all reconcile."""
        rng = np.random.default_rng(0)
        for _ in range(100):
            n = int(rng.integers(2, 9))
            skus = [f"S{i}" for i in range(n)]
            u0 = rng.uniform(10, 500, n)
            u1 = rng.uniform(10, 500, n)
            p0 = rng.uniform(50, 900, n)
            p1 = p0 * rng.uniform(0.7, 1.3, n)
            b = compute_bridge(
                frame(sku=skus, units=u0, revenue=u0 * p0),
                frame(sku=skus, units=u1, revenue=u1 * p1),
            )
            assert b.explained == pytest.approx(b.total_change, rel=1e-9, abs=1e-6)


class TestEffectIsolation:
    """Each effect must capture only its own kind of change."""

    def test_pure_volume(self):
        b = compute_bridge(BASE, frame(sku=["A", "B"], units=[80.0, 80.0], revenue=[800.0, 1600.0]))
        assert b.volume_effect == pytest.approx(-600.0)
        assert b.mix_effect == pytest.approx(0.0, abs=1e-9)
        assert b.price_effect == pytest.approx(0.0, abs=1e-9)

    def test_pure_price(self):
        b = compute_bridge(BASE, frame(sku=["A", "B"], units=[100.0, 100.0], revenue=[500.0, 2000.0]))
        assert b.price_effect == pytest.approx(-500.0)
        assert b.volume_effect == pytest.approx(0.0, abs=1e-9)
        assert b.mix_effect == pytest.approx(0.0, abs=1e-9)

    def test_pure_mix(self):
        """Same total units, shifted toward the cheaper product."""
        b = compute_bridge(BASE, frame(sku=["A", "B"], units=[150.0, 50.0], revenue=[1500.0, 1000.0]))
        assert b.mix_effect == pytest.approx(-500.0)
        assert b.volume_effect == pytest.approx(0.0, abs=1e-9)
        assert b.price_effect == pytest.approx(0.0, abs=1e-9)


class TestEdgeCases:
    def test_a_launch_is_mix_not_infinite_price(self):
        """A product absent from the base has no price to have changed."""
        current = frame(sku=["A", "B", "NEW"], units=[100.0, 100.0, 40.0],
                        revenue=[1000.0, 2000.0, 800.0])
        b = compute_bridge(BASE, current)
        assert np.isfinite(b.price_effect)
        assert b.explained == pytest.approx(b.total_change, abs=1e-6)

    def test_empty_period_is_refused(self):
        with pytest.raises(BridgeError, match="explains nothing"):
            compute_bridge(BASE, frame(sku=[], units=[], revenue=[]))

    def test_empty_base_is_refused(self):
        with pytest.raises(BridgeError, match="no baseline"):
            compute_bridge(frame(sku=["A"], units=[0.0], revenue=[0.0]), BASE)


@pytest.mark.invariant
class TestContribution:
    """I-18: slices reconcile to the total they are explaining."""

    def _pair(self):
        base = frame(region=["West", "East"], revenue=[1000.0, 1000.0], units=[10.0, 10.0])
        current = frame(region=["West", "East"], revenue=[700.0, 1050.0], units=[7.0, 10.0])
        return base, current

    def test_slices_sum_to_the_total(self):
        c = contribution_by(*self._pair(), dimension="region")
        assert sum(s.delta for s in c.slices) == pytest.approx(c.total_change)
        c.assert_reconciles()

    def test_ranks_the_largest_mover_in_the_movement_direction(self):
        c = contribution_by(*self._pair(), dimension="region")
        assert c.ranked()[0].value == "West"

    def test_a_slice_moving_against_the_trend_is_reported_not_hidden(self):
        c = contribution_by(*self._pair(), dimension="region")
        east = next(s for s in c.slices if s.value == "East")
        assert east.delta > 0 and c.total_change < 0
        assert c.share_of(east) < 0, "an offsetting slice should carry a negative share"

    def test_concentration_reveals_a_localised_problem(self):
        c = contribution_by(*self._pair(), dimension="region")
        assert c.concentration(1) > 1.0, "one slice more than explains a partly offset fall"

    def test_unknown_dimension_is_an_error(self):
        with pytest.raises(KeyError, match="not a dimension"):
            contribution_by(*self._pair(), dimension="planet")
