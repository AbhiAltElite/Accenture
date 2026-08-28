"""What the analyst told us, and what the engine is allowed to do with it.

The brief asks for a mechanism that learns from analyst and business-user
feedback. The tempting version is a loop that retrains on corrections until the
engine agrees with whoever complains loudest. That is not learning, it is
capitulation, and in a system whose entire claim is that the arithmetic is
deterministic it would be the hole through which opinion re-enters the numbers.

So the loop is bounded, and the boundary is the interesting part.

**Feedback never edits a past run.** Runs are immutable; a correction is a new
record pointing at one. The diagnosis a reader saw on Tuesday is still exactly
what they saw, which is what makes an audit trail an audit trail.

**Feedback never changes a computed value.** No correction can move a bridge
leg, a difference-in-differences estimate or a confidence score. What it can do
is change *inputs the business owns*: which candidate kinds are worth
surfacing, which documents are noise, which driver a description maps to, and
where a threshold sits. Those are business facts, and a business user is
exactly the right authority for them.

**Every learned adjustment is proposed, versioned and attributable.** A
correction becomes a `Proposal` with the evidence behind it, how many analysts
said it, over how many runs, and a proposal is applied by a named person, not
by accumulation. Two analysts disagreeing produces a contested proposal that
stays unapplied rather than a silent average of their opinions.

**The eval set grows from disagreement.** Every correction that names the cause
the engine missed becomes a labelled case in the regression set. That is the
part that genuinely compounds: the engine gets measured against the things it
got wrong, forever, and `make bench` reports on them alongside the synthetic
population.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

DEFAULT_PATH = Path("data/feedback/feedback.jsonl")

# How many independent analysts must agree before a correction becomes a
# proposal. One person is an opinion; the threshold makes it a pattern.
QUORUM = 2

# A proposal contradicted by this share of the feedback on the same target is
# contested and will not be offered for application.
CONTESTED_ABOVE = 0.25


class Judgement(StrEnum):
    """What the reader is asserting. Deliberately few, and each actionable.

    A free-text comment box produces a pile nobody reads. Each of these maps to
    a specific downstream adjustment, and anything that does not fit one of
    them is `COMMENT`, recorded, surfaced, and never learned from.
    """

    CONFIRMED = "confirmed"          # the diagnosis was right
    WRONG_CAUSE = "wrong_cause"      # right movement, wrong explanation
    MISSED_CAUSE = "missed_cause"    # something real was not surfaced
    NOT_MATERIAL = "not_material"    # correctly detected, not worth flagging
    WRONG_OWNER = "wrong_owner"      # the lever or owner is misrouted
    NOISE_SOURCE = "noise_source"    # this document class is not worth reading
    COMMENT = "comment"              # recorded only


# Which judgements are allowed to become proposals, and what they may change.
# Anything absent from this map is recorded and never acted on; the map is the
# enforcement, not a convention.
LEARNABLE: dict[Judgement, str] = {
    Judgement.WRONG_CAUSE: "candidate_ranking",
    Judgement.MISSED_CAUSE: "candidate_source",
    Judgement.NOT_MATERIAL: "materiality_threshold",
    Judgement.WRONG_OWNER: "driver_mapping",
    Judgement.NOISE_SOURCE: "retrieval_filter",
}


@dataclass(frozen=True)
class Feedback:
    """One reader's judgement on one run."""

    feedback_id: str
    run_id: str
    kpi_id: str
    persona: str
    judgement: Judgement
    submitted_by: str
    submitted_at: datetime
    candidate_id: str | None = None
    correction: str | None = None
    note: str = ""
    region: str | None = None

    @property
    def learnable(self) -> bool:
        return self.judgement in LEARNABLE

    def as_dict(self) -> dict:
        d = asdict(self)
        d["judgement"] = self.judgement.value
        d["submitted_at"] = self.submitted_at.isoformat()
        d["learnable"] = self.learnable
        return d


@dataclass(frozen=True)
class Proposal:
    """A change the feedback supports, waiting for a human to apply it.

    `contested` is not a warning label; it is a refusal. A proposal that some
    readers contradict is shown with both sides and cannot be applied until the
    disagreement is resolved by someone with the authority to resolve it.
    """

    target: str
    subject: str
    change: str
    supporting: int
    contradicting: int
    runs: tuple[str, ...]
    submitters: tuple[str, ...]
    contested: bool

    @property
    def applicable(self) -> bool:
        return self.supporting >= QUORUM and not self.contested

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "subject": self.subject,
            "change": self.change,
            "supporting": self.supporting,
            "contradicting": self.contradicting,
            "runs": list(self.runs),
            "submitters": list(self.submitters),
            "contested": self.contested,
            "applicable": self.applicable,
            "quorum": QUORUM,
        }


@dataclass
class FeedbackStore:
    """Append-only, on disk, one JSON object per line.

    A line file rather than a table on purpose: feedback has to survive the
    warehouse being regenerated, and `make gen` drops the warehouse.
    """

    path: Path = DEFAULT_PATH
    _cache: list[Feedback] = field(default_factory=list, repr=False)
    _loaded: bool = field(default=False, repr=False)

    def record(self, feedback: Feedback) -> Feedback:
        # Warm the cache *before* writing. Loading afterwards reads the line
        # just written, and appending on top of that counts the entry twice,
        # which inflates exactly the number the quorum rule depends on.
        cache = self._all()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(feedback.as_dict()) + "\n")
        cache.append(feedback)
        return feedback

    def _all(self) -> list[Feedback]:
        if not self._loaded:
            self._cache = list(self._read())
            self._loaded = True
        return self._cache

    def _read(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw.pop("learnable", None)
            yield Feedback(
                **{
                    **raw,
                    "judgement": Judgement(raw["judgement"]),
                    "submitted_at": datetime.fromisoformat(raw["submitted_at"]),
                }
            )

    def for_run(self, run_id: str) -> tuple[Feedback, ...]:
        return tuple(f for f in self._all() if f.run_id == run_id)

    def summary(self) -> dict:
        """Enough to show the loop is running, without pretending it is a model."""
        entries = self._all()
        by_judgement: dict[str, int] = {}
        for entry in entries:
            by_judgement[entry.judgement.value] = by_judgement.get(entry.judgement.value, 0) + 1
        confirmed = by_judgement.get(Judgement.CONFIRMED.value, 0)
        corrections = sum(v for k, v in by_judgement.items()
                          if k not in (Judgement.CONFIRMED.value, Judgement.COMMENT.value))
        judged = confirmed + corrections
        return {
            "total": len(entries),
            "by_judgement": by_judgement,
            "runs_with_feedback": len({f.run_id for f in entries}),
            "agreement_rate": round(confirmed / judged, 3) if judged else None,
            "eval_cases_captured": sum(
                1 for f in entries if f.judgement is Judgement.MISSED_CAUSE and f.correction
            ),
            "proposals": [p.as_dict() for p in proposals(entries)],
        }


def proposals(entries: list[Feedback]) -> tuple[Proposal, ...]:
    """Group corrections into changes somebody could actually apply.

    Grouping is by (target, subject) rather than by run: the same misrouted
    driver reported on six different runs is one problem, and showing it six
    times would let volume stand in for evidence.
    """
    buckets: dict[tuple[str, str], list[Feedback]] = {}
    confirmations: dict[tuple[str, str], list[Feedback]] = {}

    for entry in entries:
        subject = entry.candidate_id or entry.kpi_id
        if entry.learnable:
            buckets.setdefault((LEARNABLE[entry.judgement], subject), []).append(entry)
        elif entry.judgement is Judgement.CONFIRMED:
            for target in set(LEARNABLE.values()):
                confirmations.setdefault((target, subject), []).append(entry)

    out: list[Proposal] = []
    for (target, subject), group in sorted(buckets.items()):
        against = len(confirmations.get((target, subject), []))
        total = len(group) + against
        out.append(
            Proposal(
                target=target,
                subject=subject,
                change=_describe(group[0]),
                supporting=len({f.submitted_by for f in group}),
                contradicting=against,
                runs=tuple(sorted({f.run_id for f in group})),
                submitters=tuple(sorted({f.submitted_by for f in group})),
                contested=bool(total) and (against / total) > CONTESTED_ABOVE,
            )
        )
    return tuple(out)


def _describe(entry: Feedback) -> str:
    """What applying this proposal would actually do. No euphemism."""
    match entry.judgement:
        case Judgement.WRONG_CAUSE:
            return (
                f"stop surfacing {entry.candidate_id} for {entry.kpi_id}; readers "
                f"report it is not the explanation"
                + (f", they name {entry.correction!r} instead" if entry.correction else "")
            )
        case Judgement.MISSED_CAUSE:
            return (
                f"add a candidate source covering {entry.correction!r}; it was the "
                f"cause and nothing in the pipeline proposed it"
            )
        case Judgement.NOT_MATERIAL:
            return (
                f"raise the materiality floor for {entry.kpi_id}; readers report "
                f"movements of this size are not worth a diagnosis"
            )
        case Judgement.WRONG_OWNER:
            return (
                f"remap the driver behind {entry.candidate_id} in the "
                f"{entry.kpi_id} contract"
                + (f" to {entry.correction!r}" if entry.correction else "")
            )
        case Judgement.NOISE_SOURCE:
            return f"exclude this document class from retrieval for {entry.kpi_id}"
        case _:
            return "recorded only; this judgement class is not learned from"


def eval_cases(entries: list[Feedback]) -> tuple[dict, ...]:
    """Corrections that name a cause, as labelled cases for the regression set.

    This is the part that compounds. Every real miss becomes a case the engine
    is measured against from then on, so a fix that breaks an old correction
    fails the benchmark rather than being discovered by the same analyst twice.
    """
    return tuple(
        {
            "case_id": f"fb-{f.feedback_id}",
            "run_id": f.run_id,
            "kpi_id": f.kpi_id,
            "region": f.region,
            "expected_cause": f.correction,
            "source": "analyst_correction",
            "captured_at": f.submitted_at.isoformat(),
        }
        for f in entries
        if f.judgement is Judgement.MISSED_CAUSE and f.correction
    )


def new_feedback(
    *,
    run_id: str,
    kpi_id: str,
    persona: str,
    judgement: str,
    submitted_by: str,
    candidate_id: str | None = None,
    correction: str | None = None,
    note: str = "",
    region: str | None = None,
) -> Feedback:
    """Build a record with a server-side timestamp and id.

    Neither is taken from the caller: a client-supplied timestamp on an audit
    record is a client-supplied audit record.
    """
    now = datetime.now(UTC)
    return Feedback(
        feedback_id=f"fb-{now.strftime('%Y%m%d%H%M%S%f')}",
        run_id=run_id,
        kpi_id=kpi_id,
        persona=persona,
        judgement=Judgement(judgement),
        submitted_by=submitted_by,
        submitted_at=now,
        candidate_id=candidate_id,
        correction=correction,
        note=note[:2000],
        region=region,
    )
