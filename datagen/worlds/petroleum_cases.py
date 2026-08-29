"""Labelled cases for the petroleum vertical.

The mix is the argument. Two of these are national policy events that a correct
engine *cannot* verify -- an excise revision lands on every marketing region on
the same morning, so there is no unexposed region and difference-in-differences
has nothing to compare against. Four are regional and must verify. A vertical
made only of the first kind would abstain on everything; one made only of the
second would never show the abstention that makes the rest trustworthy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from datagen.scenarios import (
    AvailableSignal,
    CauseKind,
    ExpectedVerdict,
    PlantedEvent,
    Scenario,
    Slice,
)

# --- 1. Two causes at once, in one region, with a decoy that ran in two ------
MULTI_FACTOR = Scenario(
    case_id="pet-01-multi-factor",
    kpi_id="net_realisation",
    window_start=date(2026, 7, 22),
    window_end=date(2026, 8, 19),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            "TA-4411", CauseKind.REFINERY_TURNAROUND,
            date(2026, 8, 13), date(2026, 8, 15),
            Slice(region="West"), -0.21,
            description="Turnaround at the West refinery extended by nine days; "
                        "downstream allocation reduced to 55 per cent of indent",
        ),
        PlantedEvent(
            "CR-2208", CauseKind.CARRIER_SHORTAGE,
            date(2026, 8, 14), date(2026, 8, 15),
            Slice(region="West", device="tank_truck"), -0.09,
            description="Contracted tanker fleet availability shortfall at West "
                        "terminals; gantry throughput down",
        ),
    ),
    decoys=(
        # Recorded in the West and the East at the same time. The East was fine,
        # which is what gives the causal test something to bite on.
        PlantedEvent(
            "IP-9002", CauseKind.CRUDE_SPIKE,
            date(2026, 8, 12), date(2026, 8, 16),
            Slice(region="West"), 0.0, is_decoy=True, also_in=("East",),
            description="Import parity benchmark revised upward across West and East",
        ),
    ),
    notes="Two real causes in one region and a benchmark move that correlates "
          "with both and caused neither.",
    tags=("multi-factor", "decoy"),
)

# --- 2. A national excise revision: real, and genuinely untestable -----------
NATIONAL_POLICY = Scenario(
    case_id="pet-02-national-duty",
    kpi_id="net_realisation",
    window_start=date(2026, 5, 4),
    window_end=date(2026, 6, 1),
    expected=ExpectedVerdict.CANNOT_VERIFY,
    causes=(
        PlantedEvent(
            "EX-2026-07", CauseKind.DUTY_CHANGE,
            date(2026, 5, 18), date(2026, 5, 22),
            Slice(),                       # every region, no control group
            -0.11,
            description="Revised central excise rates on motor fuels take effect "
                        "at all outlets nationally",
        ),
    ),
    notes="The movement is real and the cause is known, but it happened "
          "everywhere at once. There is no unexposed region, so the causal test "
          "cannot separate it from anything else that week. `cannot_verify` is "
          "the correct answer and a confident cause would be wrong.",
    tags=("national", "no-control-group", "abstention"),
)

# --- 3. A grade commissioned three weeks ago --------------------------------
SPARSE_HISTORY = Scenario(
    case_id="pet-03-sparse-history",
    kpi_id="avg_consignment_value",
    window_start=date(2026, 8, 1),
    window_end=date(2026, 8, 21),
    expected=ExpectedVerdict.CANNOT_VERIFY,
    causes=(
        PlantedEvent(
            "NC-7781", CauseKind.PIPELINE_OUTAGE,
            date(2026, 8, 10), date(2026, 8, 14),
            Slice(region="South", sku="LUB-SYN"), -0.42,
            description="Supply interruption to the newly commissioned South "
                        "retail grade",
        ),
    ),
    notes="Three weeks of history is not a baseline. The engine must say the "
          "movement is real and untestable rather than fit a comparison to noise.",
    tags=("sparse-history",),
)

# --- 4. The monsoon, which is large and completely normal --------------------
SEASONAL_DECOY = Scenario(
    case_id="pet-04-monsoon-decoy",
    kpi_id="net_realisation",
    window_start=date(2025, 7, 1),
    window_end=date(2025, 7, 22),
    expected=ExpectedVerdict.NO_ANOMALY,
    notes="Bitumen and bulk construction offtake collapses every monsoon. "
          "Nothing happened. Silence is the right answer.",
    tags=("seasonal", "negative-control"),
)

# --- 5. A warning existed, was public, and had lead time ---------------------
SIGNAL_GAP = Scenario(
    case_id="pet-05-signal-gap",
    kpi_id="supply_reliability",
    window_start=date(2026, 6, 17),
    window_end=date(2026, 7, 15),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            "PC-3390", CauseKind.PORT_CLOSURE,
            date(2026, 7, 1), date(2026, 7, 5),
            Slice(region="East"), -0.26,
            description="East coastal terminals closed on cyclone advisory; "
                        "no discharge and approach roads flooded",
        ),
    ),
    signals=(
        AvailableSignal(
            signal_id="imd-cyclone-east-20260628",
            publisher="India Meteorological Department (Cyclone Warning Division)",
            available_at=datetime(2026, 6, 28, 5, 30, tzinfo=UTC),
            lead_time_hours=66.5,
            is_public=True,
            covers=Slice(region="East"),
            severity="red",
        ),
    ),
    notes="A red cyclone warning covering the affected region, public, with "
          "nearly three days of lead time. Answer 2: the warning existed and no "
          "function was watching for it.",
    tags=("signal-gap", "external"),
)

# --- 6. A warning existed and was useless ------------------------------------
NOT_FORESEEABLE = Scenario(
    case_id="pet-06-not-foreseeable",
    kpi_id="supply_reliability",
    window_start=date(2026, 4, 27),
    window_end=date(2026, 5, 25),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            "PL-5514", CauseKind.PIPELINE_OUTAGE,
            date(2026, 5, 11), date(2026, 5, 15),
            Slice(region="South"), -0.23,
            description="South product pipeline isolated following an integrity "
                        "alarm; road bridging at a third of throughput",
        ),
    ),
    signals=(
        AvailableSignal(
            signal_id="pipeline-operator-status-20260511",
            publisher="Pipeline operator status page",
            available_at=datetime(2026, 5, 11, 3, 10, tzinfo=UTC),
            lead_time_hours=0.75,
            is_public=True,
            covers=Slice(region="South"),
            severity="red",
        ),
    ),
    notes="Severe, public, specific -- and forty-five minutes ahead of the "
          "isolation. Nobody could have acted on it. `not_foreseeable` is the "
          "correct verdict, and it is the sharper refusal than 'nothing existed'.",
    tags=("not-foreseeable", "external"),
)

PETROLEUM_SCENARIOS: tuple[Scenario, ...] = (
    MULTI_FACTOR,
    NATIONAL_POLICY,
    SPARSE_HISTORY,
    SEASONAL_DECOY,
    SIGNAL_GAP,
    NOT_FORESEEABLE,
)
