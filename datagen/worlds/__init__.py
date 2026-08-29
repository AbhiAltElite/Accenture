"""The generated businesses, one module each.

Retail lives in `datagen.world` because it is the default every function falls
back to. These two are the externally-driven verticals: their metrics move
because of duty notifications, refinery turnarounds, port closures, tariff
orders, fuel supply and the weather, and almost none of that appears in an
internal log until after it has happened.
"""

from datagen.world import RETAIL_WORLD
from datagen.worlds.petroleum import PETROLEUM_WORLD
from datagen.worlds.power import POWER_WORLD

WORLDS = {w.id: w for w in (RETAIL_WORLD, PETROLEUM_WORLD, POWER_WORLD)}

__all__ = ["PETROLEUM_WORLD", "POWER_WORLD", "RETAIL_WORLD", "WORLDS"]
