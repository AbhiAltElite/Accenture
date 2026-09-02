"""Refined petroleum products marketing.

The business sells motor fuels, aviation fuel, LPG, bitumen and lubricants out
of coastal and inland terminals, through three offtake routes and three
dispatch modes. What makes it worth having beside retail is that it barely
controls any of its own numbers. The price is an administered figure that
follows a crude benchmark and an excise notification. The volume that can be
lifted on a given day is set by refinery availability, pipeline integrity and
whether a cyclone has closed a berth.

Two shapes of planted event, deliberately:

**National.** A duty revision or a crude spike lands on all four marketing
regions on the same morning. There is no unexposed region, difference-in-
differences has nothing to compare against, and the honest verdict is
`cannot_verify`. An engine that returned a confident cause here would be wrong.

**Regional.** A turnaround at one refinery, a pipeline section shut, a berth
closed by weather. These have a comparison group and must verify.

Mixing them is the point. A vertical made only of national policy events would
abstain on everything and demonstrate half the engine.
"""

from __future__ import annotations

from datetime import date

from datagen.catalog import City, Product
from datagen.scenarios import CauseKind
from datagen.voices import VoicePack
from datagen.world import Calendar, PlanIndex, PlanLevel, World

# Terminal towns, real coordinates so the hazard feed can be pointed at
# somewhere that exists. Coastal locations carry the berth-closure exposure.
CITIES: tuple[City, ...] = (
    City("Mumbai", "West", 19.0760, 72.8777, 0.44),
    City("Vadodara", "West", 22.3072, 73.1812, 0.31),
    City("Mangalore", "West", 12.9141, 74.8560, 0.25),
    City("Panipat", "North", 29.3909, 76.9635, 0.46),
    City("Mathura", "North", 27.4924, 77.6737, 0.30),
    City("Bathinda", "North", 30.2110, 74.9455, 0.24),
    City("Chennai", "South", 13.0827, 80.2707, 0.43),
    City("Kochi", "South", 9.9312, 76.2673, 0.32),
    City("Visakhapatnam", "South", 17.6868, 83.2185, 0.25),
    City("Haldia", "East", 22.0667, 88.0698, 0.61),
    City("Paradip", "East", 20.3169, 86.6099, 0.39),
)

# Grades, priced per kilolitre. Elasticity is genuinely low for the motor fuels
# -- a duty revision moves the price and barely moves the volume, which is what
# puts the movement in the price leg of the bridge rather than the volume leg.
PRODUCTS: tuple[Product, ...] = (
    Product("MS-91", "motor_fuels", 96_400.0, -0.18),
    Product("HSD-BS6", "motor_fuels", 89_200.0, -0.22),
    Product("XP-95", "motor_fuels", 104_800.0, -0.45),
    Product("ATF-A1", "aviation_fuel", 95_600.0, -0.35),
    Product("LPG-DOM", "lpg", 48_300.0, -0.12),
    Product("LPG-COM", "lpg", 71_900.0, -0.55),
    Product("BIT-VG30", "bitumen", 42_100.0, -0.70),
    Product("BIT-VG40", "bitumen", 46_800.0, -0.65),
    Product("LUB-HD", "lubricants", 181_000.0, -0.90),
    Product("LUB-IND", "lubricants", 154_500.0, -0.85),
    # Commissioned late in the window: a new grade at a new terminal has three
    # weeks of history, which is not enough to build a comparison group. The
    # engine must say so rather than manufacture confidence.
    #
    # Priced well *above* the book average on purpose. A sparse grade priced
    # below it would raise average consignment value when it was withdrawn, so
    # the planted shortfall would surface as a spike and the case would be
    # testing the opposite of what it says it tests.
    Product("LUB-SYN", "lubricants", 236_000.0, -0.95, launched_month=35),
)

CHANNEL_DEVICES: dict[str, tuple[str, ...]] = {
    "retail": ("tank_truck",),                       # a pump is served by road
    "direct": ("tank_truck", "rail", "pipeline"),    # bulk moves any way it can
    "aviation": ("pipeline", "tank_truck"),          # hydrant or bowser
}

VOICES = VoicePack(
    openers=(
        "", "Raising this again. ", "Third time this week. ", "FYI. ",
        "Need help urgently. ", "Logging for record. ",
    ),
    closers=(
        "", " Please advise.", " Customers are waiting.", " Escalating.",
        " Losing sales to the competition next door.",
    ),
    background=(
        "Invoice shows the wrong TIN, please reissue",
        "Requesting revision of the credit limit for next quarter",
        "Nozzle calibration due at the outlet, sending the stamping certificate",
        "Delivery arrived on time and quantity tallied",
        "Please update the bank mandate on the dealer account",
        "Asking for a copy of the last quarter's dispatch statement",
    ),
    typos=((" the ", " teh "), ("truck", "truk"), ("receive", "recieve")),
    # Phrasing the rule vocabulary does contain.
    in_vocabulary={
        CauseKind.REFINERY_TURNAROUND: (
            "no stock at the depot since Monday, allocation cut to half",
            "tank empty at the outlet, we have been rationing since morning",
            "supply delayed again, indent placed Tuesday and nothing yet",
        ),
        CauseKind.PIPELINE_OUTAGE: (
            "pipeline shut, depot says no product till further notice",
            "supply delayed, they are moving everything by tanker now",
            "did not arrive for the second day running",
        ),
        CauseKind.PORT_CLOSURE: (
            "cyclone warning, depot closed and no delivery today",
            "road closed after flooding, truck delayed since yesterday",
            "vessel has not berthed, supply delayed indefinitely",
        ),
        CauseKind.CARRIER_SHORTAGE: (
            "tanker turned away at the gantry, the queue is four hours",
            "could not load, no bay free the whole shift",
            "gantry down since morning, loading halted",
        ),
        CauseKind.DUTY_CHANGE: (
            "price revision came through overnight, customers are arguing",
            "rate revision has cut the margin, please confirm the dealer commission",
        ),
        CauseKind.CRUDE_SPIKE: (
            "price went up again, cheaper at the outlet across the highway",
            "price revision every second day now, hard to hold industrial customers",
        ),
    },
    # Phrasing it does not. Roughly two in five event-driven complaints use
    # these, which is what keeps the with-model comparison a measurement rather
    # than a difference of prose style.
    off_vocabulary={
        CauseKind.REFINERY_TURNAROUND: (
            "we have been running on fumes at the second island all week",
            "they keep saying tomorrow and tomorrow never comes",
            "half the bays are roped off and nobody will say why",
        ),
        CauseKind.PIPELINE_OUTAGE: (
            "everything is coming by road now and it shows in the timings",
            "the line is dry apparently, that is all anyone will tell us",
        ),
        CauseKind.PORT_CLOSURE: (
            "the whole coast is shut, nothing is moving in or out",
            "water is up to the gate, nobody is going anywhere today",
        ),
        CauseKind.CARRIER_SHORTAGE: (
            "our driver sat there from six until eleven and came back empty",
            "the transporter has pulled his fleet onto another contract",
        ),
        CauseKind.DUTY_CHANGE: (
            "the board changed twice before breakfast and customers noticed",
            "what we make on a litre has gone somewhere and nobody explains where",
        ),
        CauseKind.CRUDE_SPIKE: (
            "the man across the road is undercutting us by two rupees",
            "industrial buyers are asking to renegotiate the whole contract",
        ),
    },
    agent_summaries={
        CauseKind.REFINERY_TURNAROUND:
            "Contact summary: {n} dealer calls this shift from {region} about dry "
            "outlets. Common thread is allocation, not demand. Referred to the "
            "supply desk.",
        CauseKind.PIPELINE_OUTAGE:
            "Contact summary: {n} calls from {region} about missed deliveries. "
            "All road-fed since the line went down. Advised revised ETAs.",
        CauseKind.PORT_CLOSURE:
            "Contact summary: {n} calls about undelivered indents in {region}. "
            "Access, not stock. Told dealers we will re-attempt once roads open.",
        CauseKind.CARRIER_SHORTAGE:
            "Contact summary: {n} transporter complaints about gantry queues in "
            "{region}. Escalating to terminal operations.",
        CauseKind.DUTY_CHANGE:
            "Contact summary: {n} dealer queries on the revised rate schedule. "
            "All commercial, none operational. Referred to pricing.",
        CauseKind.CRUDE_SPIKE:
            "Contact summary: {n} calls about competitor pricing in {region}. "
            "Industrial accounts asking to reopen contracts.",
    },
    field_reports={
        CauseKind.REFINERY_TURNAROUND:
            "Terminal report, {region}: allocation running at 55% of indent. "
            "Two of four bays idle. Expect this to hold until the unit is back.",
        CauseKind.PIPELINE_OUTAGE:
            "Terminal report, {region}: sectionalising valve isolated, product "
            "moving by tanker at roughly a third of pipeline throughput.",
        CauseKind.PORT_CLOSURE:
            "Terminal report, {region}: berth closed on port authority advice. "
            "No discharge. Approach roads under water in places.",
        CauseKind.CARRIER_SHORTAGE:
            "Terminal report, {region}: 40% of the contracted tanker fleet did "
            "not report. Gantry throughput down accordingly.",
    },
    incidents={
        CauseKind.REFINERY_TURNAROUND:
            "INC-{num}: Unplanned extension to the {region} refinery turnaround. "
            "Downstream allocation reduced. {n} dealer contacts, {calls} escalated.",
        CauseKind.PIPELINE_OUTAGE:
            "INC-{num}: Product pipeline serving {region} isolated following an "
            "integrity alarm. Road bridging in place. {n} contacts logged.",
        CauseKind.PORT_CLOSURE:
            "INC-{num}: {region} coastal terminals closed on cyclone advisory. "
            "{n} contacts, {calls} escalated. Reopening subject to port clearance.",
        CauseKind.CARRIER_SHORTAGE:
            "INC-{num}: Transporter availability shortfall at {region} terminals. "
            "{n} contacts logged.",
    },
    external_records={
        CauseKind.REFINERY_TURNAROUND:
            "Operations circular {release}: {region} refinery unit returned to "
            "service. Allocation restored to plan with effect from today.",
        CauseKind.PIPELINE_OUTAGE:
            "External notice: pipeline operator confirms the {region} section "
            "recommissioned following inspection. Road bridging stood down.",
        CauseKind.PORT_CLOSURE:
            "External notice: port authority lifts the {region} closure. Berthing "
            "resumes on the normal roster.",
        CauseKind.DUTY_CHANGE:
            "External notice: revised central excise rates on motor fuels take "
            "effect. Retail selling prices amended at all outlets.",
        CauseKind.CRUDE_SPIKE:
            "External notice: import parity benchmark revised sharply upward "
            "following the crude move. Pricing committee notified.",
    },
    # A refinery turnaround is the one whose closing record is filed as an
    # operations circular, which is the doc type the candidate scanner reads as
    # a `release_log`.
    release_kind=CauseKind.REFINERY_TURNAROUND,
    release_label="OC-2026-14",
)

PETROLEUM_WORLD = World(
    id="petroleum",
    start=date(2023, 9, 1),
    end=date(2026, 8, 31),
    regions=("North", "South", "East", "West"),
    cities=CITIES,
    products=PRODUCTS,
    channel_devices=CHANNEL_DEVICES,
    region_scale={"West": 1.00, "North": 0.81, "South": 0.74, "East": 0.52},
    channel_share={"retail": 0.58, "direct": 0.30, "aviation": 0.12},
    device_share={"tank_truck": 0.66, "rail": 0.19, "pipeline": 0.15},
    base_daily_orders=880.0,
    annual_growth=0.04,          # fuel demand grows slowly
    noise_sd=0.038,
    calendar=Calendar(
        # Fuel sees festival *travel*, which is a real but much smaller effect
        # than a shopping run-up, and it does not collapse afterwards the way
        # retail demand does.
        festival_weights={"Diwali": 0.22, "Dussehra": 0.12, "Holi": 0.10,
                          "Eid": 0.10, "Christmas": 0.08},
        build_up_days=10,
        hangover_days=4,
        hangover_depth=0.10,
        # Industrial and bulk offtake is a weekday business; the weekend dips.
        weekday=(1.06, 1.08, 1.07, 1.05, 1.02, 0.88, 0.84),
    ),
    # The monsoon suppresses bitumen and construction offtake and closes coastal
    # berths. Same phases as retail: it is the same monsoon.
    seasonal_phase={"West": 190, "South": 250, "East": 200, "North": 210},
    seasonal_depth={"West": 0.13, "South": 0.08, "East": 0.11, "North": 0.05},
    weather_exposed_channels=("direct",),   # bulk construction offtake stops
    # Kilolitres per consignment: a road tanker is about twelve, and the premium
    # lubricant lots are smaller.
    basket_intercept=14.0,
    basket_divisor=25_000.0,
    basket_min=6.0,
    basket_max=13.5,
    # A loading gantry's day: a pre-dawn start, a long flat shift, a second
    # evening peak. Much flatter than a retail browsing curve, and never zero,
    # because bulk lifting runs through the night.
    intraday=(1.2, 1.0, 0.9, 0.9, 1.4, 2.8, 4.4, 5.6, 6.2, 6.0, 5.6, 5.2,
              4.6, 4.8, 5.2, 5.6, 5.8, 6.0, 5.4, 4.4, 3.4, 2.6, 2.0, 1.5),
    # Only road and rail lifting passes a gantry and produces a scheduled-versus-
    # loaded rate. Pipeline movement has no gantry, so it is excluded exactly the
    # way store sales are excluded from checkout conversion.
    digital_channels=("retail", "direct"),
    # Pipeline movement is deliberately absent rather than set to zero: it does
    # not cross a gantry, so it has no rate, which is not the same as a rate of
    # nought. A device with no entry here emits no scheduling rows at all.
    conversion_by_device={"tank_truck": 0.052, "rail": 0.088},
    local_time_region="East",
    carriers=("IndTrans", "Coastal Carriers", "Bharat Roadways", "InHouse"),
    plan_levels=(
        PlanLevel("logistics_spend", "revenue", 0.02, 0.04),
        PlanLevel("planned_allocation", "units", 1.02, 1.28),
    ),
    plan_index=PlanIndex("import_parity_index", 100.0, 4.2, 7.5),
    plan_id_column="plan_id",
    plan_active_column="plan_active",
    plan_event_kinds=(CauseKind.CRUDE_SPIKE, CauseKind.CARRIER_SHORTAGE),
    price_event_kinds=(CauseKind.DUTY_CHANGE, CauseKind.CRUDE_SPIKE),
    index_shock_kinds=(CauseKind.CRUDE_SPIKE,),
    delivery_event_kinds=(CauseKind.PORT_CLOSURE, CauseKind.PIPELINE_OUTAGE),
    release_kind=CauseKind.REFINERY_TURNAROUND,
    voices=VOICES,
    # A fuel marketer posts to SAP FI-CO; the marketing company code is what a
    # terminal's sales land in.
    ledger_name="sap_fico_marketing",
    hazard_kind=CauseKind.PORT_CLOSURE,
    hazard_intensity={"West": 0.58, "South": 0.40, "East": 0.66, "North": 0.14},
    hazard_signal_type="port_closure",
    hazard_publisher="India Meteorological Department (Cyclone Warning Division)",
    hazard_url="https://mausam.imd.gov.in/",
    orders_per_shipment=1.0,     # one consignment is one movement
    late_risk_base=0.07,
    seed=20260829,
)
