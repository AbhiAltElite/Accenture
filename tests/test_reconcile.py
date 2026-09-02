"""Two systems, one quantity, and what happens when they disagree.

The brief asks separately for reconciliation across heterogeneous sources and
for abstention on **contradictory** evidence, and those were being answered by
the same thing. Reconciling grain is a shape problem. Contradiction needs two
independent postings of one number, and there was nothing here capable of
producing one until `finance_ledger` existed.

The tests that matter most are the ones about the middle: a threshold that
treats an ordinary posting-policy gap as a fault gets switched off in a week,
and a threshold that lets a broken extract through is worse than not having one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from whychain.contracts import ContractRegistry
from whychain.reconcile import Agreement, reconcile

CONTRACTS = Path("contracts")


@pytest.fixture(scope="module")
def contract():
    return ContractRegistry.from_directory(CONTRACTS).get("net_revenue")


def series(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"d": list(values), "value": list(values.values())}
    )


def ledger(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"business_date": list(values), "net_revenue_posted": list(values.values())}
    )


WINDOW = (date(2026, 6, 10), date(2026, 6, 12))
DAYS = ["2026-06-10", "2026-06-11", "2026-06-12"]


class TestTheThreeStates:
    def test_a_posting_policy_gap_is_not_a_fault(self, contract):
        """Two systems that post the same trade differently are never identical.

        Equality is the wrong test, and any threshold treating a 2% gap as a
        breach will be switched off within a week of a deployment.
        """
        r = reconcile(
            contract,
            series(dict.fromkeys(DAYS, 102_000.0)),
            ledger(dict.fromkeys(DAYS, 100_000.0)),
            window=WINDOW,
        )
        assert r.state is Agreement.AGREED
        assert not r.blocks_diagnosis

    def test_further_apart_than_policy_explains_is_drift(self, contract):
        """Lowers confidence, says so, stops nothing."""
        r = reconcile(
            contract,
            series({**dict.fromkeys(DAYS, 100_000.0), "2026-06-11": 108_000.0}),
            ledger(dict.fromkeys(DAYS, 100_000.0)),
            window=WINDOW,
        )
        assert r.state is Agreement.DRIFT
        assert not r.blocks_diagnosis
        assert r.breaches

    def test_far_enough_apart_is_a_contradiction(self, contract):
        r = reconcile(
            contract,
            series(dict.fromkeys(DAYS, 60_000.0)),
            ledger(dict.fromkeys(DAYS, 100_000.0)),
            window=WINDOW,
        )
        assert r.state is Agreement.CONTRADICTED
        assert r.blocks_diagnosis
        assert "in question" in r.reason

    def test_no_second_system_is_not_the_same_as_agreement(self, contract):
        """"Nobody checked" and "two systems checked and concur" are different
        states, and only one of them is reassuring."""
        bare = contract.model_copy(update={
            "reconciliation": contract.reconciliation.model_copy(
                update={"source": None, "compare_column": None}
            )
        })
        r = reconcile(bare, series(dict.fromkeys(DAYS, 100_000.0)), None, window=WINDOW)
        assert r.state is Agreement.NOT_RECONCILED
        assert not r.blocks_diagnosis
        assert "not the same as" in r.reason


class TestItIsScopedToTheQuestion:
    def test_a_breach_outside_the_window_is_not_this_window_s_problem(self, contract):
        """A feed that broke in March is not a reason to refuse August."""
        days = [*DAYS, "2026-07-01"]
        r = reconcile(
            contract,
            series({**dict.fromkeys(DAYS, 100_000.0), "2026-07-01": 10_000.0}),
            ledger(dict.fromkeys(days, 100_000.0)),
            window=WINDOW,
        )
        assert r.state is Agreement.AGREED
        assert len(r.days) == 3

    def test_no_overlapping_days_is_reported_rather_than_assumed_clean(self, contract):
        r = reconcile(
            contract,
            series(dict.fromkeys(DAYS, 100_000.0)),
            ledger({"2026-01-01": 100_000.0}),
            window=WINDOW,
        )
        assert r.state is Agreement.NOT_RECONCILED
        assert "nothing to compare" in r.reason


@pytest.mark.invariant
class TestAgainstTheGeneratedWarehouse:
    """The planted feed break, end to end. Skipped without a warehouse."""

    @pytest.fixture(scope="class")
    def world(self):
        pytest.importorskip("duckdb")
        if not Path("data/warehouse/whychain.duckdb").exists():
            pytest.skip("run `make gen` first")
        from whychain.ingest import Warehouse
        reg = ContractRegistry.from_directory(CONTRACTS)
        c = reg.get("net_revenue")
        with Warehouse() as w:
            raw = w.kpi_series(c)
            led = w.table("finance_ledger")
        return c, raw, led

    def _for(self, world, region, lo, hi):
        c, raw, led = world
        scoped = raw[raw["region"] == region]
        day = scoped.groupby(scoped.columns[0], as_index=False)["value"].sum()
        day.columns = ["d", "value"]
        return reconcile(c, day, led[led["region"] == region], window=(lo, hi))

    def test_the_planted_break_is_contradicted(self, world):
        """A movement that is large, clean, regionally specific and false.

        Every stage below reconciliation would pass on it: the series really
        does fall, the slice really is missing, and the fall really is isolated.
        Only a second system can catch this.
        """
        r = self._for(world, "North", date(2026, 6, 10), date(2026, 6, 12))
        assert r.state is Agreement.CONTRADICTED
        assert r.worst_residual > 0.3

    def test_an_ordinary_window_reconciles(self, world):
        """The other half of the claim. A check that only ever fires is not a
        check, it is a banner."""
        r = self._for(world, "West", date(2026, 8, 13), date(2026, 8, 16))
        assert r.state is Agreement.AGREED

    def test_the_tolerance_is_calibrated_not_guessed(self, world):
        """Ordinary windows must sit inside it, or the state means nothing.

        This is the test that caught the ledger skipping `tz_normalise`. One
        region's extract lands in local time and the contract corrects it; a
        ledger built from the raw timestamps buckets that region's evening into
        the wrong business date and disagrees permanently. North, South and West
        agreed on every window and East on none of them -- a failure that is
        consistent, localised and entirely plausible, which is the hardest kind
        to notice from a summary statistic.
        """
        from datetime import timedelta

        states: dict[str, int] = {}
        start = date(2025, 1, 6)
        while start < date(2026, 8, 20):
            for region in ("North", "South", "East", "West"):
                window = (start, start + timedelta(days=6))
                # Skip the planted break; it is the subject of its own test.
                if region == "North" and window[0] <= date(2026, 6, 12) <= window[1]:
                    continue
                state = self._for(world, region, *window).state.value
                states[state] = states.get(state, 0) + 1
            start += timedelta(days=14)

        total = sum(states.values())
        assert total > 100, "not enough windows sampled to mean anything"
        assert states.get("contradicted", 0) == 0, (
            f"{states.get('contradicted')} of {total} ordinary windows were "
            f"reported as contradicted; the tolerance is not calibrated"
        )
        assert states.get("agreed", 0) / total > 0.95, states
