"""The parameters that make one generated business different from another.

Everything in here is a number or a name. None of it is a rule: the panel is
built the same way, the sources are emitted the same way, the defects are
injected the same way and the events are applied the same way in every world.
What changes is what the business sells, to how many regions, through which
routes, with what rhythm, and which of its channels feels the weather.

Holding these as a value rather than as module constants is what lets a second
and third industry exist without a second and third generator. `RETAIL_WORLD`
below carries exactly the constants the generator used before this file existed,
and is the default everywhere, so the retail warehouse regenerates byte for
byte -- which is checked rather than asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from datagen.catalog import CHANNEL_DEVICES, CITIES, PRODUCTS, REGIONS, City, Product
from datagen.voices import RETAIL_VOICES, VoicePack


@dataclass(frozen=True)
class Calendar:
    """The dates this business's demand actually responds to.

    Retail runs on the shopping festival year. A fuel marketer sees a smaller
    version of the same thing through festival travel, and a generator sees
    almost none of it -- what moves electricity is the summer, not Diwali. The
    weights are what differ; the build-up and hangover shape does not.
    """

    festival_weights: dict[str, float]
    build_up_days: int = 18
    hangover_days: int = 7
    hangover_depth: float = 0.25
    # Monday..Sunday. Retail peaks at the weekend; industrial offtake does the
    # opposite, and a generator barely notices the difference.
    weekday: tuple[float, ...] = (0.94, 0.92, 0.95, 0.99, 1.08, 1.18, 1.12)


@dataclass(frozen=True)
class PlanLevel:
    """A quantity the weekly planning extract carries, and how it is derived.

    `basis` is the panel column it tracks. A level is a quantity, so a driver
    series sums it over a week; the index below is a reading, so a driver series
    averages it. Getting that the wrong way round produces a number that looks
    like data and means nothing.
    """

    name: str
    basis: str            # "revenue" or "units"
    low: float
    high: float


@dataclass(frozen=True)
class PlanIndex:
    """An externally-set index the plan records, and what a shock does to it."""

    name: str
    mean: float
    sd: float
    shock: float          # applied when a shock-kind event is active


@dataclass(frozen=True)
class World:
    """One generated business, end to end."""

    id: str
    start: date
    end: date

    regions: tuple[str, ...]
    cities: tuple[City, ...]
    products: tuple[Product, ...]
    channel_devices: dict[str, tuple[str, ...]]
    region_scale: dict[str, float]
    channel_share: dict[str, float]
    device_share: dict[str, float]

    base_daily_orders: float
    annual_growth: float
    noise_sd: float
    calendar: Calendar

    # An annual weather cycle per region: where in the year it peaks, and how
    # deep it cuts. Retail's is the monsoon suppressing store traffic; power's
    # is the summer lifting demand, which is why depth may be negative.
    seasonal_phase: dict[str, int]
    seasonal_depth: dict[str, float]
    # Channels that feel the weather twice: once through demand and once through
    # being physically closed.
    weather_exposed_channels: tuple[str, ...] = ()

    # Units per order falls as the unit price rises: a premium line sells singly.
    basket_intercept: float = 3.2
    basket_divisor: float = 260.0
    basket_min: float = 1.0
    basket_max: float = 3.5

    # Share of the day's volume in each hour, 0..23.
    intraday: tuple[float, ...] = ()
    # Channels that produce sessions, and the baseline conversion each device
    # converts at. Only these reach the hourly rate contract.
    digital_channels: tuple[str, ...] = ()
    conversion_by_device: dict[str, float] = field(default_factory=dict)

    # Which region's extract lands in local time rather than UTC. The
    # reconciliation layer exists to correct exactly this.
    local_time_region: str = "East"
    carriers: tuple[str, ...] = ()

    # What the weekly planning extract carries. Retail plans promotions; a fuel
    # marketer plans turnarounds and allocations; a generator plans outages and
    # declared capacity. The shape is identical and only the names differ.
    plan_levels: tuple[PlanLevel, ...] = ()
    plan_index: PlanIndex | None = None
    plan_id_column: str = "promo_id"
    plan_active_column: str = "promo_active"

    # Which planted causes are recorded where. An event has to leave a trace in
    # the operational record or there is nothing for a candidate scanner to
    # find, and *which* record it lands in is a fact about the industry: a
    # competitor promotion appears in the weekly plan, a cyclone appears in the
    # delivery outcomes, a release regression appears in a deployment log.
    plan_event_kinds: tuple[str, ...] = ()
    # Kinds that move price directly and volume through elasticity, so they land
    # in the price and volume legs of the bridge rather than as unexplained
    # demand. An excise revision and a regulated tariff order are exactly this.
    price_event_kinds: tuple[str, ...] = ()
    index_shock_kinds: tuple[str, ...] = ()
    delivery_event_kinds: tuple[str, ...] = ()
    # The one kind whose operational note is filed as a `release_log` rather
    # than an `ops_note`. The doc types are shared across worlds on purpose:
    # `from_operations` reads those two names, and inventing a third per
    # industry would mean editing the scanner instead of configuring it.
    release_kind: str = ""

    # What this industry's people say, and how. See datagen/voices.py.
    voices: VoicePack = RETAIL_VOICES

    # What this industry calls the system that posts the money. The ledger is
    # the second view of the same quantity, so it needs the industry's own name
    # for it: a fuel marketer reconciles against SAP FI-CO, a generator against
    # a regulated energy-accounting ledger, and calling all three "finance" would
    # be the same flattening the rest of this file exists to avoid.
    ledger_name: str = "finance_gl"

    # The external hazard feed: what it warns about, how intense it ordinarily
    # gets in each region, and who publishes it.
    hazard_kind: str = ""
    hazard_intensity: dict[str, float] = field(default_factory=dict)
    hazard_signal_type: str = "severe_weather"
    hazard_publisher: str = "India Meteorological Department"
    hazard_url: str | None = "https://mausam.imd.gov.in/"

    # Orders per shipment, and the baseline chance one misses its promise.
    orders_per_shipment: float = 6.0
    late_risk_base: float = 0.09

    seed: int = 20260828

    def days(self) -> int:
        return (self.end - self.start).days + 1

    def region_of(self, city_name: str) -> str:
        for city in self.cities:
            if city.name == city_name:
                return city.region
        raise KeyError(f"unknown city: {city_name}")


# Retail's original intraday shape: quiet overnight, peaks at lunch and late
# evening.
_RETAIL_INTRADAY = (
    0.4, 0.2, 0.1, 0.1, 0.1, 0.2, 0.5, 1.0, 1.8, 2.6, 3.4, 4.2,
    4.8, 4.4, 3.8, 3.6, 4.0, 4.8, 6.0, 7.2, 7.6, 6.4, 3.8, 1.6,
)

RETAIL_CALENDAR = Calendar(
    festival_weights={
        "Diwali": 0.85, "Dussehra": 0.35, "Holi": 0.25, "Eid": 0.30,
        "Pongal": 0.20, "Onam": 0.25, "Christmas": 0.20, "Raksha": 0.15,
    },
)

RETAIL_WORLD = World(
    id="retail",
    start=date(2023, 9, 1),
    end=date(2026, 8, 31),
    regions=REGIONS,
    cities=CITIES,
    products=PRODUCTS,
    channel_devices=CHANNEL_DEVICES,
    region_scale={"West": 1.00, "North": 0.86, "South": 0.78, "East": 0.44},
    channel_share={"app": 0.44, "web": 0.31, "store": 0.25},
    device_share={"mobile": 0.72, "desktop": 0.20, "tablet": 0.08, "pos": 1.00},
    base_daily_orders=520.0,
    annual_growth=0.11,
    noise_sd=0.045,
    calendar=RETAIL_CALENDAR,
    seasonal_phase={"West": 190, "South": 250, "East": 200, "North": 210},
    seasonal_depth={"West": 0.10, "South": 0.05, "East": 0.07, "North": 0.03},
    weather_exposed_channels=("store",),
    intraday=_RETAIL_INTRADAY,
    digital_channels=("web", "app"),
    conversion_by_device={"mobile": 0.041, "desktop": 0.068, "tablet": 0.052},
    local_time_region="East",
    carriers=("BlueDart", "Delhivery", "Ecom", "InHouse"),
    plan_levels=(
        PlanLevel("marketing_spend", "revenue", 0.05, 0.09),
        PlanLevel("planned_stock", "units", 1.05, 1.35),
    ),
    plan_index=PlanIndex("competitor_price_index", 100.0, 3.5, -6.5),
    plan_id_column="promo_id",
    plan_active_column="promo_active",
    plan_event_kinds=("marketing_cut", "competitor_promo"),
    price_event_kinds=("price_change",),
    index_shock_kinds=("competitor_promo",),
    delivery_event_kinds=("external_weather", "stockout"),
    release_kind="internal_bug",
    hazard_kind="external_weather",
    hazard_intensity={"West": 0.62, "South": 0.34, "East": 0.45, "North": 0.20},
    hazard_signal_type="severe_weather",
    hazard_publisher="India Meteorological Department",
    hazard_url="https://mausam.imd.gov.in/",
    orders_per_shipment=6.0,
    late_risk_base=0.09,
)

# Refresh lag per source, as the engine will observe it. Shared across worlds:
# the cadences are a property of the kind of system, not of the industry, and a
# planning extract lands at T+2 whether it is planning promotions or turnarounds.
SOURCE_LAG = {
    "pos_txn": timedelta(hours=3),
    "plan_ops": timedelta(days=2),      # T+2 by design; often breaches its 72h SLA
    "voice_ops": timedelta(minutes=20),
    "ext_signals": timedelta(hours=20),
}
