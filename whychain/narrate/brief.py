"""What the writer is allowed to know.

The model does not see the warehouse, the contracts, or the pipeline. It sees a
brief: a flat table of facts that have already been computed, each with an id, a
value, a unit and a plain-language claim. Anything absent from the brief cannot
appear in the narrative, because the validator resolves every number and every
entity back through this table.

Building the brief is therefore the real safety boundary, and it is
deterministic code. Two rules govern it.

**Only terminal facts go in.** A rejected candidate is in the brief as a
rejection, with the test that killed it, because "we checked X and it was not
the cause" is worth saying. It is not in the brief as a cause. There is no
representation of a candidate that would let a writer state it as a reason
(BUGS.md T-12).

**Numbers go in pre-formatted.** The writer is never asked to convert, round, or
express a proportion. It receives the string it is allowed to print alongside the
raw value, and the validator checks the string. That closes the percentage /
percentage-point confusion (BUGS.md T-02) at the source rather than trying to
catch it afterwards in prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from whychain.evidence import Unit


def format_value(value: float | None, unit: Unit) -> str:
    """The one place a number becomes text.

    Percent and percentage point render differently on purpose. A conversion
    rate that went from 10% to 15% moved five percentage points, and writing
    that as "+5%" or "+50%" are two different wrong claims.
    """
    if value is None:
        return "not available"
    match unit:
        case Unit.INR:
            # The sign belongs outside the currency symbol. "₹-39,486" is how a
            # naive format string renders a loss and it is not how anyone
            # writes one.
            return f"{'−' if value < 0 else ''}₹{abs(value):,.0f}"
        case Unit.PCT:
            return f"{value * 100:.1f}%"
        case Unit.PCT_POINT:
            return f"{value:+.1f} percentage points"
        case Unit.COUNT:
            return f"{value:,.0f}"
        case Unit.HOURS:
            return f"{value:,.0f} hours"
        case Unit.RATIO:
            return f"{value:.2f}"
        case _:
            return f"{value:,.2f}"


@dataclass(frozen=True)
class Fact:
    """One row of the brief. The writer may cite this by `id` and nothing else."""

    id: str
    claim: str
    value: float | None
    unit: Unit
    display: str
    kind: str
    state: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "claim": self.claim,
            "display": self.display,
            "unit": self.unit.value,
            "kind": self.kind,
            "state": self.state,
        }


@dataclass(frozen=True)
class Brief:
    """Everything the writer may use, and nothing else."""

    run_id: str
    kpi: str
    region: str | None
    window: tuple[str, str]
    verdict: str
    facts: tuple[Fact, ...]
    entities: frozenset[str] = field(default_factory=frozenset)

    def by_id(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "kpi": self.kpi,
            "region": self.region,
            "window": {"from": self.window[0], "to": self.window[1]},
            "verdict": self.verdict,
            "facts": [f.as_dict() for f in self.facts],
        }


def _plain(description: str | None) -> str:
    """A cause as a reader says it, not as the record addresses it.

    Candidates arrive as "rel-4.05: Release 4.05 broke card entry". The prefix
    is how the evidence store finds the row; putting it in a sentence makes the
    narrative read like a log line.
    """
    text = (description or "").strip()
    head, sep, tail = text.partition(": ")
    return (tail.strip() if sep and len(head) <= 32 and " " not in head else text)


def _fact(
    fact_id: str,
    claim: str,
    value: float | None,
    unit: Unit,
    kind: str,
    state: str | None = None,
) -> Fact:
    return Fact(
        id=fact_id,
        claim=claim,
        value=value,
        unit=unit,
        display=format_value(value, unit),
        kind=kind,
        state=state,
    )


def build_brief(result: dict) -> Brief:
    """Flatten a diagnosis into the table the writer reads.

    The input is the API's own result dict, so the brief cannot drift from what
    the console renders; both read the same object.
    """
    run_id = result["run_id"]
    movement = result.get("movement", {})
    facts: list[Fact] = []
    entities: set[str] = set()

    if result.get("region"):
        entities.add(str(result["region"]))
    entities.add(str(result.get("kpi_id", "")))

    facts.append(
        _fact(
            "f-movement",
            f"{result.get('kpi_id')} moved over the window",
            movement.get("total_change"),
            Unit.INR,
            "movement",
        )
    )
    if movement.get("pct") is not None:
        facts.append(
            _fact("f-movement-pct", "the movement as a proportion of the baseline",
                  movement.get("pct"), Unit.PCT, "movement")
        )
    facts.append(
        _fact("f-explained", "the part of the movement verified causes account for",
              movement.get("explained"), Unit.INR, "coverage")
    )
    # Only stated when there is something to state. Causes that do not overlap
    # need no sentence about overlapping, and a fact that is always present
    # tempts a writer into always mentioning it.
    if (movement.get("overlap") or 1.0) > 1.0:
        facts.append(
            _fact("f-overlap",
                  "how far the verified causes overlap, as their gross "
                  "attribution over the movement",
                  movement.get("overlap"), Unit.PCT, "coverage")
        )

    confidence = result.get("confidence", {})
    facts.append(
        _fact("f-confidence", f"confidence, band {confidence.get('band')}",
              confidence.get("score"), Unit.RATIO, "confidence", confidence.get("band"))
    )

    for i, verified in enumerate(result.get("verified", []), start=1):
        facts.append(
            _fact(
                f"f-cause-{i}",
                f"verified cause: {_plain(verified.get('description'))}",
                verified.get("contribution"),
                Unit.INR,
                "cause",
                "verified",
            )
        )
        if verified.get("effect_pct") is not None:
            facts.append(
                _fact(
                    f"f-cause-{i}-effect",
                    f"measured effect of {_plain(verified.get('description'))}",
                    verified.get("effect_pct"),
                    Unit.PCT,
                    "cause_effect",
                    "verified",
                )
            )
        for key, value in (verified.get("scope") or {}).items():
            entities.add(str(value))
            del key
        for region in verified.get("exposed_regions", []):
            entities.add(str(region))

    # Rejections are facts. They are the part of the answer that says what was
    # checked and ruled out, and a reader who cannot see them cannot tell a
    # tested diagnosis from an untested one.
    for i, aside in enumerate(result.get("set_aside", []), start=1):
        facts.append(
            _fact(
                f"f-ruled-out-{i}",
                f"ruled out: {aside.get('candidate_id')}, {aside.get('reason')}",
                None,
                Unit.NONE,
                "ruled_out",
                "rejected",
            )
        )

    for i, card in enumerate(result.get("decisions", []), start=1):
        if card.get("owner"):
            entities.add(str(card["owner"]))
        facts.append(
            _fact(
                f"f-decision-{i}",
                f"decision: {card.get('action')}"
                + (f", owned by {card.get('owner')}" if card.get("owner") else ""),
                card.get("expected_recovery_inr_per_day"),
                Unit.INR,
                "decision",
            )
        )

    gap = result.get("signal_gap")
    if gap:
        facts.append(
            _fact(
                "f-gap",
                f"signal gap verdict {gap.get('verdict')}: {gap.get('reason')}",
                gap.get("best_lead_time_hours"),
                Unit.HOURS,
                "signal_gap",
                gap.get("verdict"),
            )
        )
        if gap.get("recurrence"):
            facts.append(
                _fact("f-gap-recurrence",
                      "prior episodes of the same warning class over this slice",
                      float(gap["recurrence"]), Unit.COUNT, "signal_gap")
            )

    return Brief(
        run_id=run_id,
        kpi=str(result.get("kpi_id")),
        region=result.get("region"),
        window=(result["window"]["from"], result["window"]["to"]),
        verdict=str(result.get("verdict")),
        facts=tuple(facts),
        entities=frozenset(e for e in entities if e),
    )
