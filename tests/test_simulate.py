"""Impact scenarios.

The thing worth protecting here is the boundary between a measurement and a
projection. A scenario is allowed to be wrong; it is not allowed to look
derived when it was chosen, or to appear at all when there is nothing behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from whychain.actions.simulate import price_move, rollback, simulate, sustained_external
from whychain.contracts import ContractRegistry
from whychain.evidence import ClaimState

pytestmark = pytest.mark.invariant


@pytest.fixture(scope="module")
def contract():
    return ContractRegistry.from_directory("contracts").get("net_revenue")


@dataclass(frozen=True)
class FakeCandidate:
    candidate_id: str
    kind: str
    description: str = ""
    channel: str | None = None
    device: str | None = None
    category: str | None = None
    exposed_regions: tuple[str, ...] = ("West",)
    start: date = date(2026, 8, 13)
    end: date = date(2026, 8, 16)


@dataclass(frozen=True)
class FakeVerification:
    candidate: FakeCandidate
    state: ClaimState
    effect_pct: float | None = -0.12


def _release(state=ClaimState.VERIFIED):
    return FakeVerification(FakeCandidate("rel-4.05", "release_log"), state)


def _weather(state=ClaimState.VERIFIED):
    return FakeVerification(FakeCandidate("wx-mum", "ops_note"), state)


def test_rollback_recovers_a_share_of_the_measured_loss(contract):
    s = rollback([_release()], {"rel-4.05": -26186.97}, contract)
    assert s.available
    # 90% of the measured loss, and both halves are visible as assumptions.
    assert s.effect_inr_per_day == pytest.approx(26186.97 * 0.90)
    names = {a.name for a in s.assumptions}
    assert "measured daily loss" in names
    assert "share recovered by a rollback" in names


def test_rollback_declines_when_no_release_survived_testing(contract):
    """A rejected cause is not something to roll back."""
    s = rollback([_release(ClaimState.REJECTED)], {"rel-4.05": -26186.97}, contract)
    assert not s.available
    assert s.effect_inr_per_day is None
    assert "survived causal testing" in s.unavailable_because


def test_price_move_uses_the_contract_elasticity(contract):
    """The coefficient must be the declared one, not a plausible one."""
    prior = next(d for d in contract.drivers if d.id == "unit_price").elasticity_prior
    s = price_move(contract, 100_000.0, -0.05)
    expected = 100_000.0 * ((1 - 0.05) * (1 + prior * -0.05) - 1)
    assert s.effect_inr_per_day == pytest.approx(expected)
    assert any(f"{prior:+.2f}" in a.value for a in s.assumptions)


def test_price_move_declines_when_the_contract_declares_no_elasticity(contract):
    """Borrowing an elasticity would make a chosen number look derived."""
    bare = contract.model_copy(update={
        "drivers": tuple(
            replace_driver(d) if d.id == "unit_price" else d for d in contract.drivers
        )
    })
    s = price_move(bare, 100_000.0, -0.05)
    assert not s.available
    assert "no price elasticity" in s.unavailable_because


def replace_driver(driver):
    return driver.model_copy(update={"elasticity_prior": None})


def test_a_price_cut_can_raise_revenue_only_when_demand_is_elastic(contract):
    """Sanity on the arithmetic, in the direction a reader would check.

    At elasticity -1.4 a 5% cut sells enough extra units to more than pay for
    itself; at -0.5 it does not. If the sign does not flip with elasticity the
    formula is not doing what it claims.
    """
    elastic = price_move(contract, 100_000.0, -0.05).effect_inr_per_day
    inelastic_contract = contract.model_copy(update={
        "drivers": tuple(
            d.model_copy(update={"elasticity_prior": -0.5}) if d.id == "unit_price" else d
            for d in contract.drivers
        )
    })
    inelastic = price_move(inelastic_contract, 100_000.0, -0.05).effect_inr_per_day
    assert elastic > 0 > inelastic


def test_sustained_external_projects_a_measured_rate_and_says_it_does_not_decay():
    s = sustained_external([_weather()], {"wx-mum": -15943.19}, 14)
    assert s.effect_inr_total == pytest.approx(-15943.19 * 14)
    decay = next(a for a in s.assumptions if a.name == "decay")
    assert decay.value == "none"


def test_every_scenario_is_labelled_an_estimate_never_a_fact(contract):
    """A projection must never be presentable as a measurement."""
    scenarios = simulate(
        [_release(), _weather()],
        {"rel-4.05": -26186.97, "wx-mum": -15943.19},
        contract, base_revenue_per_day=238_000.0,
    )
    assert scenarios
    for s in scenarios:
        assert s.kind == "scenario_estimate"


def test_an_unavailable_scenario_carries_a_reason_not_a_zero(contract):
    """Zero is a number a reader would act on. Absence is not."""
    scenarios = simulate([], {}, contract, base_revenue_per_day=238_000.0)
    unavailable = [s for s in scenarios if not s.available]
    assert unavailable
    for s in unavailable:
        assert s.effect_inr_per_day is None
        assert s.unavailable_because


def test_available_scenarios_always_state_their_assumptions(contract):
    scenarios = simulate(
        [_release(), _weather()],
        {"rel-4.05": -26186.97, "wx-mum": -15943.19},
        contract, base_revenue_per_day=238_000.0,
    )
    for s in scenarios:
        if s.available:
            assert s.assumptions, f"{s.scenario_id} projects with nothing stated"
            assert all(a.basis for a in s.assumptions)
