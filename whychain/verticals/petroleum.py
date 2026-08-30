"""Refined petroleum products marketing: a business moved from outside itself.

Retail's metrics move because of things the business did -- a release, a price
change, a stockout, a campaign. This one mostly does not. The price of motor
fuel is an administered number that follows a crude benchmark and an excise
notification; the volume that can be lifted on any given day is set by refinery
availability, pipeline integrity and whether a cyclone has closed a coastal
berth. Almost nothing on that list appears in an internal log until after it has
already happened, which is precisely why the external signal feed and the
signal-gap stage carry more weight here than they do in retail.

One consequence is worth stating plainly rather than hiding. A national excise
revision lands on every marketing region on the same morning, so there is no
unexposed region to compare against and difference-in-differences genuinely
cannot verify it. The correct answer there is `cannot_verify`, not a cause, and
the planted scenarios deliberately mix national policy events that must abstain
with regional ones -- a pipeline shutdown, a berth closure, a refinery
turnaround -- that must verify. An engine that returned a confident cause for
the national ones would be wrong in the way this whole design exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

from whychain.actions import DriverMap, RecoveryModel
from whychain.corroborate import Corpus, Vocabulary
from whychain.verify.candidates import PlanSpec
from whychain.verticals.spec import PlanColumns, Vertical

# Issue codes, in the same five roles retail uses: a pair for "the transaction
# could not be completed", a pair for "the product did not arrive", then price,
# quality and the residual. Keeping the roles lets the related-issue map say the
# same thing it says in retail -- a lifting problem should produce lifting
# complaints, and if it produced only supply complaints the notes are about
# something else.
GANTRY_FAILURE = "gantry_failure"
DOCUMENTATION_HOLD = "documentation_hold"
SUPPLY_DELAY = "supply_delay"
STOCK_DRY_OUT = "stock_dry_out"
PRICE_REVISION = "price_revision"
QUALITY_OFFSPEC = "quality_offspec"
OTHER = "other"

VOCABULARY = Vocabulary(
    issue_terms=(
        (GANTRY_FAILURE,
         ("gantry down", "loading arm", "loading bay", "could not load",
          "unable to load", "gantry queue", "loading halted", "bay closed",
          "meter fault", "tanker turned away")),
        (DOCUMENTATION_HOLD,
         ("invoice not generated", "indent rejected", "delivery order",
          "documentation hold", "e-way bill", "credit limit", "payment gateway",
          "indent could not")),
        (SUPPLY_DELAY,
         ("truck delayed", "arrived late", "did not arrive", "no delivery",
          "supply delayed", "rake delayed", "pipeline shut", "pipeline down",
          "berth", "vessel", "cyclone", "flooding", "road closed",
          "depot closed", "no update for")),
        (STOCK_DRY_OUT,
         ("dry out", "dried out", "ran out", "nil stock", "no stock",
          "tank empty", "out of stock", "allocation cut", "rationing",
          # How the *operational* record says the same thing. A dealer writes
          # "allocation cut to half"; the terminal writes "allocation reduced to
          # 55 per cent of indent" and the field report writes "allocation
          # running at 55% of indent". Without these the note describing a
          # turnaround classified as the residual, and the tickets that
          # corroborate it were discarded unread.
          "allocation reduced", "allocation running", "allocation restricted",
          "of indent", "short supply")),
        (PRICE_REVISION,
         ("price revision", "rate revision", "duty change", "excise",
          "price went up", "cheaper at", "margin", "dealer commission")),
        (QUALITY_OFFSPEC,
         ("off-spec", "off spec", "contaminated", "water in", "density",
          "flash point", "quality was", "sediment")),
    ),
    scope_terms={
        "channel": {
            "retail outlet": "retail", "petrol pump": "retail", "pump": "retail",
            "dealer": "retail", "direct": "direct", "industrial": "direct",
            "bulk": "direct", "consumer pump": "direct",
            "aviation": "aviation", "afs": "aviation", "airport": "aviation",
        },
        "device": {
            "tank truck": "tank_truck", "tanker": "tank_truck", "truck": "tank_truck",
            "rake": "rail", "rail": "rail", "wagon": "rail",
            "pipeline": "pipeline", "pumping": "pipeline",
        },
        "category": {
            "petrol": "motor_fuels", "diesel": "motor_fuels", "hsd": "motor_fuels",
            "ms ": "motor_fuels", "motor spirit": "motor_fuels",
            "atf": "aviation_fuel", "jet fuel": "aviation_fuel",
            "lpg": "lpg", "cylinder": "lpg",
            "bitumen": "bitumen", "lubricant": "lubricants", "lube": "lubricants",
        },
    },
    residual_issue=OTHER,
)

CORPUS = Corpus(
    related_issues={
        GANTRY_FAILURE: (GANTRY_FAILURE, DOCUMENTATION_HOLD),
        DOCUMENTATION_HOLD: (DOCUMENTATION_HOLD, GANTRY_FAILURE),
        SUPPLY_DELAY: (SUPPLY_DELAY, STOCK_DRY_OUT),
        STOCK_DRY_OUT: (STOCK_DRY_OUT, SUPPLY_DELAY),
        PRICE_REVISION: (PRICE_REVISION,),
        QUALITY_OFFSPEC: (QUALITY_OFFSPEC,),
        OTHER: (),
    },
    # Words that belong to the operational record rather than to the dealer or
    # consignee affected by it. A dealer writes about a tanker that never came,
    # never about the turnaround plan that stopped it.
    not_in_complaints=(
        "turnaround", "circular", "notification", "schedule", "allocation plan",
        "benchmark", "parity", "sop", "process", "planning", "advisory",
    ),
    vocabulary=VOCABULARY,
)

DRIVERS = DriverMap(
    kind_to_driver={
        # A terminal or refinery circular announcing a unit trip or a shutdown.
        "release_log": "refinery_availability",
        # A planned turnaround carried in the weekly plan.
        "turnaround": "refinery_availability",
    },
    note_to_driver=(
        (("pipeline", "pumping", "leak", "integrity", "sectionalis"), "pipeline_integrity"),
        (("turnaround", "shutdown", "unit trip", "refinery", "maintenance"),
         "refinery_availability"),
        (("duty", "excise", "levy", "price revision", "rate revision"), "excise_duty"),
        (("cyclone", "storm", "berth", "port closed", "flood", "weather"),
         "port_closure"),
        (("tanker", "transporter", "haulage", "fleet", "carrier", "rake"),
         "carrier_capacity"),
        (("crude", "benchmark", "brent", "parity"), "crude_benchmark"),
    ),
    note_kind="ops_note",
)

PLAN = PlanSpec(
    id_column="plan_id",
    active_column="plan_active",
    kind="turnaround",
    noun="Turnaround",
)

RECOVERY = RecoveryModel(
    # What each lever recovers of the loss its cause was measured to account
    # for. Lower across the board than retail's, because most of what moves this
    # business cannot be reversed at all: an excise revision stands, a crude
    # move stands, and the only question is how much of the consequence can be
    # routed around.
    share={
        "alternate_sourcing": 0.45,   # another refinery, at a longer haul
        "mode_switch": 0.60,          # road bridging round a shut pipeline
        "fleet_augmentation": 0.70,   # spot tankers clear a gantry queue quickly
        "pricing_revision": 0.25,     # a dealer commission change moves little
        "allocation_mix": 0.40,
    },
    reversal_id="alternate_sourcing",
    reversal_driver="refinery_availability",
    reversal_kind="release_log",      # the operations circular
    reversal_lever="alternate_sourcing",
    reversal_question="What happens if we source the shortfall from another "
                      "refinery now?",
    reversal_absent="no refinery availability event survived causal testing in "
                    "this window, so there is nothing measured to re-source",
    reversal_caveat="an alternate source covers the volume but at a longer haul, "
                    "and the liftings already missed do not come back",
    price_driver="excise_duty",
    price_noun="the administered price",
    external_kinds=("ops_note", "turnaround"),
)

PETROLEUM = Vertical(
    id="petroleum",
    label="Petroleum marketing",
    tagline="Refined product marketing across four regions and three offtake routes",
    driven_by="Almost entirely external: crude benchmarks, excise notifications, "
              "refinery turnarounds, pipeline integrity and port closures",
    graph_summary=(
        "Five connected metrics across three sources. Realisation is consignments times average consignment value; consignments come from what the gantry schedules and what it actually loads. The price leg is an administered number, so a movement there is a movement caused from outside the business."
    ),
    contracts_dir=Path("contracts/petroleum"),
    warehouse=Path("data/warehouse/petroleum.duckdb"),
    headline_kpi="net_realisation",
    dimensions={
        "region": "Marketing region",
        "channel": "Offtake route",
        "device": "Dispatch mode",
        "category": "Product family",
        "sku": "Grade",
    },
    corpus=CORPUS,
    drivers=DRIVERS,
    plan=PLAN,
    recovery=RECOVERY,
    plan_columns=PlanColumns(
        levels=("logistics_spend", "planned_allocation"),
        index="import_parity_index",
    ),
)
