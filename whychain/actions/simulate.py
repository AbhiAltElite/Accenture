"""What would happen if we did something about it.

A diagnosis says what moved and why. The next question a reader asks is what
happens if they act, and it is a different kind of question: everything above
this module is a measurement of something that already happened, and everything
here is a projection of something that has not.

That line is the whole design. Each scenario is arithmetic over a quantity the
engine already measured or a coefficient the contract already declares, it
carries its assumptions as data rather than burying them in a formula, and it is
labelled `scenario_estimate` and never `causal_fact`. A reader who wants to
disagree can see exactly which number to argue with.

Three refusals:

- A scenario with no measured quantity behind it is not offered. There is no
  "what if we improved conversion by 10%" here, because nothing in the record
  says what that would take or cost.
- A scenario whose coefficient the contract does not declare returns unavailable
  rather than borrowing a plausible one.
- Nothing here is presented as a forecast with a confidence. These are single
  points under stated assumptions, and the assumptions are the output.
"""

from __future__ import annotations

from dataclasses import dataclass

# How much of a measured loss reversing the cause recovers, per lever. Shared
# with the decision card so a card and a scenario cannot disagree about the same
# action.
from whychain.actions.recovery import RECOVERY_SHARE
from whychain.contracts import KPIContract
from whychain.evidence import ClaimState


@dataclass(frozen=True)
class Assumption:
    """One input a scenario rests on, stated so it can be argued with."""

    name: str
    value: str
    basis: str

    def as_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "basis": self.basis}


@dataclass(frozen=True)
class Scenario:
    """A projection, explicitly not a measurement."""

    scenario_id: str
    question: str
    available: bool
    effect_inr_per_day: float | None
    effect_inr_total: float | None
    horizon_days: int | None
    assumptions: tuple[Assumption, ...]
    bounded_by: str | None = None
    unavailable_because: str | None = None
    kind: str = "scenario_estimate"

    def as_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "question": self.question,
            "available": self.available,
            "kind": self.kind,
            "effect_inr_per_day": (
                round(self.effect_inr_per_day, 2)
                if self.effect_inr_per_day is not None else None
            ),
            "effect_inr_total": (
                round(self.effect_inr_total, 2)
                if self.effect_inr_total is not None else None
            ),
            "horizon_days": self.horizon_days,
            "assumptions": [a.as_dict() for a in self.assumptions],
            "bounded_by": self.bounded_by,
            "unavailable_because": self.unavailable_because,
        }


def _driver(contract: KPIContract, driver_id: str):
    return next((d for d in contract.drivers if d.id == driver_id), None)


def rollback(verifications, per_cause: dict[str, float], contract: KPIContract) -> Scenario:
    """Reverse a verified internal cause.

    The recoverable amount is the movement difference-in-differences attributed
    to that cause, times the share the lever is assumed to recover. Both halves
    are visible: the first was measured, the second is an assumption.
    """
    target = next(
        (v for v in verifications
         if v.state is ClaimState.VERIFIED
         and (_driver(contract, "release_quality") is not None)
         and v.candidate.kind == "release_log"),
        None,
    )
    question = "What happens if we roll the release back now?"
    if target is None:
        return Scenario(
            "rollback", question, False, None, None, None, (),
            unavailable_because=(
                "no shipped release survived causal testing in this window, so "
                "there is nothing measured to roll back"
            ),
        )

    loss = abs(per_cause.get(target.candidate.candidate_id, 0.0))
    share = RECOVERY_SHARE["release_rollback"]
    return Scenario(
        "rollback", question, True, loss * share, None, None,
        (
            Assumption(
                "measured daily loss", f"{loss:,.0f} INR/day",
                f"difference-in-differences on {target.candidate.candidate_id}, "
                f"effect {target.effect_pct:+.1%}",
            ),
            Assumption(
                "share recovered by a rollback", f"{share:.0%}",
                "declared per lever in whychain/actions/recovery.py; a rollback "
                "restores the prior build but not the orders already lost",
            ),
        ),
        bounded_by="the movement this cause was measured to account for",
    )


def price_move(
    contract: KPIContract, base_revenue_per_day: float, delta_pct: float
) -> Scenario:
    """Move list price by `delta_pct` and let the contract's elasticity respond.

        revenue = price x quantity
        price'  = price (1 + d)
        qty'    = qty (1 + e d)
        change  = revenue [ (1 + d)(1 + e d) - 1 ]

    The elasticity is the contract's declared prior, not a fitted value, so this
    is a planning estimate and the assumption says as much.
    """
    question = f"What happens if we move price by {delta_pct:+.0%} on this slice?"
    driver = _driver(contract, "unit_price")
    if driver is None or driver.elasticity_prior is None:
        return Scenario(
            "price_move", question, False, None, None, None, (),
            unavailable_because=(
                "the contract declares no price elasticity for this metric, and "
                "borrowing one from elsewhere would make the number look "
                "derived when it was chosen"
            ),
        )

    e = driver.elasticity_prior
    change = base_revenue_per_day * ((1 + delta_pct) * (1 + e * delta_pct) - 1)
    return Scenario(
        "price_move", question, True, change, None, None,
        (
            Assumption("current revenue", f"{base_revenue_per_day:,.0f} INR/day",
                       "observed over the event window"),
            Assumption("price elasticity", f"{e:+.2f}",
                       f"elasticity_prior declared on the {driver.id} driver in "
                       f"{contract.kpi_id}.yml, version {contract.version}"),
            Assumption("price change applied", f"{delta_pct:+.0%}",
                       "the scenario input"),
        ),
        bounded_by=(
            "a single-period elasticity: it does not model competitor response, "
            "and it is unreliable far outside the range prices have actually moved"
        ),
    )


def sustained_external(
    verifications, per_cause: dict[str, float], horizon_days: int
) -> Scenario:
    """Carry a verified external effect forward at its measured rate.

    This projects a measured daily effect across a horizon and does nothing else.
    It assumes the effect neither decays nor compounds, which is stated, because
    over a fortnight that assumption is doing most of the work.
    """
    question = (
        f"What happens if the external pressure persists for {horizon_days} days?"
    )
    external = [
        v for v in verifications
        if v.state is ClaimState.VERIFIED and v.candidate.kind in ("ops_note", "promotion")
    ]
    if not external:
        return Scenario(
            "sustained_external", question, False, None, None, horizon_days, (),
            unavailable_because=(
                "no external cause survived causal testing in this window, so "
                "there is no measured rate to carry forward"
            ),
        )

    daily = sum(abs(per_cause.get(v.candidate.candidate_id, 0.0)) for v in external)
    return Scenario(
        "sustained_external", question, True, -daily, -daily * horizon_days,
        horizon_days,
        (
            Assumption("measured daily effect", f"{daily:,.0f} INR/day",
                       "sum of the verified external causes' attributed movement"),
            Assumption("decay", "none",
                       "the effect is held flat across the horizon; a real one "
                       "usually fades, so this is the pessimistic end"),
            Assumption("horizon", f"{horizon_days} days", "the scenario input"),
        ),
        bounded_by="a straight-line projection of an effect measured over a few days",
    )


def simulate(
    verifications,
    per_cause: dict[str, float],
    contract: KPIContract,
    *,
    base_revenue_per_day: float,
    price_delta: float = -0.05,
    horizon_days: int = 14,
) -> list[Scenario]:
    """Every scenario this diagnosis can support, including the ones it cannot."""
    return [
        rollback(verifications, per_cause, contract),
        price_move(contract, base_revenue_per_day, price_delta),
        sustained_external(verifications, per_cause, horizon_days),
    ]


__all__ = [
    "Assumption",
    "Scenario",
    "price_move",
    "rollback",
    "simulate",
    "sustained_external",
]
