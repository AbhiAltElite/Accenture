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
from datagen.scenarios import PlantedEvent
from datagen.world import RETAIL_WORLD, World

# Retail's window and shares, under their original names. Read off the world
# rather than restated, so there is one place each number lives.
START = RETAIL_WORLD.start
END = RETAIL_WORLD.end
REGION_SCALE = RETAIL_WORLD.region_scale
CHANNEL_SHARE = RETAIL_WORLD.channel_share
DEVICE_SHARE = RETAIL_WORLD.device_share

BASE_DAILY_ORDERS = RETAIL_WORLD.base_daily_orders
ANNUAL_GROWTH = RETAIL_WORLD.annual_growth
NOISE_SD = RETAIL_WORLD.noise_sd


def _valid_cells(world: World) -> list[tuple[str, str, str, str]]:
    """Region x channel x device x SKU, excluding impossible combinations."""
    cells = []
    for region, channel in itertools.product(world.regions, world.channel_share):
        for device in world.channel_devices[channel]:
            for product in world.products:
                cells.append((region, channel, device, product.sku))
    return cells


def _seasonal_factor(days: pd.Series, region: str, world: World) -> np.ndarray:
    """Regional weather seasonality.

    The West monsoon is sharp and suppresses store traffic; the South is milder
    and later. This exists so that a real weather event has to be separated from
    ordinary seasonal wetness rather than standing out trivially.

    Depth may be negative, which is a season that lifts rather than suppresses:
    a fuel marketer sells more diesel through the harvest, and a generator's
    whole year is shaped by the summer peak.
    """
    day_of_year = days.dt.dayofyear.to_numpy()
    phase = world.seasonal_phase[region]
    depth = world.seasonal_depth[region]
    return 1.0 - depth * np.exp(-(((day_of_year - phase) / 32.0) ** 2))


def build_panel(
    start: date | None = None,
    end: date | None = None,
    events: tuple[PlantedEvent, ...] = (),
    seed: int | None = None,
    world: World = RETAIL_WORLD,
) -> pd.DataFrame:
    """Daily panel with planted effects applied.

    Returns one row per day and cell with `orders`, `units`, `unit_price` and
    `revenue`. Revenue is computed from the other three rather than modelled
    separately, so the KPI identity holds exactly and the bridge can reconcile.
    """
    start = start or world.start
    end = end or world.end
    rng = np.random.default_rng(world.seed if seed is None else seed)
    days = pd.date_range(start, end, freq="D")
    cells = _valid_cells(world)
    products = {p.sku: p for p in world.products}

    uplift = festival_uplift(start, end, world.calendar)
    festival = np.array([uplift.get(d.date(), 1.0) for d in days])
    weekday = np.array([weekday_uplift(d.date(), world.calendar) for d in days])
    elapsed_years = np.arange(len(days)) / 365.25
    trend = (1.0 + world.annual_growth) ** elapsed_years

    frames = []
    for region, channel, device, sku in cells:
        product = products[sku]

        scale = (
            world.base_daily_orders
            * world.region_scale[region]
            * world.channel_share[channel]
            * world.device_share[device]
            / len(world.products)
        )
        seasonal = _seasonal_factor(days.to_series(), region, world)
        orders = scale * trend * weekday * festival * seasonal

        # Physically exposed channels feel weather twice: once through demand
        # and once through being shut. Digital channels barely do.
        if channel in world.weather_exposed_channels:
            orders = orders * (2.0 - seasonal)

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
    panel = _apply_events(panel, events, products, world)

    # Noise last, so planted effects are not smoothed by it.
    noise = rng.normal(1.0, world.noise_sd, len(panel))
    panel["orders"] = np.maximum(panel["orders"] * noise, 0.0)

    # Units per order varies a little by category; premium lines sell singly.
    basket = panel["unit_price"].to_numpy()
    panel["units_per_order"] = np.clip(
        world.basket_intercept - basket / world.basket_divisor,
        world.basket_min,
        world.basket_max,
    )

    panel["orders"] = panel["orders"].round(3)
    panel["units"] = (panel["orders"] * panel["units_per_order"]).round(3)
    panel["revenue"] = (panel["units"] * panel["unit_price"]).round(2)
    return panel.drop(columns=["units_per_order"])


def _apply_events(
    panel: pd.DataFrame,
    events: tuple[PlantedEvent, ...],
    products: dict,
    world: World = RETAIL_WORLD,
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
        regions = [event.target.region] if event.target.region else list(world.regions)
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

        if event.kind in world.price_event_kinds:
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
