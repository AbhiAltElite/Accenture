"""Electricity generation and dispatch: an industry whose day is set for it.

A generator does not choose how much it sells. A load despatch centre schedules
it, a regulator sets the tariff it is paid, a fuel supply agreement decides
whether the coal arrives, and the weather decides what the solar and wind
capacity contributes and what the demand is. The one genuinely internal driver
is plant availability, and even that is dominated by fuel supply rather than by
anything the operator did.

Two things make this vertical worth having beside petroleum. Dispatch is
natively half-hourly, so the hourly contract stops being a contrivance and
becomes the grain the industry actually reports on. And the external drivers
here are regulatory and physical rather than fiscal -- a tariff order, a grid
constraint, a fuel rake that did not arrive -- so the two externally-driven
verticals are not the same story told twice.
"""

from __future__ import annotations

from pathlib import Path

from whychain.actions import DriverMap
from whychain.corroborate import Corpus, Vocabulary
from whychain.verify.candidates import PlanSpec
from whychain.verticals.spec import PlanColumns, Vertical

# The same five roles again: a pair for "the dispatch could not be completed",
# a pair for "the energy did not arrive", then tariff, quality and residual.
DISPATCH_FAILURE = "dispatch_failure"
SCHEDULING_HOLD = "scheduling_hold"
FUEL_SHORTAGE = "fuel_shortage"
CURTAILMENT = "curtailment"
TARIFF_REVISION = "tariff_revision"
QUALITY_DEVIATION = "quality_deviation"
OTHER = "other"

VOCABULARY = Vocabulary(
    issue_terms=(
        (DISPATCH_FAILURE,
         ("unit tripped", "trip", "forced outage", "boiler", "turbine",
          "could not sync", "generation lost", "machine off bar", "off bar")),
        (SCHEDULING_HOLD,
         ("schedule revised", "revision not accepted", "declared capacity",
          "dc revision", "scheduling hold", "nomination rejected",
          "open access denied", "no-objection")),
        (FUEL_SHORTAGE,
         ("coal stock", "fuel shortage", "rake not received", "rakes short",
          "gas supply", "critical stock", "supercritical stock", "linkage",
          "fuel supply agreement")),
        (CURTAILMENT,
         ("curtailed", "backing down", "backed down", "grid constraint",
          "transmission constraint", "line outage", "evacuation constraint",
          "load shed", "must-run cut")),
        (TARIFF_REVISION,
         ("tariff order", "tariff revision", "true-up", "regulatory order",
          "rate schedule", "surcharge")),
        (QUALITY_DEVIATION,
         ("frequency deviation", "voltage", "reactive", "deviation settlement",
          "power factor", "harmonics")),
    ),
    scope_terms={
        "channel": {
            "long-term ppa": "ppa", "ppa": "ppa", "long term": "ppa",
            "exchange": "exchange", "iex": "exchange", "spot": "exchange",
            "banking": "banking", "bilateral": "banking",
        },
        "device": {
            "base load": "base_load", "baseload": "base_load",
            "peaking": "peaking", "peaker": "peaking",
            "must-run": "must_run", "must run": "must_run",
        },
        "category": {
            "coal": "coal", "thermal": "coal", "boiler": "coal",
            "gas": "gas", "ccgt": "gas",
            "hydro": "hydro", "reservoir": "hydro",
            "solar": "solar", "pv": "solar",
            "wind": "wind", "turbine blade": "wind",
        },
    },
    residual_issue=OTHER,
)

CORPUS = Corpus(
    related_issues={
        DISPATCH_FAILURE: (DISPATCH_FAILURE, SCHEDULING_HOLD),
        SCHEDULING_HOLD: (SCHEDULING_HOLD, DISPATCH_FAILURE),
        FUEL_SHORTAGE: (FUEL_SHORTAGE, CURTAILMENT),
        CURTAILMENT: (CURTAILMENT, FUEL_SHORTAGE),
        TARIFF_REVISION: (TARIFF_REVISION,),
        QUALITY_DEVIATION: (QUALITY_DEVIATION,),
        OTHER: (),
    },
    not_in_complaints=(
        "circular", "notification", "merit order", "outage plan", "schedule",
        "regulation", "sop", "process", "planning", "advisory", "benchmark",
    ),
    vocabulary=VOCABULARY,
)

DRIVERS = DriverMap(
    kind_to_driver={
        # A load despatch or plant circular: a trip notice, a constraint bulletin.
        "release_log": "plant_availability",
        # A planned outage carried in the weekly plan.
        "outage": "plant_availability",
    },
    note_to_driver=(
        (("coal", "rake", "linkage", "fuel", "gas supply"), "fuel_supply"),
        (("constraint", "backing down", "curtail", "evacuation", "line outage"),
         "grid_constraint"),
        (("tariff", "true-up", "regulatory order", "surcharge"), "tariff_order"),
        (("trip", "boiler", "off bar", "forced outage", "overhaul"),
         "plant_availability"),
        (("monsoon", "cyclone", "heat wave", "wind speed", "irradiance", "weather"),
         "weather_load"),
        (("demand", "load curve", "peak deficit"), "demand_shift"),
    ),
    note_kind="ops_note",
)

PLAN = PlanSpec(
    id_column="plan_id",
    active_column="plan_active",
    kind="outage",
    noun="Outage",
)

POWER = Vertical(
    id="power",
    label="Power generation",
    tagline="Generation and dispatch across four grid regions and three offtake routes",
    driven_by="Set from outside: regulatory tariff orders, fuel supply, grid "
              "constraints, merit order and weather-driven load",
    graph_summary=(
        "Five connected metrics across three sources. Realisation is scheduled blocks times average realised tariff; blocks come from what is declared and what the grid actually takes. Both legs are set elsewhere — one by a regulator, the other by a merit order."
    ),
    contracts_dir=Path("contracts/power"),
    warehouse=Path("data/warehouse/power.duckdb"),
    ground_truth=Path("data/ground_truth/power/cases.json"),
    headline_kpi="dispatch_realisation",
    dimensions={
        "region": "Grid region",
        "channel": "Offtake route",
        "device": "Unit class",
        "category": "Fuel",
        "sku": "Station",
    },
    corpus=CORPUS,
    drivers=DRIVERS,
    plan=PLAN,
    plan_columns=PlanColumns(
        levels=("fuel_cost", "declared_capacity"),
        index="market_clearing_index",
    ),
)
