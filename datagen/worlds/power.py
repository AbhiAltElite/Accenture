"""Electricity generation and dispatch.

A generator does not choose how much it sells. A load despatch centre schedules
it against a merit order, a regulator sets the tariff it is paid, a fuel supply
agreement decides whether the coal rakes arrive, and the weather decides both
what the solar and wind fleet contributes and what the demand is in the first
place. The one genuinely internal driver is plant availability, and even that
is dominated by fuel supply rather than by anything the operator did.

Dispatch is natively hourly, which is why the hourly contract in this vertical
is the grain the industry actually reports on rather than a construction.

The same two shapes as petroleum. A regulatory tariff order moves a number for
every region at once and must come back `cannot_verify`; a fuel rake shortfall,
a transmission constraint or a unit trip is regional and must verify.
"""

from __future__ import annotations

from datetime import date

from datagen.catalog import City, Product
from datagen.scenarios import CauseKind
from datagen.voices import VoicePack
from datagen.world import Calendar, PlanIndex, PlanLevel, World

# Grid regions as the Indian system is actually organised, with a
# representative generating hub in each.
CITIES: tuple[City, ...] = (
    City("Mundra", "West", 22.8394, 69.7219, 0.40),
    City("Korba", "West", 22.3595, 82.7501, 0.35),
    City("Chandrapur", "West", 19.9615, 79.2961, 0.25),
    City("Singrauli", "North", 24.1997, 82.6739, 0.44),
    City("Dadri", "North", 28.5556, 77.5556, 0.32),
    City("Bhakra", "North", 31.4110, 76.4335, 0.24),
    City("Ramagundam", "South", 18.7594, 79.4744, 0.41),
    City("Neyveli", "South", 11.5433, 79.4800, 0.33),
    City("Kudgi", "South", 16.4700, 76.1200, 0.26),
    City("Farakka", "East", 24.8040, 87.9110, 0.58),
    City("Talcher", "East", 20.9500, 85.2333, 0.42),
)

# Stations, priced per MWh. Renewables are must-run and near-zero marginal cost;
# gas peaking is expensive and only dispatched when it has to be.
PRODUCTS: tuple[Product, ...] = (
    Product("STN-COAL-1", "coal", 4_120.0, -0.20),
    Product("STN-COAL-2", "coal", 3_880.0, -0.24),
    Product("STN-COAL-3", "coal", 4_460.0, -0.18),
    Product("STN-GAS-1", "gas", 7_240.0, -0.95),
    Product("STN-GAS-2", "gas", 6_680.0, -0.88),
    Product("STN-HYD-1", "hydro", 3_150.0, -0.35),
    Product("STN-HYD-2", "hydro", 2_960.0, -0.30),
    Product("STN-SOL-1", "solar", 2_450.0, -0.10),
    Product("STN-SOL-2", "solar", 2_380.0, -0.10),
    Product("STN-WND-1", "wind", 2_920.0, -0.12),
    # Commissioned late in the window. A station with three weeks of generation
    # history has no comparison group, and the engine must say so.
    Product("STN-SOL-3", "solar", 2_310.0, -0.10, launched_month=35),
)

CHANNEL_DEVICES: dict[str, tuple[str, ...]] = {
    "ppa": ("base_load", "must_run"),        # long-term contracted offtake
    "exchange": ("peaking", "base_load"),    # sold into the spot market
    "banking": ("base_load",),               # returned in kind later
}

VOICES = VoicePack(
    openers=(
        "", "Reporting for the shift. ", "Second occurrence today. ",
        "For the log. ", "Urgent, please advise. ",
    ),
    closers=(
        "", " Please confirm.", " Escalating to the RLDC.",
        " Revised declaration to follow.", " Awaiting instruction.",
    ),
    background=(
        "Monthly energy accounting statement reconciled, no exceptions",
        "Requesting revision of the annual maintenance window",
        "Meter testing completed at the interface point, report attached",
        "Auxiliary consumption within the normative band this fortnight",
        "Please confirm the revised open access nomination format",
        "Routine protection audit closed with no observations",
    ),
    typos=((" the ", " teh "), ("schedule", "schedual"), ("received", "recieved")),
    in_vocabulary={
        CauseKind.PLANT_OUTAGE: (
            "unit tripped on boiler protection, machine off bar since 0340",
            "forced outage on the turbine, generation lost for the shift",
            "unit could not sync after the trip, still off bar",
        ),
        CauseKind.FUEL_SHORTAGE: (
            "coal stock down to critical stock, rake not received for three days",
            "fuel shortage against linkage, backing down to preserve stock",
            "gas supply curtailed by the supplier, declared capacity revised",
        ),
        CauseKind.GRID_CONSTRAINT: (
            "backed down on grid constraint, evacuation constraint on the corridor",
            "curtailed by the load despatch centre, transmission constraint",
            "line outage on the export corridor, generation curtailed",
        ),
        CauseKind.MERIT_ORDER_SHIFT: (
            "schedule revised downward, cheaper generation ahead of us in merit",
            "nomination rejected on the exchange, scheduling hold in place",
        ),
        CauseKind.TARIFF_ORDER: (
            "tariff order notified, rate schedule changes from this billing cycle",
            "true-up allowed only in part, regulatory order attached",
        ),
        CauseKind.HEAT_WAVE: (
            "deviation settlement exposure high, frequency deviation all afternoon",
            "load shed instructed in pockets, demand well over the forecast",
        ),
    },
    off_vocabulary={
        CauseKind.PLANT_OUTAGE: (
            "the machine came off in the small hours and has not gone back",
            "we lost the set on protection and are still boxing it up",
        ),
        CauseKind.FUEL_SHORTAGE: (
            "we are down to about four days in the yard and nothing is moving",
            "the supplier has cut us again with no notice at all",
        ),
        CauseKind.GRID_CONSTRAINT: (
            "they have told us to come down again, the corridor is full",
            "we are being held at half load for reasons upstream of us",
        ),
        CauseKind.MERIT_ORDER_SHIFT: (
            "cheaper sets have come in ahead of us and we are sitting idle",
            "our block did not clear this morning and nobody warned us",
        ),
        CauseKind.TARIFF_ORDER: (
            "the numbers we bill against have moved and not in our favour",
            "the commission has disallowed most of what we claimed",
        ),
        CauseKind.HEAT_WAVE: (
            "it has been well over forty all week and the system is straining",
            "demand has run ahead of anything in the forecast for five days",
        ),
    },
    agent_summaries={
        CauseKind.PLANT_OUTAGE:
            "Shift summary: {n} entries this shift for the {region} station on "
            "the forced outage. Boiler side. Restoration estimate awaited.",
        CauseKind.FUEL_SHORTAGE:
            "Shift summary: {n} entries on fuel position in {region}. Stock "
            "critical at two stations. Backing down to conserve.",
        CauseKind.GRID_CONSTRAINT:
            "Shift summary: {n} curtailment instructions received for {region}. "
            "All corridor-related, none plant-related.",
        CauseKind.MERIT_ORDER_SHIFT:
            "Shift summary: {n} schedule revisions for {region}. Displacement by "
            "cheaper generation, no availability issue at our end.",
        CauseKind.TARIFF_ORDER:
            "Shift summary: {n} commercial queries following the tariff order. "
            "None operational. Referred to regulatory affairs.",
        CauseKind.HEAT_WAVE:
            "Shift summary: {n} entries on demand overshoot in {region}. "
            "Deviation exposure flagged to the trading desk.",
    },
    field_reports={
        CauseKind.PLANT_OUTAGE:
            "Station report, {region}: unit off bar following a protection "
            "operation. Declared capacity revised to zero for the unit.",
        CauseKind.FUEL_SHORTAGE:
            "Station report, {region}: coal stock at four days against a "
            "normative twenty. Rakes short against programme. Load restricted.",
        CauseKind.GRID_CONSTRAINT:
            "Station report, {region}: held at reduced load on despatch "
            "instruction. Corridor loading at limit.",
        CauseKind.HEAT_WAVE:
            "System report, {region}: peak demand above forecast for a fifth "
            "consecutive day. Reserve margin thin through the afternoon.",
    },
    incidents={
        CauseKind.PLANT_OUTAGE:
            "INC-{num}: Forced outage at the {region} station. {n} log entries, "
            "{calls} escalated. Scheduled generation revised for the period.",
        CauseKind.FUEL_SHORTAGE:
            "INC-{num}: Fuel stock critical at {region} stations following short "
            "rake receipt. {n} entries logged. Declared capacity reduced.",
        CauseKind.GRID_CONSTRAINT:
            "INC-{num}: Sustained curtailment of {region} generation on "
            "transmission constraint. {n} instructions received.",
        CauseKind.HEAT_WAVE:
            "INC-{num}: Demand overshoot across {region} during the heat wave. "
            "{n} entries, {calls} escalated to the trading desk.",
    },
    external_records={
        CauseKind.PLANT_OUTAGE:
            "Despatch circular {release}: {region} unit synchronised and "
            "returned to bar. Declared capacity restored to normative.",
        CauseKind.FUEL_SHORTAGE:
            "External notice: fuel supplier confirms rake programme restored for "
            "{region}. Stock rebuilding from today.",
        CauseKind.GRID_CONSTRAINT:
            "External notice: transmission licensee confirms the {region} "
            "corridor outage closed. Curtailment instruction withdrawn.",
        CauseKind.TARIFF_ORDER:
            "External notice: the commission's tariff order takes effect. "
            "Rate schedules amended for all long-term contracted offtake.",
        CauseKind.MERIT_ORDER_SHIFT:
            "External notice: revised merit order stack published. Marginal "
            "clearing price moved sharply against the thermal fleet.",
    },
    release_kind=CauseKind.PLANT_OUTAGE,
    release_label="DC-2026-31",
)

POWER_WORLD = World(
    id="power",
    start=date(2023, 9, 1),
    end=date(2026, 8, 31),
    regions=("North", "South", "East", "West"),
    cities=CITIES,
    products=PRODUCTS,
    channel_devices=CHANNEL_DEVICES,
    region_scale={"West": 1.00, "North": 0.94, "South": 0.88, "East": 0.61},
    channel_share={"ppa": 0.68, "exchange": 0.21, "banking": 0.11},
    device_share={"base_load": 0.74, "peaking": 0.14, "must_run": 0.12},
    base_daily_orders=1_240.0,   # scheduled blocks
    annual_growth=0.06,
    noise_sd=0.032,
    calendar=Calendar(
        # A generator barely notices the shopping year. Industry shuts for a few
        # days around the big festivals, which *reduces* demand -- so the weights
        # are small and the sign of the effect comes through the hangover.
        festival_weights={"Diwali": 0.06, "Holi": 0.04},
        build_up_days=4,
        hangover_days=3,
        hangover_depth=0.35,
        # Demand is flat Monday to Saturday and falls on Sunday when industry is
        # off. Nothing like a retail weekend.
        weekday=(1.03, 1.04, 1.04, 1.03, 1.02, 0.98, 0.86),
    ),
    # The summer peak, not the monsoon: depth is negative because this season
    # *lifts* demand rather than suppressing it. Peaks in May (day 140) in the
    # north and west, later and milder in the south.
    seasonal_phase={"West": 140, "South": 160, "East": 145, "North": 135},
    seasonal_depth={"West": -0.22, "South": -0.14, "East": -0.17, "North": -0.28},
    weather_exposed_channels=("exchange",),   # spot demand swings hardest
    # MWh per scheduled block. Base-load blocks are large and uniform; the
    # expensive peaking stations clear in smaller quantities.
    basket_intercept=62.0,
    basket_divisor=180.0,
    basket_min=18.0,
    basket_max=48.0,
    # The system load curve: a morning agricultural and industrial rise, a dip
    # through the afternoon as solar displaces thermal, and the evening peak
    # after sunset when it does not. Never near zero.
    intraday=(3.2, 2.9, 2.7, 2.7, 2.9, 3.4, 4.0, 4.4, 4.6, 4.4, 4.2, 4.0,
              3.8, 3.7, 3.8, 4.1, 4.6, 5.6, 6.8, 7.2, 6.6, 5.6, 4.6, 3.8),
    # Contracted and exchange offtake is scheduled block by block, so it has a
    # scheduled-versus-delivered rate. Banking is settled in energy terms later
    # and has no block-level schedule, so it is excluded.
    digital_channels=("ppa", "exchange"),
    # Fulfilment against declaration, not against a physical maximum. Kept well
    # clear of 1.0 on purpose: the East extract lands in local time, and a rate
    # already at 0.93 would be pushed above unity by that five-and-a-half hour
    # shift -- a nonsense figure rather than a visible data defect.
    conversion_by_device={"base_load": 0.720, "peaking": 0.580, "must_run": 0.790},
    local_time_region="East",
    carriers=("PowerGrid", "State Transco", "Private Licensee", "InHouse"),
    plan_levels=(
        PlanLevel("fuel_cost", "revenue", 0.30, 0.44),
        PlanLevel("declared_capacity", "units", 1.04, 1.22),
    ),
    plan_index=PlanIndex("market_clearing_index", 100.0, 6.8, -9.0),
    plan_id_column="plan_id",
    plan_active_column="plan_active",
    plan_event_kinds=(CauseKind.MERIT_ORDER_SHIFT, CauseKind.FUEL_SHORTAGE),
    price_event_kinds=(CauseKind.TARIFF_ORDER, CauseKind.MERIT_ORDER_SHIFT),
    index_shock_kinds=(CauseKind.MERIT_ORDER_SHIFT,),
    # Everything that stops declared energy reaching the grid shows up in the
    # settlement outcomes: a corridor constraint, a fuel shortfall, a unit off
    # bar, and a heat wave that takes the reserve margin with it. Leaving the
    # last two out made both signal-gap cases undetectable, because the metric
    # they are planted against is built from exactly this table.
    delivery_event_kinds=(
        CauseKind.GRID_CONSTRAINT,
        CauseKind.FUEL_SHORTAGE,
        CauseKind.PLANT_OUTAGE,
        CauseKind.HEAT_WAVE,
    ),
    release_kind=CauseKind.PLANT_OUTAGE,
    voices=VOICES,
    # A generator's revenue is settled through regional energy accounting before
    # it reaches the general ledger, which is why the two disagree at all.
    ledger_name="energy_accounting_gl",
    hazard_kind=CauseKind.HEAT_WAVE,
    hazard_intensity={"West": 0.54, "South": 0.38, "East": 0.44, "North": 0.68},
    hazard_signal_type="heat_wave",
    hazard_publisher="India Meteorological Department (Heat Wave Warning)",
    hazard_url="https://mausam.imd.gov.in/",
    orders_per_shipment=1.0,
    late_risk_base=0.055,
    seed=20260830,
)
