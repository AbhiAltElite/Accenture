"""How much the engine should be believed, and when it should stop.

Confidence here is arithmetic over things already established, not a judgement
and not something a model writes. Five inputs, each of which a reader can be
shown:

**Coverage** is the share of the movement that verified causes account for. If
half the fall is unexplained, no explanation of the other half deserves high
confidence however well tested it is.

**Causal strength** is how far the measured effect stands outside the range the
same comparison produces on quiet data.

**Corroboration** is how many independent documents describe the thing the
statistics point at, saturating quickly: the second ticket adds a great deal, the
twelfth adds almost nothing.

**Freshness** penalises a diagnosis built on a source that has breached its SLA.

**Contradiction** penalises verified claims that disagree with each other.

The score is deliberately not calibrated yet. Turning it into a probability
requires held-out cases to fit against, and asserting a probability without them
would be the exact failure this project exists to avoid. Until then it is a
comparable score with a stated basis, and it says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from whychain.evidence import ClaimState, Freshness

# What each input is worth. They sum to one so the score reads as a proportion.
WEIGHTS = {
    "coverage": 0.35,
    "causal_strength": 0.30,
    "corroboration": 0.20,
    "freshness": 0.15,
}

# Below this, too much of the movement is unaccounted for to name a cause.
MIN_COVERAGE = 0.45
# Below this the engine abstains rather than reporting its best guess.
ABSTAIN_BELOW = 0.45
HIGH_ABOVE = 0.70
# Corroboration saturates: this many supporting documents is full credit.
CORROBORATION_SATURATION = 3
# A placebo-relative effect at or beyond this counts as full causal strength.
STRENGTH_SATURATION = 3.0


class Band(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Component:
    name: str
    value: float          # normalised nought to one
    detail: str

    @property
    def weighted(self) -> float:
        return self.value * WEIGHTS.get(self.name, 0.0)


@dataclass(frozen=True)
class Confidence:
    score: float
    band: Band
    components: tuple[Component, ...]
    reasons: tuple[str, ...] = ()          # why it abstained, if it did

    @property
    def abstained(self) -> bool:
        return self.band is Band.UNKNOWN

    def explain(self) -> dict[str, float]:
        return {c.name: round(c.value, 3) for c in self.components}


@dataclass(frozen=True)
class Abstention:
    """What the engine says instead of guessing.

    An abstention that only says "unknown" wastes the analyst's time as surely as
    a wrong answer. This carries what was ruled out and by which test, what is
    blocking, and the single next thing worth checking.
    """

    ruled_out: tuple[dict[str, str], ...]
    blocking: tuple[str, ...]
    next_check: str
    question: str | None = None
    coverage: float = 0.0


def _coverage(explained: float, total_movement: float) -> Component:
    if not total_movement:
        return Component("coverage", 0.0, "the metric did not move")
    share = min(abs(explained / total_movement), 1.0)
    return Component(
        "coverage", share,
        f"verified causes account for {share:.0%} of the movement",
    )


def _causal_strength(verifications) -> Component:
    """How far the strongest verified effect stands outside the quiet range."""
    strengths = []
    for v in verifications:
        if v.state is not ClaimState.VERIFIED:
            continue
        placebo = next((r for r in v.results if r.name == "placebo"), None)
        if placebo and placebo.statistic and v.effect_pct:
            strengths.append(abs(v.effect_pct) / abs(placebo.statistic))
    if not strengths:
        return Component("causal_strength", 0.0, "no verified cause to measure")
    best = max(strengths)
    return Component(
        "causal_strength", min(best / STRENGTH_SATURATION, 1.0),
        f"the strongest verified effect is {best:.1f} times the largest movement "
        f"the same comparison produces on quiet data",
    )


def _corroboration(supporting: int) -> Component:
    value = min(supporting / CORROBORATION_SATURATION, 1.0)
    if supporting == 0:
        return Component("corroboration", 0.0, "nothing in the record describes this")
    return Component(
        "corroboration", value,
        f"{supporting} independent document(s) describe it",
    )


def _freshness(sources: dict[str, Freshness]) -> Component:
    if not sources:
        return Component("freshness", 1.0, "no freshness requirement declared")
    breached = [f.source_id for f in sources.values() if not f.sla_met]
    if not breached:
        return Component("freshness", 1.0, "every source is within its SLA")
    value = max(0.0, 1.0 - len(breached) / len(sources))
    return Component(
        "freshness", value,
        f"{', '.join(breached)} breached the freshness SLA",
    )


def _contradictions(verifications) -> tuple[str, ...]:
    """Verified claims that disagree in direction on the same exposure."""
    verified = [v for v in verifications if v.state is ClaimState.VERIFIED and v.effect_pct]
    found = []
    for i, a in enumerate(verified):
        for b in verified[i + 1:]:
            shared = set(a.candidate.exposed_regions) & set(b.candidate.exposed_regions)
            if shared and a.effect_pct * b.effect_pct < 0:
                found.append(
                    f"{a.candidate.candidate_id} and {b.candidate.candidate_id} "
                    f"move {', '.join(sorted(shared))} in opposite directions"
                )
    return tuple(found)


def score(
    verifications,
    *,
    explained: float,
    total_movement: float,
    supporting_documents: int,
    sources: dict[str, Freshness],
) -> Confidence:
    """Combine the inputs, then decide whether to report at all."""
    components = (
        _coverage(explained, total_movement),
        _causal_strength(verifications),
        _corroboration(supporting_documents),
        _freshness(sources),
    )
    raw = sum(c.weighted for c in components)
    contradictions = _contradictions(verifications)

    reasons: list[str] = []
    if not any(v.state is ClaimState.VERIFIED for v in verifications):
        reasons.append("no candidate survived testing")
    coverage = components[0].value
    if coverage < MIN_COVERAGE:
        reasons.append(
            f"verified causes account for only {coverage:.0%} of the movement"
        )
    if contradictions:
        reasons.extend(contradictions)
    breached = [f.source_id for f in sources.values() if not f.sla_met]
    if breached:
        reasons.append(f"{', '.join(breached)} is stale beyond its SLA")
    if raw < ABSTAIN_BELOW:
        reasons.append(f"the combined score is {raw:.2f}, below the reporting threshold")

    # Any reason at all is enough. Confidence is not a vote among concerns.
    band = Band.UNKNOWN if reasons else (Band.HIGH if raw >= HIGH_ABOVE else Band.MODERATE)
    return Confidence(round(raw, 3), band, components, tuple(reasons))


def abstain(verifications, confidence: Confidence, blocking: tuple[str, ...] = ()) -> Abstention:
    """Assemble the structured answer given in place of a cause."""
    ruled_out = tuple(
        {
            "candidate": v.candidate.candidate_id,
            "description": v.candidate.description,
            "verdict": v.state.value,
            "reason": v.reason,
        }
        for v in verifications
        if v.state in (ClaimState.REJECTED, ClaimState.CANNOT_VERIFY)
    )

    untestable = [v for v in verifications if v.state is ClaimState.CANNOT_VERIFY]
    if untestable:
        first = untestable[0]
        next_check = (
            f"establish a comparison group for {first.candidate.candidate_id}, or "
            f"extend history until one exists"
        )
        question = (
            f"Was {first.candidate.candidate_id} limited to a particular region, "
            f"channel or category? It is currently untestable because it appears "
            f"to have applied everywhere."
        )
    elif confidence.components[0].value < MIN_COVERAGE:
        next_check = (
            "break the movement down a further level, since most of it is not "
            "accounted for by anything in the operational record"
        )
        question = "Is there an event in this window that was not written down anywhere?"
    else:
        next_check = "widen the search window and re-run"
        question = None

    return Abstention(
        ruled_out=ruled_out,
        blocking=blocking,
        next_check=next_check,
        question=question,
        coverage=confidence.components[0].value,
    )
