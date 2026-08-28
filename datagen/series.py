"""The underlying demand series, before it becomes source records.

Builds a daily panel at region x channel x device x SKU, then applies planted
events to the slices they target. Everything downstream is a view of this: order
lines, weekly plans and support tickets are all emitted from the same numbers, so
the sources agree with each other the way real ones do.

The series is deliberately not smooth. Trend, weekly rhythm, festivals, regional
monsoon effects and noise all sit on top of each other, because a detector that
only has to find a step change in a flat line has not been tested.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import numpy as np
import pandas as pd

from datagen.calendar import festival_uplift, weekday_uplift
from datagen.catalog import CHANNEL_DEVICES, PRODUCTS, REGIONS
from datagen.scenarios import CauseKind, PlantedEvent

START = date(2023, 9, 1)
END = date(2026, 8, 31)

# Baseline daily order volume per region, before any other effect.
REGION_SCALE = {"West": 1.00, "North": 0.86, "South": 0.78, "East": 0.44}
CHANNEL_SHARE = {"app": 0.44, "web": 0.31, "store": 0.25}
DEVICE_SHARE = {"mobile": 0.72, "desktop": 0.20, "tablet": 0.08, "pos": 1.00}

BASE_DAILY_ORDERS = 520.0
ANNUAL_GROWTH = 0.11
NOISE_SD = 0.045


def _valid_cells() -> list[tuple[str, str, str, str]]:
    """Region x channel x device x SKU, excluding impossible combinations."""
    cells = []
    for region, channel in itertools.product(REGIONS, CHANNEL_SHARE):
        for device in CHANNEL_DEVICES[channel]:
            for product in PRODUCTS:
                cells.append((region, channel, device, product.sku))
    return cells


def _monsoon_factor(days: pd.Series, region: str) -> np.ndarray:
    """Regional weather seasonality.

    The West monsoon is sharp and suppresses store traffic; the South is milder
    and later. This exists so that a real weather event has to be separated from
    ordinary seasonal wetness rather than standing out trivially.
    """
    day_of_year = days.dt.dayofyear.to_numpy()
    phase = {"West": 190, "South": 250, "East": 200, "North": 210}[region]
    depth = {"West": 0.10, "South": 0.05, "East": 0.07, "North": 0.03}[region]
    return 1.0 - depth * np.exp(-(((day_of_year - phase) / 32.0) ** 2))


def build_panel(
    start: date = START,
    end: date = END,
    events: tuple[PlantedEvent, ...] = (),
    seed: int = 20260828,
) -> pd.DataFrame:
    """Daily panel with planted effects applied.

    Returns one row per day and cell with `orders`, `units`, `unit_price` and
    `revenue`. Revenue is computed from the other three rather than modelled
    separately, so the KPI identity holds exactly and the bridge can reconcile.
    """
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    cells = _valid_cells()
    products = {p.sku: p for p in PRODUCTS}

    uplift = festival_uplift(start, end)
    festival = np.array([uplift.get(d.date(), 1.0) for d in days])
    weekday = np.array([weekday_uplift(d.date()) for d in days])
    elapsed_years = np.arange(len(days)) / 365.25
    trend = (1.0 + ANNUAL_GROWTH) ** elapsed_years

    frames = []
    for region, channel, device, sku in cells:
        product = products[sku]

        scale = (
            BASE_DAILY_ORDERS
            * REGION_SCALE[region]
            * CHANNEL_SHARE[channel]
            * DEVICE_SHARE[device]
            / len(PRODUCTS)
        )
        orders = scale * trend * weekday * festival * _monsoon_factor(days.to_series(), region)

        # Store channels feel weather; digital channels barely do.
        if channel == "store":
            orders = orders * (2.0 - _monsoon_factor(days.to_series(), region))

        price = np.full(len(days), product.base_price, dtype=float)

        # A SKU launched partway through has nothing before that date. This is
        # what makes the sparse-history case genuinely sparse rather than a
        # short window over a long history.
        if product.launched_month:
            launch = start + timedelta(days=int(product.launched_month * 30.44))
            orders = np.where(days.date >= launch, orders, 0.0)

        frame = pd.DataFrame(
            {
                "d": days,
                "region": region,
                "channel": channel,
                "device": device,
                "sku": sku,
                "category": product.category,
                "orders": orders,
                "unit_price": price,
            }
        )
        frames.append(frame)

    panel = pd.concat(frames, ignore_index=True)
    panel = _apply_events(panel, events, products)

    # Noise last, so planted effects are not smoothed by it.
    noise = rng.normal(1.0, NOISE_SD, len(panel))
    panel["orders"] = np.maximum(panel["orders"] * noise, 0.0)

    # Units per order varies a little by category; premium lines sell singly.
    basket = panel["unit_price"].to_numpy()
    panel["units_per_order"] = np.clip(3.2 - basket / 260.0, 1.0, 3.5)

    panel["orders"] = panel["orders"].round(3)
    panel["units"] = (panel["orders"] * panel["units_per_order"]).round(3)
    panel["revenue"] = (panel["units"] * panel["unit_price"]).round(2)
    return panel.drop(columns=["units_per_order"])


def _apply_events(
    panel: pd.DataFrame, events: tuple[PlantedEvent, ...], products: dict
) -> pd.DataFrame:
    """Apply each planted event to the rows its slice targets.

    Decoys go through this same path and simply carry an effect of zero, so
    nothing in the emitted data distinguishes a trap from a real cause.
    """
    if not events:
        return panel

    day = panel["d"].dt.date

    for event in events:
        in_window = (day >= event.start) & (day <= event.end)

        # `also_in` regions receive the event record but never its effect. That
        # is what a comparison group is: the same thing happened, nothing moved.
        regions = [event.target.region] if event.target.region else list(REGIONS)
        target_regions = set(regions) | set(event.also_in)

        mask = in_window & panel["region"].isin(target_regions)
        for dim in ("channel", "device", "category", "sku"):
            value = getattr(event.target, dim)
            if value is not None:
                mask &= panel[dim] == value

        effective = mask.copy()
        if event.also_in:
            effective &= ~panel["region"].isin(event.also_in)

        if event.effect == 0.0:
            continue

        if event.kind is CauseKind.PRICE_CHANGE:
            # A price move changes price directly and volume through elasticity,
            # so it lands in the price and volume legs of the bridge rather than
            # showing up as unexplained demand.
            elasticity = np.array(
                [products[s].elasticity for s in panel.loc[effective, "sku"]]
            )
            panel.loc[effective, "unit_price"] *= 1.0 + event.effect
            panel.loc[effective, "orders"] *= 1.0 + event.effect * elasticity
        else:
            panel.loc[effective, "orders"] *= 1.0 + event.effect

    return panel


def daily_kpi(panel: pd.DataFrame, dims: tuple[str, ...] = ()) -> pd.DataFrame:
    """Aggregate the panel to a KPI series at the requested grain."""
    keys = ["d", *dims]
    agg = panel.groupby(keys, as_index=False).agg(
        orders=("orders", "sum"), units=("units", "sum"), revenue=("revenue", "sum")
    )
    agg["aov"] = (agg["revenue"] / agg["orders"].replace(0, np.nan)).round(2)
    return agg
