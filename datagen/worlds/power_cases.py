"""Labelled cases for the power vertical.

Same mix and the same argument as petroleum: a regulatory tariff order moves a
number for every grid region at once and must come back `cannot_verify`, while
a fuel rake shortfall, a transmission constraint or a unit trip is regional and
must verify.
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

MULTI_FACTOR = Scenario(
    case_id="pwr-01-multi-factor",
    kpi_id="dispatch_realisation",
    window_start=date(2026, 7, 22),
    window_end=date(2026, 8, 19),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            "FS-8120", CauseKind.FUEL_SHORTAGE,
            date(2026, 8, 12), date(2026, 8, 16),
            Slice(region="West", category="coal"), -0.19,
            description="Coal stock critical at West stations following short "
                        "rake receipt; declared capacity reduced",
        ),
        PlantedEvent(
            "GC-4471", CauseKind.GRID_CONSTRAINT,
            date(2026, 8, 14), date(2026, 8, 16),
            Slice(region="West"), -0.10,
            description="West export corridor outage; generation curtailed on "
                        "transmission constraint",
        ),
    ),
    decoys=(
        PlantedEvent(
            "MO-6600", CauseKind.MERIT_ORDER_SHIFT,
            date(2026, 8, 11), date(2026, 8, 17),
            Slice(region="West"), 0.0, is_decoy=True, also_in=("South",),
            description="Revised merit order stack published for West and South",
        ),
    ),
    notes="Fuel and the grid together, with a merit order revision that "
          "correlates with both and caused neither.",
    tags=("multi-factor", "decoy"),
)

NATIONAL_POLICY = Scenario(
    case_id="pwr-02-national-tariff",
    kpi_id="dispatch_realisation",
    window_start=date(2026, 5, 4),
    window_end=date(2026, 6, 1),
    expected=ExpectedVerdict.CANNOT_VERIFY,
    causes=(
        PlantedEvent(
            "TO-2026-19", CauseKind.TARIFF_ORDER,
            date(2026, 5, 18), date(2026, 5, 22),
            Slice(), -0.07,
            description="Commission tariff order takes effect; rate schedules "
                        "amended for all long-term contracted offtake",
        ),
    ),
    notes="A regulator moved the number for every region at once. Real, known, "
          "and untestable by comparison. `cannot_verify` is correct.",
    tags=("national", "no-control-group", "abstention"),
)

SPARSE_HISTORY = Scenario(
    case_id="pwr-03-sparse-history",
    kpi_id="avg_realised_tariff",
    window_start=date(2026, 8, 1),
    window_end=date(2026, 8, 21),
    expected=ExpectedVerdict.CANNOT_VERIFY,
    causes=(
        PlantedEvent(
            "NC-9902", CauseKind.GRID_CONSTRAINT,
            date(2026, 8, 10), date(2026, 8, 14),
            Slice(region="South", sku="STN-SOL-3"), -0.34,
            description="Evacuation constraint at the newly commissioned South "
                        "solar station",
        ),
    ),
    notes="Three weeks of generation history is not a baseline.",
    tags=("sparse-history",),
)

SEASONAL_DECOY = Scenario(
    case_id="pwr-04-summer-decoy",
    kpi_id="dispatch_realisation",
    window_start=date(2025, 5, 5),
    window_end=date(2025, 5, 26),
    expected=ExpectedVerdict.NO_ANOMALY,
    notes="Demand climbs every May and falls back every June. The swing is "
          "large and means nothing.",
    tags=("seasonal", "negative-control"),
)

SIGNAL_GAP = Scenario(
    case_id="pwr-05-signal-gap",
    kpi_id="grid_availability",
    window_start=date(2026, 6, 17),
    window_end=date(2026, 7, 15),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            "HW-7742", CauseKind.HEAT_WAVE,
            date(2026, 7, 1), date(2026, 7, 5),
            Slice(region="North"), -0.21,
            description="North demand overshoot during the heat wave; reserve "
                        "margin thin and deviation exposure high",
        ),
    ),
    signals=(
        AvailableSignal(
            signal_id="imd-heatwave-north-20260628",
            publisher="India Meteorological Department (Heat Wave Warning)",
            available_at=datetime(2026, 6, 28, 6, 0, tzinfo=UTC),
            lead_time_hours=72.0,
            is_public=True,
            covers=Slice(region="North"),
            severity="red",
        ),
    ),
    notes="A red heat wave warning for the affected region, public, three days "
          "ahead. Answer 2: nothing in the scheduling process consumes it.",
    tags=("signal-gap", "external"),
)

NOT_FORESEEABLE = Scenario(
    case_id="pwr-06-not-foreseeable",
    kpi_id="grid_availability",
    window_start=date(2026, 4, 27),
    window_end=date(2026, 5, 25),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            "PO-3318", CauseKind.PLANT_OUTAGE,
            date(2026, 5, 11), date(2026, 5, 15),
            Slice(region="South", category="coal"), -0.24,
            description="Forced outage at the South station following a boiler "
                        "protection operation; unit off bar",
        ),
    ),
    signals=(
        AvailableSignal(
            signal_id="plant-scada-alarm-20260511",
            publisher="Station SCADA alarm log",
            available_at=datetime(2026, 5, 11, 3, 22, tzinfo=UTC),
            lead_time_hours=0.3,
            is_public=False,
            covers=Slice(region="South"),
            severity="red",
        ),
    ),
    notes="A protection trip gives eighteen minutes of notice and the alarm is "
          "internal, so it fails both gates: not public and far too late. "
          "`not_foreseeable`, and correctly so.",
    tags=("not-foreseeable", "external"),
)

POWER_SCENARIOS: tuple[Scenario, ...] = (
    MULTI_FACTOR,
    NATIONAL_POLICY,
    SPARSE_HISTORY,
    SEASONAL_DECOY,
    SIGNAL_GAP,
    NOT_FORESEEABLE,
)
