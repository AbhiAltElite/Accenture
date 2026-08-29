"""How much of a measured loss reversing a cause is assumed to recover.

Kept in its own module because both the decision card and the impact simulator
need it, and a card and a scenario disagreeing about the same action would be
worse than either being wrong on its own.

These are assumptions, not measurements. They are declared here, as data, so a
reader can see the number and argue with it rather than find it inside a
formula. A rollback restores the prior build but not the orders already lost; a
replenishment recovers less still, because demand deferred is partly demand
gone. Bringing a tripped unit back on bar recovers most of what it was
scheduled for; a regulatory filing recovers very little, because a tariff order
is not reversed by asking.

A lever absent from a model's table has no declared share, and both callers
leave the expected impact blank rather than choosing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RECOVERY_SHARE: dict[str, float] = {
    "release_rollback": 0.90,
    # A failover restores the payment path within minutes, so it recovers almost
    # everything still ahead of it -- but not the baskets already abandoned.
    "gateway_failover": 0.85,
    "replenishment": 0.65,
    # Switching carrier fixes the deliveries not yet promised. The ones already
    # late stay late, and the credits against them are already owed.
    "carrier_mix": 0.55,
    "pricing": 0.50,
    "media_budget": 0.40,
    # Re-merchandising is the slowest lever here: an assortment change reaches a
    # shelf on the next planogram cycle, not this week.
    "assortment": 0.35,
}


@dataclass(frozen=True)
class RecoveryModel:
    """What reversing a cause is worth, and what reversing it is called.

    The arithmetic does not vary by industry: a recovery is a measured loss
    times a declared share, and a scenario is unavailable when the cause it
    would reverse did not survive causal testing. What varies is which levers
    exist, how much each recovers, and the words a reader of that industry uses
    -- "roll the release back" is meaningless to a refinery, and asking it there
    reads as a console built for somebody else.

    Every field defaults to retail's, which is the model this module was
    written against.
    """

    share: dict[str, float] = field(default_factory=lambda: dict(RECOVERY_SHARE))

    # The reversal scenario: the one verified cause this industry can undo.
    reversal_id: str = "rollback"
    reversal_driver: str = "release_quality"
    reversal_kind: str = "release_log"
    reversal_lever: str = "release_rollback"
    reversal_question: str = "What happens if we roll the release back now?"
    reversal_absent: str = (
        "no shipped release survived causal testing in this window, so there is "
        "nothing measured to roll back"
    )
    reversal_caveat: str = (
        "a rollback restores the prior build but not the orders already lost"
    )

    # The price scenario: which declared driver carries the elasticity, and what
    # a reader of this industry calls the number being moved.
    price_driver: str = "unit_price"
    price_noun: str = "price"

    # Candidate kinds that count as an external pressure to project forward.
    external_kinds: tuple[str, ...] = ("ops_note", "promotion")

    def share_for(self, lever: str | None) -> float | None:
        return self.share.get(lever) if lever else None


RETAIL_RECOVERY = RecoveryModel()

__all__ = ["RECOVERY_SHARE", "RETAIL_RECOVERY", "RecoveryModel"]
