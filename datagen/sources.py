"""Turn the demand panel into the source systems the engine reads.

Each source gets its own grain, its own refresh cadence and its own defects,
because reconciling them is part of what the engine is being asked to do. A
generator that emits three clean tables at the same grain removes the problem
rather than modelling it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from datagen.catalog import CITIES
from datagen.scenarios import CauseKind, PlantedEvent

# Refresh lag per source, as the engine will observe it.
SOURCE_LAG = {
    "pos_txn": timedelta(hours=3),
    "plan_ops": timedelta(days=2),      # T+2 by design; often breaches its 72h SLA
    "voice_ops": timedelta(minutes=20),
    "ext_signals": timedelta(hours=20),
}


def emit_pos_txn(panel: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Order lines, the finest grain in the system.

    Expanded from the panel so the transactions sum back to the series exactly.
    Two defects are injected on purpose: a handful of duplicated order ids, and
    timestamps written in local time for one region while the rest are UTC.
    """
    rng = np.random.default_rng(seed)
    counts = np.maximum(panel["orders"].to_numpy().round().astype(int), 0)
    keep = counts > 0
    rows = panel.loc[keep]
    counts = counts[keep]

    idx = np.repeat(np.arange(len(rows)), counts)
    total = len(idx)

    src = rows.iloc[idx]
    # Spread orders through the trading day rather than stacking them at midnight;
    # the hourly conversion metric needs a real intraday shape.
    hours = rng.choice(
        np.arange(24), size=total, p=_intraday_profile()
    )
    minutes = rng.integers(0, 60, total)

    order_ts = (
        pd.to_datetime(src["d"].to_numpy())
        + pd.to_timedelta(hours, unit="h")
        + pd.to_timedelta(minutes, unit="m")
    )

    qty = np.maximum(rng.poisson(1.4, total), 1)
    unit_price = src["unit_price"].to_numpy()
    # Most orders carry no discount; a minority carry a real one.
    discount = np.where(rng.random(total) < 0.22, unit_price * qty * rng.uniform(0.05, 0.25, total), 0.0)

    txn = pd.DataFrame(
        {
            "order_id": [f"O{i:09d}" for i in range(total)],
            "order_ts": order_ts,
            "region": src["region"].to_numpy(),
            "channel": src["channel"].to_numpy(),
            "device": src["device"].to_numpy(),
            "category": src["category"].to_numpy(),
            "sku": src["sku"].to_numpy(),
            "qty": qty,
            "unit_price": unit_price.round(2),
            "discount": discount.round(2),
            "status": "completed",
            "is_test": False,
        }
    )

    # Cancellations, so the contract's status filter has something to exclude.
    cancelled = rng.random(total) < 0.018
    txn.loc[cancelled, "status"] = "cancelled"

    # Test accounts, which the orders contract filters and the revenue one does not.
    txn.loc[rng.random(total) < 0.004, "is_test"] = True

    return _inject_defects(txn, rng)


def _intraday_profile() -> np.ndarray:
    """Hourly order distribution: quiet overnight, peaks at lunch and late evening."""
    shape = np.array(
        [0.4, 0.2, 0.1, 0.1, 0.1, 0.2, 0.5, 1.0, 1.8, 2.6, 3.4, 4.2,
         4.8, 4.4, 3.8, 3.6, 4.0, 4.8, 6.0, 7.2, 7.6, 6.4, 3.8, 1.6]
    )
    return shape / shape.sum()


def _inject_defects(txn: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Real extracts are not clean. These are the two the reconciler must handle."""
    # Duplicate order ids: the same order delivered twice by an upstream feed.
    # A naive count(*) inflates volume; count(distinct order_id) does not.
    dupes = txn.sample(n=max(1, len(txn) // 4000), random_state=int(rng.integers(1e6)))
    txn = pd.concat([txn, dupes], ignore_index=True)

    # One region's extract arrives in local time rather than UTC. Left uncorrected
    # it shifts orders across the day boundary and smears the hourly metric.
    east = txn["region"] == "East"
    txn.loc[east, "order_ts"] = txn.loc[east, "order_ts"] + timedelta(hours=5, minutes=30)

    return txn.sort_values("order_ts").reset_index(drop=True)


def emit_plan_ops(panel: pd.DataFrame, events: tuple[PlantedEvent, ...], seed: int = 11) -> pd.DataFrame:
    """Weekly planning extract: marketing spend, stock cover, competitor index.

    Coarser grain and a two-day lag, so a diagnosis run early in the week is
    working with numbers that predate the movement it is explaining.
    """
    rng = np.random.default_rng(seed)
    weekly = (
        panel.assign(week=panel["d"].dt.to_period("W").dt.start_time)
        .groupby(["week", "region", "category"], as_index=False)
        .agg(revenue=("revenue", "sum"), units=("units", "sum"))
    )

    # Spend tracks revenue with noise, correlated enough to be a plausible
    # candidate driver, which is what makes ranking non-trivial.
    weekly["marketing_spend"] = (
        weekly["revenue"] * rng.uniform(0.05, 0.09, len(weekly))
    ).round(0)
    weekly["planned_stock"] = (weekly["units"] * rng.uniform(1.05, 1.35, len(weekly))).round(0)
    weekly["competitor_price_index"] = np.round(rng.normal(100, 3.5, len(weekly)), 2)

    # Planted events are recorded here as operational facts. Causes and decoys
    # are written identically; nothing marks which is which.
    weekly["promo_active"] = False
    weekly["promo_id"] = None
    for event in events:
        if event.kind not in (CauseKind.MARKETING_CUT, CauseKind.COMPETITOR_PROMO):
            continue
        regions = {event.target.region} if event.target.region else set(weekly["region"])
        regions |= set(event.also_in)
        mask = (
            weekly["week"].dt.date.between(
                event.start - timedelta(days=6), event.end
            )
            & weekly["region"].isin(regions)
        )
        if event.target.category:
            mask &= weekly["category"] == event.target.category
        weekly.loc[mask, "promo_active"] = True
        weekly.loc[mask, "promo_id"] = event.event_id
        if event.kind is CauseKind.COMPETITOR_PROMO:
            weekly.loc[mask, "competitor_price_index"] -= 6.5

    # Missing weeks: the extract does not always land. Null, not zero; a zero
    # would be read as "no spend" rather than "we do not know".
    drop = rng.random(len(weekly)) < 0.03
    weekly.loc[drop, ["marketing_spend", "planned_stock"]] = np.nan

    return weekly.drop(columns=["revenue", "units"])


TICKET_TEMPLATES = {
    CauseKind.INTERNAL_BUG: [
        "Cannot complete checkout on the app. The card entry page is blank after the update.",
        "Payment step crashes every time on Android. Tried four times, no order placed.",
        "App checkout broken since the last release. It spins and then fails.",
        "Unable to pay on mobile. The card form does not load at all.",
    ],
    CauseKind.EXTERNAL_WEATHER: [
        "Delivery delayed due to flooding in the area. No update for two days.",
        "Store was shut because of the rain, could not collect my order.",
        "Shipment stuck, courier says roads are closed after heavy rainfall.",
    ],
    CauseKind.STOCKOUT: [
        "The item I wanted has been out of stock for a week now.",
        "Order cancelled by the seller citing unavailability.",
        "Cannot find the product in my area any more.",
    ],
    CauseKind.COMPETITOR_PROMO: [
        "Found the same pack cheaper elsewhere, cancelling this order.",
        "Your price went up compared to the other app.",
    ],
    CauseKind.PRICE_CHANGE: [
        "The price of this item changed between adding it and checking out.",
        "Introductory offer seems to have ended without notice.",
    ],
    CauseKind.MARKETING_CUT: [
        "Was the monsoon sale extended? The banner disappeared.",
    ],
}

BACKGROUND_TICKETS = [
    "Delivery arrived on time, no issues.",
    "Requesting a refund for a damaged item.",
    "How do I change my delivery address?",
    "Product quality was good but packaging was torn.",
    "Please cancel my subscription renewal.",
    "The invoice shows the wrong GST number.",
]


def emit_voice_ops(
    panel: pd.DataFrame, events: tuple[PlantedEvent, ...], seed: int = 13
) -> pd.DataFrame:
    """Support tickets, rep notes and the release log.

    Ticket volume tracks the events that actually happened. A decoy generates no
    tickets, because nothing went wrong, which is one of the ways corroboration
    separates a real cause from a coincidence.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    doc_id = 0

    start = panel["d"].min().date()
    end = panel["d"].max().date()

    # Background noise across the whole period.
    day = start
    while day <= end:
        for _ in range(rng.poisson(6)):
            rows.append(
                {
                    "doc_id": f"TK{doc_id:06d}",
                    "doc_type": "support_ticket",
                    "ts": datetime(day.year, day.month, day.day, int(rng.integers(6, 22)), tzinfo=UTC),
                    "region": rng.choice([c.region for c in CITIES]),
                    "text": rng.choice(BACKGROUND_TICKETS),
                }
            )
            doc_id += 1
        day += timedelta(days=1)

    # Event-driven tickets. Volume scales with how much the event actually moved
    # the metric, so a large regression produces a visible spike.
    for event in events:
        if event.effect == 0.0:
            continue  # a decoy breaks nothing, so nobody complains about it
        templates = TICKET_TEMPLATES.get(event.kind, BACKGROUND_TICKETS)
        per_day = int(abs(event.effect) * 90)
        day = event.start
        while day <= event.end:
            for _ in range(rng.poisson(per_day)):
                rows.append(
                    {
                        "doc_id": f"TK{doc_id:06d}",
                        "doc_type": "support_ticket",
                        "ts": datetime(day.year, day.month, day.day, int(rng.integers(6, 22)), tzinfo=UTC),
                        "region": event.target.region or rng.choice([c.region for c in CITIES]),
                        "text": rng.choice(templates),
                    }
                )
                doc_id += 1
            day += timedelta(days=1)

        # The corresponding operational record: a release note, a supplier email.
        rows.append(
            {
                "doc_id": f"OPS{doc_id:06d}",
                "doc_type": "release_log" if event.kind is CauseKind.INTERNAL_BUG else "ops_note",
                "ts": datetime(event.start.year, event.start.month, event.start.day, 8, tzinfo=UTC),
                "region": event.target.region or "All",
                "text": f"{event.event_id}: {event.description}",
            }
        )
        doc_id += 1

    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


def source_freshness(as_of: datetime | None = None) -> pd.DataFrame:
    """When each source last landed, as the engine would observe it."""
    now = as_of or datetime.now(UTC)
    return pd.DataFrame(
        [
            {"source_id": source, "as_of": now - lag, "observed_at": now}
            for source, lag in SOURCE_LAG.items()
        ]
    )


def emit_sessions(panel: pd.DataFrame, seed: int = 17) -> pd.DataFrame:
    """Hourly session counts for the digital channels.

    Emitted as counts, not one row per session. Web analytics arrives
    pre-aggregated in practice, and materialising thirty million rows in order to
    divide them straight back down is a costly way to store the same number.

    Sessions are generated independently of orders, so conversion is not constant
    by construction and a checkout regression can actually move it.
    """
    rng = np.random.default_rng(seed)
    digital = panel[panel["channel"].isin(["web", "app"])]
    grouped = digital.groupby(["d", "region", "channel", "device"], as_index=False)["orders"].sum()
    grouped = grouped[grouped["orders"] > 0].reset_index(drop=True)

    # Baseline conversion by device: mobile browses more and buys less.
    base_rate = grouped["device"].map({"mobile": 0.041, "desktop": 0.068, "tablet": 0.052})
    daily = (grouped["orders"] / base_rate * rng.normal(1.0, 0.05, len(grouped))).round()

    frames = []
    for hour, share in enumerate(_intraday_profile()):
        if share < 0.005:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "session_ts": pd.to_datetime(grouped["d"]) + pd.Timedelta(hours=hour),
                    "region": grouped["region"],
                    "channel": grouped["channel"],
                    "device": grouped["device"],
                    "sessions": np.maximum((daily * share).round(), 0).astype(int),
                }
            )
        )
    out = pd.concat(frames, ignore_index=True)
    return out[out["sessions"] > 0].reset_index(drop=True)


def emit_shipments(panel: pd.DataFrame, events: tuple[PlantedEvent, ...], seed: int = 23) -> pd.DataFrame:
    """Delivery promises and outcomes, at T+1 from a separate system."""
    rng = np.random.default_rng(seed)
    grouped = panel.groupby(["d", "region", "category"], as_index=False)["orders"].sum()
    grouped = grouped[grouped["orders"] > 0]

    counts = np.maximum((grouped["orders"] / 6).round().astype(int), 1)
    idx = np.repeat(np.arange(len(grouped)), counts)
    total = len(idx)
    src = grouped.iloc[idx]

    promised = pd.to_datetime(src["d"].to_numpy()) + pd.to_timedelta(
        rng.integers(2, 6, total), unit="D"
    )
    # Baseline on-time performance, before anything goes wrong.
    late_risk = np.full(total, 0.09)

    day = pd.Series(promised).dt.date.to_numpy()
    region = src["region"].to_numpy()
    for event in events:
        if event.effect == 0.0 or event.kind not in (
            CauseKind.EXTERNAL_WEATHER, CauseKind.STOCKOUT
        ):
            continue
        hit = (day >= event.start) & (day <= event.end)
        if event.target.region:
            hit &= region == event.target.region
        late_risk = np.where(hit, np.clip(late_risk + abs(event.effect), 0, 0.95), late_risk)

    late = rng.random(total) < late_risk
    delivered = promised + pd.to_timedelta(np.where(late, rng.integers(1, 5, total), 0), unit="D")

    return pd.DataFrame(
        {
            "shipment_id": [f"SH{i:09d}" for i in range(total)],
            "promised_date": promised,
            "delivered_date": delivered,
            "region": region,
            "category": src["category"].to_numpy(),
            "carrier": rng.choice(["BlueDart", "Delhivery", "Ecom", "InHouse"], total),
        }
    )


# Severity bands as a public met service issues them. Only amber and above is
# actionable: a yellow advisory covering half the country every monsoon week is
# available without being usable, which is the distinction Answer 2 turns on.
_SEVERITY_BANDS = ((0.85, "red"), (0.65, "amber"), (0.40, "yellow"), (0.0, "green"))


def _severity(intensity: float) -> str:
    return next(name for floor, name in _SEVERITY_BANDS if intensity >= floor)


def emit_ext_signals(
    panel: pd.DataFrame,
    events: tuple[PlantedEvent, ...],
    seed: int = 29,
    declared: tuple = (),
) -> pd.DataFrame:
    """Public weather warnings, per city, as an external feed would deliver them.

    This is the source Answer 2 reads. It is a peer of nothing: the engine
    consults it, never joins it into the fact grain, because a warning is
    context until a causal test says otherwise.

    Every row carries what foreseeability is decided on, and no more:

    - `issued_at` against `valid_from` gives the lead time. A warning that
      landed an hour before the weather is not a missed opportunity, and the
      engine must be able to say so rather than manufacture a gap in hindsight.
    - `severity` gives the actionability threshold.
    - `city` and `region` give the spatial specificity. A national advisory does
      not cover a regional slice.
    - `is_public` records whether anyone outside the company could have seen it.

    The values are generated, not fetched. That is stated in `source` on every
    row so a reader is never misled about provenance, and the schema is the one
    a cached IMD or Open-Meteo snapshot drops into unchanged.
    """
    rng = np.random.default_rng(seed)
    days = pd.to_datetime(panel["d"]).drop_duplicates().sort_values()

    weather_windows = {
        (e.target.region, d.date())
        for e in events
        if e.kind is CauseKind.EXTERNAL_WEATHER and not e.is_decoy
        for d in pd.date_range(e.start, e.end, freq="D")
    }

    rows = []
    for city in CITIES:
        seasonal = _monsoon_intensity(days, city.region)
        for day, base in zip(days, seasonal, strict=True):
            planted = (city.region, day.date()) in weather_windows
            # A planted event is a genuine severe-weather episode; the rest is
            # ordinary monsoon variation, which is what stops the feed being a
            # perfect oracle for the events.
            intensity = min(1.0, base + 0.55) if planted else base
            intensity = float(np.clip(intensity + rng.normal(0, 0.06), 0.0, 1.0))
            severity = _severity(intensity)
            if severity == "green":
                continue

            valid_from = datetime.combine(day.date(), datetime.min.time(), tzinfo=UTC)
            # Real met services issue further ahead for more severe weather.
            lead_hours = {"yellow": 18.0, "amber": 54.0, "red": 78.0}[severity]
            lead_hours += float(rng.normal(0, 6))
            rows.append(
                {
                    "signal_id": f"wx-{city.name.lower()}-{day.date():%Y%m%d}",
                    "signal_type": "severe_weather",
                    "city": city.name,
                    "region": city.region,
                    "lat": city.lat,
                    "lon": city.lon,
                    "severity": severity,
                    "intensity": round(intensity, 3),
                    "issued_at": valid_from - timedelta(hours=lead_hours),
                    "valid_from": valid_from,
                    "valid_to": valid_from + timedelta(hours=24),
                    "lead_time_hours": round(lead_hours, 1),
                    "is_public": True,
                    "publisher": "India Meteorological Department",
                    "source": "generated",
                    "source_url": "https://mausam.imd.gov.in/",
                }
            )
    rows.extend(_declared_rows(declared))
    return pd.DataFrame(rows).sort_values(["valid_from", "city"]).reset_index(drop=True)


# Scenario-declared signals are not weather. The demo cases carry warnings from
# other publishers, a carrier status page, a competitor price feed, and they
# exist to make the non-weather verdicts reachable from the real feed rather
# than only from the scenario definition. Without them `not_foreseeable` is a
# state the engine can return and the data can never produce, which is the same
# as not having it.
_DECLARED_TYPE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("carrier", "courier", "logistics", "3pl"), "carrier_disruption"),
    (("imd", "weather", "rain", "flood", "storm", "cyclone"), "severe_weather"),
    (("competitor", "price", "promo"), "competitor_action"),
    (("supplier", "stock", "shortage"), "supply_disruption"),
)


def _declared_type(signal_id: str, publisher: str) -> str:
    text = f"{signal_id} {publisher}".lower()
    for words, mapped in _DECLARED_TYPE:
        if any(w in text for w in words):
            return mapped
    return "external_advisory"


def _declared_rows(declared: tuple) -> list[dict]:
    """Emit each scenario's AvailableSignal into the feed's own schema.

    Severity is carried from the scenario rather than derived from lead time.
    They are independent: a flash-flood nowcast is red and arrives fifty minutes
    ahead, while a routine monsoon advisory is yellow and arrives two days
    ahead. Deriving severity from timing would collapse the two gates Answer 2
    deliberately keeps apart, so that the only refusal it could ever produce is
    "nothing was serious" rather than the sharper and more common "serious, and
    far too late to act on".
    """
    rows: list[dict] = []
    for signal in declared:
        region = getattr(signal.covers, "region", None) or "All"
        severity = getattr(signal, "severity", "amber")
        valid_from = signal.available_at + timedelta(hours=signal.lead_time_hours)
        city = next((c for c in CITIES if c.region == region), CITIES[0])
        rows.append(
            {
                "signal_id": signal.signal_id,
                "signal_type": _declared_type(signal.signal_id, signal.publisher),
                "city": city.name if region != "All" else "All India",
                "region": region,
                "lat": city.lat,
                "lon": city.lon,
                "severity": severity,
                "intensity": round(min(1.0, signal.lead_time_hours / 96.0), 3),
                "issued_at": signal.available_at,
                "valid_from": valid_from,
                "valid_to": valid_from + timedelta(hours=120),
                "lead_time_hours": round(signal.lead_time_hours, 1),
                "is_public": signal.is_public,
                "publisher": signal.publisher,
                "source": "generated",
                "source_url": None,
            }
        )
    return rows


def _monsoon_intensity(days: pd.Series, region: str) -> np.ndarray:
    """Ordinary seasonal wetness, on the same curve the panel is built from.

    Shares its shape with `series._monsoon_factor` so the feed and the demand it
    is meant to explain agree about when the monsoon is.
    """
    day_of_year = days.dt.dayofyear.to_numpy()
    phase = {"West": 190, "South": 250, "East": 200, "North": 210}[region]
    depth = {"West": 0.62, "South": 0.34, "East": 0.45, "North": 0.20}[region]
    return depth * np.exp(-(((day_of_year - phase) / 32.0) ** 2))
