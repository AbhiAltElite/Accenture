"""The scenarios the demo walks through.

Each maps to one of the minimum prototype expectations. They are written out
explicitly rather than sampled, because a demo has to behave the same way every
time it is run in front of someone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from datagen.scenarios import (
    AvailableSignal,
    CauseKind,
    ExpectedVerdict,
    PlantedEvent,
    Scenario,
    Slice,
)

# Anchor the demo late in the generated period so there is a full history behind it.
ANCHOR = date(2026, 8, 12)


def _at(day: date, hour: int = 9) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. Multi-factor movement, with a planted correlation trap.
#
# Three real contributors of different sizes, one seasonal decoy sitting in the
# same window, and a promotion that starts on exactly the same day as the
# release regression. The promotion caused nothing, and it also ran in the East,
# which is how difference-in-differences rejects it.
# ---------------------------------------------------------------------------
MULTI_FACTOR = Scenario(
    case_id="demo-01-multi-factor",
    kpi_id="net_revenue",
    window_start=ANCHOR - timedelta(days=21),
    window_end=ANCHOR + timedelta(days=7),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            event_id="rel-4.05",
            kind=CauseKind.INTERNAL_BUG,
            start=ANCHOR,
            end=ANCHOR + timedelta(days=6),
            target=Slice(region="West", channel="app", device="mobile"),
            effect=-0.34,
            description="Release 4.05 broke card entry on the Android checkout flow.",
        ),
        PlantedEvent(
            event_id="comp-pricecut-aug",
            kind=CauseKind.COMPETITOR_PROMO,
            start=ANCHOR - timedelta(days=2),
            end=ANCHOR + timedelta(days=7),
            target=Slice(region="West", category="personal_care"),
            effect=-0.09,
            description="Competitor cut personal care prices across the West.",
        ),
        PlantedEvent(
            event_id="wx-mumbai-aug",
            kind=CauseKind.EXTERNAL_WEATHER,
            start=ANCHOR + timedelta(days=1),
            end=ANCHOR + timedelta(days=3),
            target=Slice(region="West", channel="store"),
            effect=-0.22,
            description="Heavy rainfall suppressed store footfall in Mumbai and Pune.",
        ),
    ),
    decoys=(
        PlantedEvent(
            event_id="promo-monsoon-sale",
            kind=CauseKind.MARKETING_CUT,
            start=ANCHOR,
            end=ANCHOR + timedelta(days=6),
            target=Slice(region="West"),
            effect=0.0,
            is_decoy=True,
            also_in=("East", "South"),
            description=(
                "Monsoon promotion launched the same day as release 4.05. "
                "It correlates almost perfectly with the drop and caused none of it."
            ),
        ),
    ),
    signals=(
        AvailableSignal(
            signal_id="imd_severe_weather_alert",
            publisher="India Meteorological Department",
            available_at=_at(ANCHOR - timedelta(days=2), 6),
            lead_time_hours=72.0,
            is_public=True,
            covers=Slice(region="West"),
        ),
    ),
    notes="Bug 62%, competitor 18%, weather 12%. Promotion is the trap.",
    tags=("multi_factor", "negative_control", "demo"),
)


# ---------------------------------------------------------------------------
# 2. Genuine ambiguity. Sources disagree, no comparison group survives, and the
#    honest answer is UNKNOWN with what was ruled out.
# ---------------------------------------------------------------------------
LOW_CONFIDENCE = Scenario(
    case_id="demo-02-low-confidence",
    kpi_id="net_revenue",
    window_start=date(2026, 6, 3) - timedelta(days=21),
    window_end=date(2026, 6, 10),
    expected=ExpectedVerdict.UNKNOWN,
    causes=(
        PlantedEvent(
            event_id="diffuse-softness",
            kind=CauseKind.STOCKOUT,
            start=date(2026, 6, 3),
            end=date(2026, 6, 9),
            # Nationwide and shallow: every region moves, so no region can serve
            # as a control, and the effect is too small to isolate.
            target=Slice(),
            effect=-0.06,
            description="Shallow availability softness across all regions at once.",
        ),
    ),
    notes="No unaffected comparison group exists. Abstention is the correct output.",
    tags=("abstention", "demo"),
)


# ---------------------------------------------------------------------------
# 3. Sparse history. A SKU three weeks old cannot support causal verification.
# ---------------------------------------------------------------------------
SPARSE_HISTORY = Scenario(
    case_id="demo-03-sparse-history",
    kpi_id="aov",
    window_start=date(2026, 8, 1),
    window_end=date(2026, 8, 21),
    expected=ExpectedVerdict.CANNOT_VERIFY,
    causes=(
        PlantedEvent(
            event_id="pc1099-launch-dip",
            kind=CauseKind.PRICE_CHANGE,
            start=date(2026, 8, 14),
            end=date(2026, 8, 21),
            target=Slice(sku="PC-1099"),
            effect=-0.18,
            description="Introductory pricing ended on a SKU launched three weeks earlier.",
        ),
    ),
    notes="Estimate must shrink toward the category prior; verification unavailable.",
    tags=("sparse_history", "demo"),
)


# ---------------------------------------------------------------------------
# 4. Seasonal decoy. A large movement that is entirely normal.
#    The post-Diwali collapse is roughly eighteen per cent overnight.
# ---------------------------------------------------------------------------
SEASONAL_DECOY = Scenario(
    case_id="demo-04-seasonal-decoy",
    kpi_id="net_revenue",
    window_start=date(2025, 10, 6),
    window_end=date(2025, 10, 27),
    expected=ExpectedVerdict.NO_ANOMALY,
    notes="Post-Diwali fall. Large, alarming, and completely ordinary.",
    tags=("false_alarm", "demo"),
)


# ---------------------------------------------------------------------------
# 5. Answer 2, and the two refusals that prove the gate is a gate.
# ---------------------------------------------------------------------------
SIGNAL_GAP = Scenario(
    case_id="demo-05-signal-gap",
    kpi_id="on_time_delivery",
    window_start=date(2026, 7, 8) - timedelta(days=21),
    window_end=date(2026, 7, 15),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            event_id="wx-flood-jul",
            kind=CauseKind.EXTERNAL_WEATHER,
            start=date(2026, 7, 8),
            end=date(2026, 7, 12),
            target=Slice(region="West"),
            effect=-0.28,
            description="Flooding closed two distribution centres in the West.",
        ),
    ),
    signals=(
        AvailableSignal(
            signal_id="imd_severe_weather_alert",
            publisher="India Meteorological Department",
            available_at=_at(date(2026, 7, 5), 6),
            lead_time_hours=72.0,
            is_public=True,
            covers=Slice(region="West"),
        ),
    ),
    notes="Gap found: 72h of public warning, and the process consumes no weather signal.",
    tags=("signal_gap", "answer2", "demo"),
)

NOT_FORESEEABLE = Scenario(
    case_id="demo-06-not-foreseeable",
    kpi_id="on_time_delivery",
    window_start=date(2026, 5, 18) - timedelta(days=21),
    window_end=date(2026, 5, 25),
    expected=ExpectedVerdict.VERIFIED,
    causes=(
        PlantedEvent(
            event_id="carrier-collapse-may",
            kind=CauseKind.STOCKOUT,
            start=date(2026, 5, 18),
            end=date(2026, 5, 22),
            target=Slice(region="South"),
            effect=-0.24,
            description="A regional carrier suspended operations without notice.",
        ),
    ),
    signals=(
        # Public, but forty minutes ahead of the event. Available is not the same
        # as actionable, and the engine must decline rather than call this a gap.
        AvailableSignal(
            signal_id="carrier_status_feed",
            publisher="Carrier status page",
            available_at=_at(date(2026, 5, 18), 7) - timedelta(minutes=40),
            lead_time_hours=0.67,
            is_public=True,
            covers=Slice(region="South"),
        ),
    ),
    notes="A forty-minute warning is not actionable. Expected: not foreseeable.",
    tags=("signal_gap", "answer2", "refusal", "demo"),
)

DEMO_SCENARIOS: tuple[Scenario, ...] = (
    MULTI_FACTOR,
    LOW_CONFIDENCE,
    SPARSE_HISTORY,
    SEASONAL_DECOY,
    SIGNAL_GAP,
    NOT_FORESEEABLE,
)
