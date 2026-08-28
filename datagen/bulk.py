"""A population of labelled cases, so the engine can be measured rather than described.

The six demo scenarios show behaviour. They cannot establish a rate: whether the
engine finds the right cause four times in five, how often it fires on nothing,
how often it falls for a coincidence. Those need a population, and calibration
needs one before a score can honestly be called a probability.

Events are spread across several independently generated panels rather than
crammed into one. Verification looks back roughly a hundred days for its baseline
and placebo windows, so two events in the same region inside that span would
contaminate each other, and a benchmark built on contaminated cases measures the
contamination.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from datagen.catalog import REGIONS
from datagen.scenarios import (
    CauseKind,
    ExpectedVerdict,
    PlantedEvent,
    Scenario,
    Slice,
)

PANEL_START = date(2023, 9, 1)
PANEL_DAYS = 560
# Clearance each event needs behind it: fourteen days of baseline plus six
# placebo windows spaced a fortnight apart.
LOOKBACK_DAYS = 110
EVENT_LENGTH = (4, 8)

# Proportions of the population. Decoy-bearing cases are what make the
# negative-control rejection rate measurable; noise-only cases are what catch
# the engine explaining things that did not happen.
DECOY_SHARE = 0.34
NOISE_SHARE = 0.12

# Effect sizes are stated against the *slice*, but materiality is judged at the
# region, so what matters is the product of the two. The first version of this
# table planted 10-40% moves on slices worth 6-20% of a region, which lands at
# 1-5% of regional revenue, below the contract's materiality floor by
# construction. 152 of 160 cases produced no material movement and top-1
# accuracy read 2.9%: the benchmark was measuring a generator bug.
#
# The floor is not the thing that was wrong. ~7.5% of a region-day is a
# defensible bar for a finance director, and lowering it to make cases pass is
# the trap in BUGS.md T-14. What was wrong is that no planted event was ever
# big enough to be worth explaining. Each profile below now plants on a slice
# wide enough that a plausible incident-sized effect clears the floor, and the
# comment records the arithmetic so the next person can check it rather than
# trust it.
#
#   scope                share of region   effect range   -> region movement
#   app + mobile              34.6%        -28% .. -55%      -9.7% .. -19.0%
#   web (all devices)         33.9%        -26% .. -50%      -8.8% .. -17.0%
#   store                     27.6%        -34% .. -62%      -9.4% .. -17.1%
#   packaged_foods            21.9%        -44% .. -78%      -9.6% .. -17.1%
#   home_care                 23.5%        -42% .. -72%      -9.9% .. -16.9%
#   personal_care             32.0%        -30% .. -58%      -9.6% .. -18.6%
#
# Shares are measured from the generated panel, not assumed; the test in
# tests/test_bulk.py asserts each profile's floor still clears materiality, so
# a future change to the catalog that shrinks a slice fails loudly.
CAUSE_PROFILES: tuple[tuple[CauseKind, tuple[float, float], dict], ...] = (
    (CauseKind.INTERNAL_BUG, (-0.55, -0.28), {"channel": "app", "device": "mobile"}),
    (CauseKind.INTERNAL_BUG, (-0.50, -0.26), {"channel": "web"}),
    (CauseKind.EXTERNAL_WEATHER, (-0.62, -0.34), {"channel": "store"}),
    (CauseKind.STOCKOUT, (-0.78, -0.44), {"category": "packaged_foods"}),
    (CauseKind.STOCKOUT, (-0.72, -0.42), {"category": "home_care"}),
    (CauseKind.COMPETITOR_PROMO, (-0.58, -0.30), {"category": "personal_care"}),
    (CauseKind.PRICE_CHANGE, (-0.68, -0.38), {"category": "home_care"}),
)

DESCRIPTIONS = {
    CauseKind.INTERNAL_BUG: "Release {n} broke the checkout flow on {scope}.",
    CauseKind.EXTERNAL_WEATHER: "Heavy rainfall suppressed store footfall across {region}.",
    CauseKind.STOCKOUT: "Supplier shortfall left {category} unavailable in {region}.",
    CauseKind.COMPETITOR_PROMO: "Competitor cut {category} prices across {region}.",
    CauseKind.PRICE_CHANGE: "List prices rose on {category} in {region}.",
}


@dataclass(frozen=True)
class BenchCase:
    """One labelled case: what was planted, and what a correct engine concludes."""

    case_id: str
    panel_id: int
    kpi_id: str
    region: str
    window_start: date
    window_end: date
    expected: ExpectedVerdict
    true_causes: tuple[str, ...] = ()
    decoys: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    effect: float | None = None


@dataclass
class BenchPanel:
    """A generated world, and the cases inside it."""

    panel_id: int
    events: list[PlantedEvent] = field(default_factory=list)
    cases: list[BenchCase] = field(default_factory=list)


def _slots(rng: random.Random, per_region: int) -> list[date]:
    """Event start dates with enough clearance behind each one."""
    usable = PANEL_DAYS - LOOKBACK_DAYS - max(EVENT_LENGTH) - 5
    if usable <= 0 or per_region <= 0:
        return []
    spacing = usable // per_region
    return [
        PANEL_START
        + timedelta(days=LOOKBACK_DAYS + i * spacing + rng.randint(0, max(spacing - 20, 1)))
        for i in range(per_region)
    ]


def _describe(kind: CauseKind, region: str, scope: dict, rng: random.Random) -> str:
    template = DESCRIPTIONS[kind]
    return template.format(
        n=f"{rng.randint(3, 9)}.{rng.randint(10, 99)}",
        region=region,
        scope=" ".join(str(v) for v in scope.values()) or region,
        category=(scope.get("category") or "several categories").replace("_", " "),
    )


def build_cases(
    panels: int = 10, per_region: int = 4, seed: int = 4242
) -> list[BenchPanel]:
    """Generate the population.

    Each panel gets a handful of events per region, spaced so their lookback
    windows do not overlap. A share carry a decoy, and a share carry nothing at
    all.
    """
    rng = random.Random(seed)
    out: list[BenchPanel] = []

    for panel_id in range(panels):
        panel = BenchPanel(panel_id=panel_id)

        for region in REGIONS:
            for slot_index, start in enumerate(_slots(rng, per_region)):
                case_id = f"bench-{panel_id:02d}-{region.lower()}-{slot_index}"
                end = start + timedelta(days=rng.randint(*EVENT_LENGTH))
                roll = rng.random()

                if roll < NOISE_SHARE:
                    # Nothing planted. The correct answer is silence, and an
                    # engine that explains this case is explaining noise.
                    panel.cases.append(
                        BenchCase(
                            case_id=case_id, panel_id=panel_id, kpi_id="net_revenue",
                            region=region, window_start=start, window_end=end,
                            expected=ExpectedVerdict.NO_ANOMALY, tags=("noise",),
                        )
                    )
                    continue

                kind, (low, high), scope = rng.choice(CAUSE_PROFILES)
                effect = rng.uniform(low, high)
                event_id = f"{case_id}-cause"
                panel.events.append(
                    PlantedEvent(
                        event_id=event_id, kind=kind, start=start, end=end,
                        target=Slice(region=region, **scope), effect=effect,
                        description=_describe(kind, region, scope, rng),
                    )
                )

                decoys: tuple[str, ...] = ()
                if roll < NOISE_SHARE + DECOY_SHARE:
                    # A decoy runs in the same window and in two regions that saw
                    # nothing, so it correlates here and is contradicted there.
                    others = tuple(r for r in REGIONS if r != region)
                    decoy_id = f"{case_id}-decoy"
                    panel.events.append(
                        PlantedEvent(
                            event_id=decoy_id, kind=CauseKind.MARKETING_CUT,
                            start=start, end=end, target=Slice(region=region),
                            effect=0.0, is_decoy=True,
                            also_in=rng.sample(others, 2),
                            description=f"Promotion {decoy_id} active in several regions.",
                        )
                    )
                    decoys = (decoy_id,)

                panel.cases.append(
                    BenchCase(
                        case_id=case_id, panel_id=panel_id, kpi_id="net_revenue",
                        region=region, window_start=start, window_end=end,
                        expected=ExpectedVerdict.VERIFIED,
                        true_causes=(event_id,), decoys=decoys, effect=effect,
                        tags=("decoy",) if decoys else ("single_cause",),
                    )
                )

        out.append(panel)
    return out


def as_scenarios(panel: BenchPanel) -> tuple[Scenario, ...]:
    """The panel's cases in the shape the rest of the generator already takes."""
    by_id = {e.event_id: e for e in panel.events}
    return tuple(
        Scenario(
            case_id=c.case_id, kpi_id=c.kpi_id,
            window_start=c.window_start, window_end=c.window_end,
            expected=c.expected,
            causes=tuple(by_id[i] for i in c.true_causes if i in by_id),
            decoys=tuple(by_id[i] for i in c.decoys if i in by_id),
            tags=c.tags,
        )
        for c in panel.cases
    )


def summarise(panels: list[BenchPanel]) -> dict[str, int]:
    cases = [c for p in panels for c in p.cases]
    counts = {
        "cases": len(cases),
        "with_cause": sum(1 for c in cases if c.true_causes),
        "with_decoy": sum(1 for c in cases if c.decoys),
        "noise_only": sum(1 for c in cases if c.expected is ExpectedVerdict.NO_ANOMALY),
        "panels": len(panels),
    }
    return counts
