"""Price, volume and mix decomposition.

Revenue is units times price, summed over products. When it moves, exactly three
things can have changed: how much was sold, what was sold, and what it was sold
for. Separating them is arithmetic, not estimation, and the three parts add back
to the total exactly.

That exactness is the point. A model-based attribution can rank drivers but
cannot promise its numbers sum to the movement being explained. This can, and
the reconciliation is asserted rather than assumed.

    revenue = Q * sum(share_i * price_i)

    volume = (Q1 - Q0) * sum(share0_i * price0_i)
    mix    = Q1 * sum((share1_i - share0_i) * price0_i)
    price  = Q1 * sum(share1_i * (price1_i - price0_i))

Volume holds mix and price at base and moves total units. Mix holds price at
base and moves composition. Price moves last, over the mix that actually
occurred. The order matters: attribution is path dependent, and this order
answers the question a reader is asking, which is what changed relative to how
things used to be.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from whychain.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceStore,
    MethodClass,
    Provenance,
    Unit,
)

# Floating point error accumulates over hundreds of thousands of rows. A tenth
# of a rupee on a movement measured in lakhs is arithmetic noise; anything
# larger means the decomposition is wrong.
RECONCILE_TOLERANCE = 0.10


class BridgeError(Exception):
    """The decomposition failed to reconcile, so it must not be reported."""


@dataclass(frozen=True)
class Bridge:
    """A movement split into its three causes, with the identity checked."""

    base_revenue: float
    current_revenue: float
    volume_effect: float
    mix_effect: float
    price_effect: float
    base_units: float
    current_units: float
    products: int

    @property
    def total_change(self) -> float:
        return self.current_revenue - self.base_revenue

    @property
    def explained(self) -> float:
        return self.volume_effect + self.mix_effect + self.price_effect

    @property
    def residual(self) -> float:
        return self.total_change - self.explained

    def shares(self) -> dict[str, float]:
        """Each effect as a share of the movement, for reporting."""
        total = self.total_change
        if total == 0:
            return {"volume": 0.0, "mix": 0.0, "price": 0.0}
        return {
            "volume": self.volume_effect / total,
            "mix": self.mix_effect / total,
            "price": self.price_effect / total,
        }

    def assert_reconciles(self) -> None:
        if abs(self.residual) > RECONCILE_TOLERANCE:
            raise BridgeError(
                f"bridge does not reconcile: change {self.total_change:,.2f} but "
                f"effects sum to {self.explained:,.2f} (residual {self.residual:,.2f}). "
                "An identity that does not hold must not be reported as one."
            )


def compute_bridge(base: pd.DataFrame, current: pd.DataFrame, key: str = "sku") -> Bridge:
    """Decompose the movement between two periods.

    Both frames need `units` and `revenue` per product. Price is derived rather
    than taken as given, because the price actually realised includes discounting
    and a list price would not reconcile.
    """
    if base.empty or current.empty:
        raise BridgeError("both periods need data; a bridge from nothing explains nothing")

    b = base.groupby(key, as_index=False)[["units", "revenue"]].sum()
    c = current.groupby(key, as_index=False)[["units", "revenue"]].sum()

    merged = b.merge(c, on=key, how="outer", suffixes=("_0", "_1")).fillna(0.0)

    q0_total = merged["units_0"].sum()
    q1_total = merged["units_1"].sum()
    if q0_total <= 0:
        raise BridgeError("base period sold nothing, so there is no baseline to move from")

    # Realised price. Products absent from a period have no price of their own,
    # so they inherit the other period's: a launch is a mix change, not an
    # infinite price change.
    # NaN rather than pd.NA: the result is arithmetic, and NA does not cast to float.
    price_0 = merged["revenue_0"].astype(float) / merged["units_0"].astype(float).replace(0.0, np.nan)
    price_1 = merged["revenue_1"].astype(float) / merged["units_1"].astype(float).replace(0.0, np.nan)
    price_0 = price_0.fillna(price_1).fillna(0.0)
    price_1 = price_1.fillna(price_0).fillna(0.0)

    share_0 = merged["units_0"] / q0_total
    share_1 = merged["units_1"] / q1_total if q1_total > 0 else share_0 * 0.0

    base_avg_price = float((share_0 * price_0).sum())

    volume = (q1_total - q0_total) * base_avg_price
    mix = q1_total * float(((share_1 - share_0) * price_0).sum())
    price = q1_total * float((share_1 * (price_1 - price_0)).sum())

    bridge = Bridge(
        base_revenue=float(merged["revenue_0"].sum()),
        current_revenue=float(merged["revenue_1"].sum()),
        volume_effect=float(volume),
        mix_effect=float(mix),
        price_effect=float(price),
        base_units=float(q0_total),
        current_units=float(q1_total),
        products=len(merged),
    )
    bridge.assert_reconciles()
    return bridge


def record_bridge(
    bridge: Bridge, store: EvidenceStore, source_id: str, query: str
) -> list[Evidence]:
    """Write each leg of the bridge as its own evidence record."""
    legs = (
        ("volume", bridge.volume_effect, "fewer or more units sold"),
        ("mix", bridge.mix_effect, "a shift in which products sold"),
        ("price", bridge.price_effect, "a change in realised price"),
    )
    out: list[Evidence] = []
    for name, value, meaning in legs:
        direction = "reduced" if value < 0 else "increased"
        out.append(
            store.add(
                Evidence(
                    id=store.next_id(),
                    kind=EvidenceKind.DECOMPOSITION,
                    claim=(
                        f"The {name} effect {direction} revenue by "
                        f"{abs(value):,.0f}, from {meaning}."
                    ),
                    value=float(value),
                    unit=Unit.INR,
                    method="pvm_bridge",
                    method_class=MethodClass.DETERMINISTIC,
                    provenance=Provenance(source_id=source_id, query=query),
                    run_id=store.run_id,
                    extra={
                        "leg": name,
                        "share_of_movement": bridge.shares()[name],
                        "base_revenue": bridge.base_revenue,
                        "current_revenue": bridge.current_revenue,
                        "residual": bridge.residual,
                    },
                )
            )
        )
    return out
