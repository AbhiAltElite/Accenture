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
from whychain.actions.recovery import RETAIL_RECOVERY, RecoveryModel
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
    # What `effect_inr_per_day` is a quantity *of*. Every scenario here used to
    # report revenue and say so nowhere, which is safe until one of them has a
    # reason to report something else.
    effect_of: str = "revenue"
    # Figures the headline must be read against rather than instead of. A price
    # move has two, and showing one is how a reader is talked into it.
    alongside: tuple[tuple[str, float], ...] = ()

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
            "effect_of": self.effect_of,
            "alongside": [
                {"name": n, "inr_per_day": round(v, 2)} for n, v in self.alongside
            ],
            "assumptions": [a.as_dict() for a in self.assumptions],
            "bounded_by": self.bounded_by,
            "unavailable_because": self.unavailable_because,
        }


def _driver(contract: KPIContract, driver_id: str):
    return next((d for d in contract.drivers if d.id == driver_id), None)


def rollback(
    verifications,
    per_cause: dict[str, float],
    contract: KPIContract,
    recovery: RecoveryModel = RETAIL_RECOVERY,
) -> Scenario:
    """Reverse the one verified cause this industry can undo.

    The recoverable amount is the movement difference-in-differences attributed
    to that cause, times the share the lever is assumed to recover. Both halves
    are visible: the first was measured, the second is an assumption.

    Which cause is reversible is a fact about the industry. Retail can roll a
    release back; a fuel marketer can source a shortfall from another refinery;
    a generator can bring a unit back on bar. The arithmetic is the same and the
    words are not, which is why they come off the recovery model.
    """
    target = next(
        (v for v in verifications
         if v.state is ClaimState.VERIFIED
         and (_driver(contract, recovery.reversal_driver) is not None)
         and v.candidate.kind == recovery.reversal_kind),
        None,
    )
    question = recovery.reversal_question
    if target is None:
        return Scenario(
            recovery.reversal_id, question, False, None, None, None, (),
            unavailable_because=recovery.reversal_absent,
        )

    loss = abs(per_cause.get(target.candidate.candidate_id, 0.0))
    share = recovery.share_for(recovery.reversal_lever)
    if share is None:
        return Scenario(
            recovery.reversal_id, question, False, None, None, None, (),
            unavailable_because=(
                f"the {recovery.reversal_lever!r} lever has no declared recovery "
                f"share, and choosing one here would make the number look "
                f"derived when it was invented"
            ),
        )
    return Scenario(
        recovery.reversal_id, question, True, loss * share, None, None,
        (
            Assumption(
                "measured daily loss", f"{loss:,.0f} INR/day",
                f"difference-in-differences on {target.candidate.candidate_id}, "
                f"effect {target.effect_pct:+.1%}",
            ),
            Assumption(
                "share recovered", f"{share:.0%}",
                f"declared per lever in whychain/actions/recovery.py; "
                f"{recovery.reversal_caveat}",
            ),
        ),
        bounded_by="the movement this cause was measured to account for",
    )


def price_move(
    contract: KPIContract,
    base_revenue_per_day: float,
    delta_pct: float,
    recovery: RecoveryModel = RETAIL_RECOVERY,
) -> Scenario:
    """Move list price by `delta_pct` and let the contract's elasticity respond.

        revenue = price x quantity
        price'  = price (1 + d)
        qty'    = qty (1 + e d)
        change  = revenue [ (1 + d)(1 + e d) - 1 ]

    The elasticity is the contract's declared prior, not a fitted value, so this
    is a planning estimate and the assumption says as much.

    **Revenue is not the number this decides on.** Below an elasticity of -1 a
    price cut raises revenue and lowers gross profit at the same time, and this
    scenario used to report only the first: on retail's -1.4 it offered a finance
    director "+₹10,373 per day" for a move that costs about twice that in gross
    profit. Nothing was miscalculated -- it was the half of the arithmetic that
    argues for the decision, presented as the result of it, which is a
    better-evidenced version of exactly the failure this engine exists to
    prevent.

    So where the contract declares a margin, gross profit is the headline and
    revenue is shown beside it:

        gp'    = R (1 + e d) [(1 + d) - (1 - m)]
        change = gp' - R m

    with unit cost held constant, which is the assumption doing the work. Where
    no margin is declared the revenue figure still stands, and the scenario says
    in the open that it cannot tell whether the move is worth making.
    """
    question = (
        f"What happens if we move {recovery.price_noun} by {delta_pct:+.0%} "
        f"on this slice?"
    )
    driver = _driver(contract, recovery.price_driver)
    if driver is None or driver.elasticity_prior is None:
        return Scenario(
            "price_move", question, False, None, None, None, (),
            unavailable_because=(
                f"the contract declares no price elasticity on "
                f"{recovery.price_driver!r} for this metric, and borrowing one "
                f"from elsewhere would make the number look derived when it was "
                f"chosen"
            ),
        )

    e = driver.elasticity_prior
    d = delta_pct
    volume = 1 + e * d
    revenue_change = base_revenue_per_day * ((1 + d) * volume - 1)
    margin = contract.economics.gross_margin_pct

    assumptions = [
        Assumption("current revenue", f"{base_revenue_per_day:,.0f} INR/day",
                   "observed over the event window"),
        Assumption("price elasticity", f"{e:+.2f}",
                   f"elasticity_prior declared on the {driver.id} driver in "
                   f"{contract.kpi_id}.yml, version {contract.version}"),
        Assumption(f"{recovery.price_noun} change applied", f"{d:+.0%}",
                   "the scenario input"),
    ]

    if margin is None:
        return Scenario(
            "price_move", question, True, revenue_change, None, None,
            tuple(assumptions),
            effect_of="revenue",
            bounded_by=(
                "a single-period elasticity: it does not model competitor "
                "response, and it is unreliable far outside the range prices "
                "have actually moved. It is also revenue alone: this contract "
                "declares no gross_margin_pct, so whether the move earns or "
                "costs money is not a question this figure answers"
            ),
        )

    # Unit cost is held at its current level, so the whole of a price move lands
    # on the margin. That is the assumption doing the work here and it is stated
    # rather than folded into the formula.
    gross_profit_change = (
        base_revenue_per_day * volume * ((1 + d) - (1 - margin))
        - base_revenue_per_day * margin
    )
    assumptions.append(
        Assumption("gross margin", f"{margin:.0%}",
                   f"gross_margin_pct declared in {contract.kpi_id}.yml, version "
                   f"{contract.version}; a business-owned input, not a measured "
                   f"one -- no cost column exists in the source")
    )

    below_cost = (1 + d) < (1 - margin)
    return Scenario(
        "price_move", question, True, gross_profit_change, None, None,
        tuple(assumptions),
        effect_of="gross profit",
        alongside=(("revenue", revenue_change),),
        bounded_by=(
            "a single-period elasticity, holding unit cost constant: it does "
            "not model competitor response, and it is unreliable far outside "
            "the range prices have actually moved"
            + (". At this size the price falls below unit cost, so every "
               "additional unit sold loses money and the elasticity stops "
               "being the relevant question" if below_cost else "")
        ),
    )


def sustained_external(
    verifications,
    per_cause: dict[str, float],
    horizon_days: int,
    recovery: RecoveryModel = RETAIL_RECOVERY,
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
        if v.state is ClaimState.VERIFIED and v.candidate.kind in recovery.external_kinds
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
    recovery: RecoveryModel = RETAIL_RECOVERY,
) -> list[Scenario]:
    """Every scenario this diagnosis can support, including the ones it cannot."""
    return [
        rollback(verifications, per_cause, contract, recovery),
        price_move(contract, base_revenue_per_day, price_delta, recovery),
        sustained_external(verifications, per_cause, horizon_days, recovery),
    ]


__all__ = [
    "Assumption",
    "Scenario",
    "price_move",
    "rollback",
    "simulate",
    "sustained_external",
]
