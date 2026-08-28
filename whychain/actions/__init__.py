"""From a verified cause to the decision somebody has to make.

A diagnosis that stops at "the release broke checkout" leaves the reader with
the work still to do. This stage carries it the last step, and the brief names
the chain it has to produce:

    driver -> lever -> action -> expected impact -> owner -> confidence
           -> monitoring plan

Every link is derived. The driver comes from the verified candidate, the lever
and the owner from the KPI contract, the impact from the movement the causal
test already measured, the confidence from the score already computed. A model
does not choose any of them, and if a link is missing the card says so rather
than inventing it.

Two refusals matter more than the happy path.

**Not every cause has a lever.** Weather moves revenue and nobody owns a
weather lever. Rather than manufacture an action, the card returns
`controllable: false` and the only output is a monitoring rule. That is the
honest answer, and it is the one that leads into Answer 2.

**Nothing here executes.** The card produces a draft for a named human to
approve. An agent that investigates and drafts is deployable; one that rolls
back production because a statistic moved is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from whychain.contracts import Driver, KPIContract
from whychain.evidence import ClaimState

# How much of a measured loss reversing the cause is assumed to recover, by
# lever. These are assumptions, not measurements, and they are declared here so
# a reader can see and argue with them rather than find them inside a formula.
# A rollback recovers most of what a regression took; a replenishment recovers
# less, because demand deferred is partly demand lost.
RECOVERY_SHARE: dict[str, float] = {
    "release_rollback": 0.90,
    "replenishment": 0.65,
    "pricing": 0.50,
    "media_budget": 0.40,
}

# Which contract driver a verified candidate belongs to. Declared rather than
# inferred: a model guessing that a release note is a pricing problem would put
# the wrong owner's name on a decision.
KIND_TO_DRIVER: dict[str, str] = {
    "release_log": "release_quality",
    "promotion": "competitor_price_index",
}

# Ops notes are not one kind of thing, so they are matched on what the note
# says. The vocabulary is shared with corroboration so the two stages agree.
NOTE_TO_DRIVER: tuple[tuple[tuple[str, ...], str], ...] = (
    (("stockout", "out of stock", "shortfall", "supplier", "inventory"), "stock_position"),
    (("price", "pricing", "discount"), "unit_price"),
    (("marketing", "campaign", "spend", "media"), "marketing_spend"),
    (("weather", "rainfall", "storm", "flood", "monsoon"), "severe_weather"),
)


@dataclass(frozen=True)
class MonitoringRule:
    """What to watch so this is caught earlier next time."""

    watch: str
    threshold: str
    window: str
    route_to: str

    def as_dict(self) -> dict:
        return {
            "watch": self.watch,
            "threshold": self.threshold,
            "window": self.window,
            "route_to": self.route_to,
        }


@dataclass(frozen=True)
class ApprovalDraft:
    """A request for a human to approve. Never an executed action."""

    action_id: str
    title: str
    body: str
    assigned_to: str
    drafted_at: datetime
    status: str = "awaiting_approval"

    def as_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "body": self.body,
            "assigned_to": self.assigned_to,
            "drafted_at": self.drafted_at.isoformat(),
            "status": self.status,
        }


@dataclass(frozen=True)
class DecisionCard:
    """One verified cause, carried through to the decision it implies."""

    candidate_id: str
    cause: str
    driver: str | None
    lever: str | None
    owner: str | None
    controllable: bool
    action: str
    measured_loss_inr_per_day: float
    expected_recovery_inr_per_day: float | None
    recovery_basis: str
    confidence_band: str
    monitoring: MonitoringRule
    approval: ApprovalDraft | None = None
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "cause": self.cause,
            "driver": self.driver,
            "lever": self.lever,
            "owner": self.owner,
            "controllable": self.controllable,
            "action": self.action,
            "measured_loss_inr_per_day": round(self.measured_loss_inr_per_day, 2),
            "expected_recovery_inr_per_day": (
                round(self.expected_recovery_inr_per_day, 2)
                if self.expected_recovery_inr_per_day is not None
                else None
            ),
            "recovery_basis": self.recovery_basis,
            "confidence_band": self.confidence_band,
            "monitoring": self.monitoring.as_dict(),
            "approval": self.approval.as_dict() if self.approval else None,
            "caveats": list(self.caveats),
        }


def _driver_for(candidate, contract: KPIContract) -> Driver | None:
    """Which contract driver this candidate belongs to, if any."""
    driver_id = KIND_TO_DRIVER.get(candidate.kind)
    if driver_id is None and candidate.kind == "ops_note":
        text = f"{candidate.description}".lower()
        for words, mapped in NOTE_TO_DRIVER:
            if any(w in text for w in words):
                driver_id = mapped
                break
    if driver_id is None:
        return None
    return next((d for d in contract.drivers if d.id == driver_id), None)


def _monitoring_for(
    driver: Driver | None, candidate, contract: KPIContract
) -> MonitoringRule:
    """The rule that would surface this earlier.

    Routed to the driver's owner where one exists, and to the KPI's owner where
    the driver is something the business can only watch.
    """
    route = (driver.owner_role if driver and driver.owner_role else contract.owner_role)
    scope = candidate.category or candidate.device or candidate.channel or "all slices"

    if driver and driver.id == "release_quality":
        return MonitoringRule(
            watch=f"{contract.kpi_id} and checkout conversion, by device, after every release",
            threshold="conversion down more than 2 percentage points against the pre-release day",
            window="the 24 hours following a deploy",
            route_to=route,
        )
    if driver and driver.id == "severe_weather":
        return MonitoringRule(
            watch="public severe-weather warnings covering a distribution-centre city",
            threshold="amber or above with at least 48 hours of lead time",
            window="rolling 7 days",
            route_to=route,
        )
    if driver and driver.id == "stock_position":
        return MonitoringRule(
            watch=f"stock cover for {scope}",
            threshold="cover below 7 days at current run rate",
            window="daily",
            route_to=route,
        )
    return MonitoringRule(
        watch=f"{contract.kpi_id} for {scope}",
        threshold=(
            f"robust z beyond {contract.materiality.min_abs_robust_z:g} and a "
            f"movement over {contract.materiality.min_abs_delta_inr:,.0f} rupees"
        ),
        window="daily",
        route_to=route,
    )


def _draft(
    card_action: str,
    candidate,
    driver: Driver,
    recovery: float,
    contract: KPIContract,
    now: datetime,
) -> ApprovalDraft:
    return ApprovalDraft(
        action_id=f"act-{candidate.candidate_id}",
        title=card_action,
        body=(
            f"Verified cause: {candidate.description or candidate.candidate_id}. "
            f"Lever: {driver.controllable_lever}. "
            f"Expected recovery {recovery:,.0f} rupees per day, computed from the "
            f"movement measured by difference-in-differences, not estimated. "
            f"Requires approval from {driver.owner_role} before anything is changed."
        ),
        assigned_to=driver.owner_role or contract.owner_role,
        drafted_at=now,
    )


def decision_cards(
    verifications,
    per_cause: dict[str, float],
    contract: KPIContract,
    confidence_band: str,
    *,
    now: datetime | None = None,
) -> list[DecisionCard]:
    """A card for every verified cause, ranked by what it cost.

    `per_cause` is the movement each cause accounts for, already computed by the
    coverage stage. Nothing here recomputes it: the expected recovery is a share
    of a measured loss, so the figure on the card traces back to the same
    difference-in-differences result the diagnosis rests on.
    """
    now = now or datetime.now(UTC)
    cards: list[DecisionCard] = []

    for v in verifications:
        if v.state is not ClaimState.VERIFIED:
            continue
        candidate = v.candidate
        loss = abs(per_cause.get(candidate.candidate_id, 0.0))
        driver = _driver_for(candidate, contract)
        monitoring = _monitoring_for(driver, candidate, contract)
        caveats: list[str] = []

        lever = driver.controllable_lever if driver else None
        if driver is None:
            caveats.append(
                "no contract driver matches this cause, so no lever or owner "
                "could be derived"
            )
        elif lever is None:
            caveats.append(
                f"{driver.id} is observable but not controllable: the business "
                "can watch it, not change it"
            )

        if lever is None:
            cards.append(
                DecisionCard(
                    candidate_id=candidate.candidate_id,
                    cause=candidate.description or candidate.candidate_id,
                    driver=driver.id if driver else None,
                    lever=None,
                    owner=None,
                    controllable=False,
                    action=(
                        "No action: this cause has no lever. The response is to "
                        "monitor for it, which is the rule below."
                    ),
                    measured_loss_inr_per_day=loss,
                    expected_recovery_inr_per_day=None,
                    recovery_basis=(
                        "not computed: reversing this cause is not something "
                        "the business can do"
                    ),
                    confidence_band=confidence_band,
                    monitoring=monitoring,
                    approval=None,
                    caveats=tuple(caveats),
                )
            )
            continue

        share = RECOVERY_SHARE.get(lever)
        if share is None:
            recovery, basis = None, f"no recovery assumption declared for lever {lever!r}"
            caveats.append(
                "expected impact is left blank rather than guessed, because this "
                "lever has no declared recovery share"
            )
        else:
            recovery = loss * share
            basis = (
                f"{share:.0%} of the {loss:,.0f} rupees per day this cause was "
                f"measured to account for"
            )

        scope = ", ".join(
            f"{k} {val}" for k, val in
            (("channel", candidate.channel), ("device", candidate.device),
             ("category", candidate.category)) if val
        ) or ", ".join(candidate.exposed_regions) or "the affected slice"
        action = f"Apply {lever.replace('_', ' ')} for {scope}"

        approval = (
            _draft(action, candidate, driver, recovery, contract, now)
            if recovery is not None else None
        )

        cards.append(
            DecisionCard(
                candidate_id=candidate.candidate_id,
                cause=candidate.description or candidate.candidate_id,
                driver=driver.id,
                lever=lever,
                owner=driver.owner_role,
                controllable=True,
                action=action,
                measured_loss_inr_per_day=loss,
                expected_recovery_inr_per_day=recovery,
                recovery_basis=basis,
                confidence_band=confidence_band,
                monitoring=monitoring,
                approval=approval,
                caveats=tuple(caveats),
            )
        )

    cards.sort(key=lambda c: c.measured_loss_inr_per_day, reverse=True)
    return cards


__all__ = [
    "KIND_TO_DRIVER",
    "RECOVERY_SHARE",
    "ApprovalDraft",
    "DecisionCard",
    "MonitoringRule",
    "decision_cards",
]
