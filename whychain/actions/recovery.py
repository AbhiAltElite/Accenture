"""How much of a measured loss reversing a cause is assumed to recover.

Kept in its own module because both the decision card and the impact simulator
need it, and a card and a scenario disagreeing about the same action would be
worse than either being wrong on its own.

These are assumptions, not measurements. They are declared here, as data, so a
reader can see the number and argue with it rather than find it inside a
formula. A rollback restores the prior build but not the orders already lost; a
replenishment recovers less still, because demand deferred is partly demand
gone.

A lever absent from this table has no declared share, and both callers leave the
expected impact blank rather than choosing one.
"""

from __future__ import annotations

RECOVERY_SHARE: dict[str, float] = {
    "release_rollback": 0.90,
    "replenishment": 0.65,
    "pricing": 0.50,
    "media_budget": 0.40,
}

__all__ = ["RECOVERY_SHARE"]
