"""The benchmark population has to be able to fail the engine.

A generator bug is the worst kind of measurement bug, because the numbers it
produces look like results. The first version of `CAUSE_PROFILES` planted
effects too small to clear regional materiality, so 152 of 160 cases had
nothing worth explaining and top-1 accuracy read 2.9%. Nothing was wrong with
the engine. The benchmark was reporting on the generator.

These tests assert the arithmetic that the comment above `CAUSE_PROFILES`
claims, against the panel that is actually generated rather than against the
shares that were assumed when the table was written. A change to the catalog
that shrinks a slice now fails here instead of quietly depressing the headline
number six months later.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from datagen.bulk import (
    CAUSE_PROFILES,
    DECOY_SHARE,
    EVENT_LENGTH,
    LOOKBACK_DAYS,
    NOISE_SHARE,
    build_cases,
)
from datagen.scenarios import ExpectedVerdict
from whychain.contracts import ContractRegistry

WAREHOUSE = Path("data/warehouse/whychain.duckdb")


@pytest.fixture(scope="module")
def panel():
    duckdb = pytest.importorskip("duckdb")
    if not WAREHOUSE.exists():
        pytest.skip("run `make gen` first")
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return con.execute(
            "SELECT region, channel, device, category, revenue FROM _panel"
        ).fetchdf()


@pytest.fixture(scope="module")
def region_day(panel):
    """Mean revenue for one region on one day, which is what materiality is judged against."""
    duckdb = pytest.importorskip("duckdb")
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return float(
            con.execute(
                "SELECT avg(r) FROM (SELECT d, region, sum(revenue) r "
                "FROM _panel GROUP BY 1, 2)"
            ).fetchone()[0]
        )


@pytest.fixture(scope="module")
def contract():
    return ContractRegistry.from_directory("contracts").get("net_revenue")


def _share(panel, scope: dict) -> float:
    """What fraction of regional revenue this scope carries, measured not assumed."""
    mask = None
    for column, value in scope.items():
        column_mask = panel[column] == value
        mask = column_mask if mask is None else (mask & column_mask)
    return float(panel.loc[mask, "revenue"].sum() / panel["revenue"].sum())


class TestPlantedEffectsAreWorthExplaining:
    @pytest.mark.invariant
    @pytest.mark.parametrize("profile", CAUSE_PROFILES, ids=lambda p: f"{p[0].value}-{p[2]}")
    def test_the_weakest_effect_still_clears_the_rupee_floor(
        self, profile, panel, region_day, contract
    ):
        """Every profile's *floor*, not its midpoint, must be material.

        Testing the midpoint would let half of each profile's cases fall below
        the threshold and still pass, which is exactly the state this file
        exists to prevent.
        """
        kind, (low, high), scope = profile
        floor = max(abs(low), abs(high)) and min(abs(low), abs(high))
        share = _share(panel, scope)
        movement = region_day * share * floor

        assert movement >= contract.materiality.min_abs_delta_inr, (
            f"{kind.value} on {scope} moves at most {movement:,.0f} rupees a day "
            f"at its weakest ({floor:.0%} of a slice carrying {share:.1%} of a "
            f"{region_day:,.0f} rupee region-day), under the "
            f"{contract.materiality.min_abs_delta_inr:,.0f} floor. Widen the "
            f"slice or raise the effect; do not lower the floor (BUGS.md T-14)"
        )

    def test_no_profile_plants_an_implausible_wipeout(self):
        """A slice cannot lose more than all of itself, and an effect near that
        is a generator straining to beat a threshold rather than a scenario."""
        for kind, (low, _), scope in CAUSE_PROFILES:
            assert abs(low) < 0.85, (
                f"{kind.value} on {scope} plants a {abs(low):.0%} fall, which is "
                "close enough to a total wipeout to read as fitted to the test"
            )

    def test_slices_are_measured_not_assumed(self, panel):
        """Each profile's scope has to exist in the data it is planted into."""
        for kind, _, scope in CAUSE_PROFILES:
            share = _share(panel, scope)
            assert share > 0, f"{kind.value} targets {scope}, which is empty"


class TestThePopulationIsBalanced:
    def test_the_mix_is_what_the_shares_declare(self):
        panels = build_cases()
        cases = [c for p in panels for c in p.cases]
        noise = sum(1 for c in cases if c.expected is ExpectedVerdict.NO_ANOMALY)
        decoyed = sum(1 for c in cases if c.decoys)

        assert cases, "the generator produced no cases"
        # Wide tolerance: this asserts the shares are honoured, not that a
        # random draw hit them exactly.
        assert abs(noise / len(cases) - NOISE_SHARE) < 0.06
        assert abs(decoyed / len(cases) - DECOY_SHARE) < 0.10

    def test_noise_cases_carry_no_planted_cause(self):
        """A case whose correct answer is silence must have nothing to find."""
        for panel in build_cases():
            for case in panel.cases:
                if case.expected is ExpectedVerdict.NO_ANOMALY:
                    assert not case.true_causes
                    assert not case.decoys

    @pytest.mark.invariant
    def test_decoys_carry_no_effect(self):
        """A decoy that moved the metric would be a cause, and the
        negative-control rejection rate would be measuring nothing."""
        for panel in build_cases():
            for event in panel.events:
                if event.is_decoy:
                    assert event.effect == 0.0

    @pytest.mark.invariant
    def test_events_do_not_contaminate_each_others_baselines(self):
        """The invariant the module docstring rests its whole design on.

        Verification looks back `LOOKBACK_DAYS` for its baseline and its six
        placebo windows. Two events inside that span in one region each sit in
        the other's control period, so both measurements are of the pair rather
        than of either. A benchmark built on such cases reports the
        contamination, which is worse than reporting nothing.
        """
        clearance = LOOKBACK_DAYS + max(EVENT_LENGTH)
        for panel in build_cases():
            by_region: dict[str, list] = {}
            for case in panel.cases:
                by_region.setdefault(case.region, []).append(case)
            for region, cases in by_region.items():
                starts = sorted(c.window_start for c in cases)
                gaps = [(b - a).days for a, b in pairwise(starts)]
                assert all(g >= clearance for g in gaps), (
                    f"{region} has events {min(gaps)} days apart, inside the "
                    f"{clearance} each one needs for a clean baseline"
                )
