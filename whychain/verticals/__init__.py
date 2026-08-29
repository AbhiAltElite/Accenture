"""Which industries this deployment can be pointed at.

Three verticals, chosen so the console can show the same engine answering the
same eight questions about businesses whose metrics move for completely
different reasons. Retail is mostly moved by things the business did; petroleum
and power are mostly moved by things done to them. That contrast is the point of
having more than one, and it is what the switcher in the console is for.

Nothing here changes how anything is computed. A vertical names where its
contracts and its warehouse live, what its operational notes are about, and what
a reader of that industry calls each dimension. Detection, decomposition,
ranking, verification, confidence and every threshold are the contract's job in
all three, exactly as before.
"""

from __future__ import annotations

from whychain.verticals.petroleum import PETROLEUM
from whychain.verticals.power import POWER
from whychain.verticals.retail import RETAIL
from whychain.verticals.spec import RETAIL_PLAN_COLUMNS, PlanColumns, Vertical

# Retail first: it is the default, and the one every existing command and test
# resolves to when nothing is asked for.
VERTICALS: tuple[Vertical, ...] = (RETAIL, PETROLEUM, POWER)
DEFAULT_VERTICAL = RETAIL

_BY_ID = {v.id: v for v in VERTICALS}


class UnknownVertical(KeyError):
    pass


def get(vertical_id: str | None) -> Vertical:
    """Resolve an industry id, falling back to the default when none is given.

    Raises rather than guessing on an unknown id. A typo that silently served
    retail's numbers under a petroleum heading is the same class of failure as a
    cache key that omits its context (T-06): the answer looks right and is about
    something else.
    """
    if vertical_id is None or vertical_id == "":
        return DEFAULT_VERTICAL
    try:
        return _BY_ID[vertical_id]
    except KeyError:
        raise UnknownVertical(
            f"unknown industry {vertical_id!r}; known: {sorted(_BY_ID)}"
        ) from None


def available() -> tuple[Vertical, ...]:
    """Those whose warehouse has actually been generated."""
    return tuple(v for v in VERTICALS if v.is_generated())


__all__ = [
    "DEFAULT_VERTICAL",
    "PETROLEUM",
    "POWER",
    "RETAIL",
    "RETAIL_PLAN_COLUMNS",
    "VERTICALS",
    "PlanColumns",
    "UnknownVertical",
    "Vertical",
    "available",
    "get",
]
