"""Applying a proposal, which is the step that was missing.

Everything up to here was real: corrections are captured, grouped by target,
gated on two independent submitters, and held contested when readers disagree.
And then nothing consumed one. `README` called it a workflow rather than a
learning loop for exactly that reason, which was honest and still left objective
7 of the brief resting on a mechanism that stopped one step short of mattering.

This is that step, and it is deliberately narrow.

**An applied change is an overlay, never an edit to the contract.** The `.yml`
stays the reviewed, version-controlled definition of the metric; applications
are appended here and composed over it at load. Three reasons, and the first is
the one that matters: a change nobody can see is not governance. An overlay
carries who applied it, when, on the strength of which runs and which
submitters, and it can be lifted by deleting a line. Rewriting the YAML in place
would leave a contract whose provenance is a diff in somebody's history.

**One target is consumable, and the rest say so.** `materiality_threshold` is a
single declared number that the engine reads on every run, so applying it is
observable the same day: movements a quorum of readers called not worth
diagnosing stop being flagged. The other four targets in `LEARNABLE` need
machinery that does not exist yet -- a candidate source registry, a ranking
prior -- and `apply_proposal` refuses them by name rather than accepting an
application it cannot honour. A refusal a caller can read beats a queue nobody
drains.

**The new value is derived, not chosen.** A reader saying "this was not worth
flagging" is evidence about a magnitude, so the floor moves to just above the
largest movement they said that about, and no further. Nobody types a number,
and the record carries the movements it was computed from. A threshold somebody
picked to make a complaint go away is how a materiality floor becomes the place
where inconvenient findings are buried.

**Nothing here moves a computed value.** The floor is a business input: it
decides what is worth an analyst's attention, not what the arithmetic says
happened. Every bridge leg, every difference-in-differences estimate and every
confidence score is untouched, which is the boundary the whole feedback design
is built around.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from whychain.feedback.store import QUORUM, Proposal

DEFAULT_PATH = Path("data/feedback/applied.jsonl")

# The targets an application can actually honour. Everything else in `LEARNABLE`
# is a proposal a human can read and act on by hand; only these change what the
# engine does on the next run without anybody editing code.
CONSUMABLE: dict[str, str] = {
    "materiality_threshold": "materiality.min_abs_delta_inr",
}

WHY_NOT: dict[str, str] = {
    "candidate_ranking": (
        "there is no ranking prior for a candidate to be demoted in; track A is "
        "an exact identity and track B is refitted per run, so nothing here "
        "persists a preference between runs"
    ),
    "candidate_source": (
        "candidates come from the operational record, and adding a source means "
        "registering a document class and its extraction rules, which is a "
        "contract change rather than a value change"
    ),
    "driver_mapping": (
        "the description-to-driver mapping is a vocabulary in code, not a "
        "contract field; remapping it changes what the retrieval layer means by "
        "a word and is reviewed rather than applied"
    ),
    "retrieval_filter": (
        "no per-deployment document exclusion list exists yet; suppressing a "
        "document class silently is the one change here that could hide a real "
        "cause, so it stays a proposal a person acts on"
    ),
}

# A floor may not move further than this in one application, however loud the
# feedback. Materiality decides what a reader is shown at all, so an unbounded
# raise is the one change in this file that could quietly switch detection off.
MAX_RAISE_MULTIPLE = 2.0


@dataclass(frozen=True)
class AppliedChange:
    """One applied proposal, as an audit record.

    Everything needed to answer "why is this threshold what it is" without
    leaving the file: the field, both values, the person, and the evidence.
    """

    change_id: str
    kpi_id: str
    target: str
    field_path: str
    from_value: float
    to_value: float
    applied_by: str
    applied_at: datetime
    supporting: int
    submitters: tuple[str, ...]
    runs: tuple[str, ...]
    basis: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["applied_at"] = self.applied_at.isoformat()
        d["submitters"] = list(self.submitters)
        d["runs"] = list(self.runs)
        return d


class ApplyRefused(Exception):
    """The application was not made, and this says why. Never a silent no-op."""


@dataclass
class AppliedStore:
    """Append-only, on disk, one JSON object per line. As the feedback log."""

    path: Path = DEFAULT_PATH
    _cache: list[AppliedChange] | None = field(default=None, repr=False)
    _stamp: float | None = field(default=None, repr=False)

    def _mtime(self) -> float:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return 0.0

    def all(self) -> list[AppliedChange]:
        # Re-read when the file has moved on. Caching this outright looks safe --
        # the log is append-only and this process is the only writer -- and is
        # not: it sits in front of every contract load, so a stale cache serves
        # the old threshold for the life of the process, and lifting a change by
        # editing the file does nothing at all. That failure is invisible,
        # because the value it serves is a plausible one.
        stamp = self._mtime()
        if self._cache is not None and self._stamp == stamp:
            return self._cache
        out: list[AppliedChange] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    raw["applied_at"] = datetime.fromisoformat(raw["applied_at"])
                    raw["submitters"] = tuple(raw.get("submitters", ()))
                    raw["runs"] = tuple(raw.get("runs", ()))
                    out.append(AppliedChange(**raw))
                except (ValueError, TypeError, KeyError):
                    # A malformed line is skipped rather than raising. This file
                    # sits in front of every contract load; a bad line must not
                    # be able to take the engine down.
                    continue
        self._cache, self._stamp = out, stamp
        return out

    def record(self, change: AppliedChange) -> AppliedChange:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(change.as_dict(), ensure_ascii=False) + "\n")
        # Invalidate rather than append: the next read re-derives from the file,
        # which is the only thing that is actually the record.
        self._cache = self._stamp = None
        return change

    def overlay(self) -> dict[str, dict[str, float]]:
        """The effective value of every overlaid field, per KPI.

        Last application wins, which is what append-only plus replay means. The
        history stays in the file either way.
        """
        out: dict[str, dict[str, float]] = {}
        for change in self.all():
            out.setdefault(change.kpi_id, {})[change.field_path] = change.to_value
        return out

    def history(self, kpi_id: str | None = None) -> list[AppliedChange]:
        return [c for c in self.all() if kpi_id is None or c.kpi_id == kpi_id]


def proposed_threshold(current: float, movements: list[float]) -> float:
    """Where the floor goes: just clear of the largest movement readers rejected.

    Derived from the evidence rather than chosen. `movements` are the absolute
    rupee impacts of the runs a quorum called not material, so the smallest floor
    that would have stopped all of them is a hair above the largest, and 1% is
    that hair. Anything more is somebody's preference wearing an argument.
    """
    if not movements:
        raise ApplyRefused(
            "no movement sizes were recorded against this feedback, so the new "
            "floor would have to be chosen rather than derived"
        )
    wanted = max(abs(m) for m in movements) * 1.01
    if wanted <= current:
        raise ApplyRefused(
            f"the current floor of {current:,.0f} already excludes every movement "
            f"this proposal cites, so there is nothing to apply"
        )
    return min(wanted, current * MAX_RAISE_MULTIPLE)


def apply_proposal(
    proposal: Proposal,
    *,
    kpi_id: str,
    current_value: float,
    movements: list[float],
    applied_by: str,
    store: AppliedStore | None = None,
) -> AppliedChange:
    """Apply one proposal, or refuse and say why. Never a silent partial.

    The quorum and contested checks are re-run here rather than trusted from the
    caller: this is the function that changes what readers see, so it is the
    function that has to be sure.
    """
    if not applied_by.strip():
        raise ApplyRefused(
            "an application must name the person making it; an audit record "
            "with no author is not an audit record"
        )
    if proposal.contested:
        raise ApplyRefused(
            "this proposal is contested: readers disagree about it, and averaging "
            "a disagreement is how an engine stops being able to say it does not know"
        )
    if not proposal.applicable:
        raise ApplyRefused(
            f"this proposal has {proposal.supporting} independent submitter(s) and "
            f"needs {QUORUM}; one person is an opinion, and the threshold is what "
            f"makes it a pattern"
        )
    if proposal.target not in CONSUMABLE:
        raise ApplyRefused(
            f"{proposal.target!r} cannot be applied automatically: "
            f"{WHY_NOT.get(proposal.target, 'no consumer exists for this target')}. "
            f"The proposal stands and a person can act on it."
        )

    to_value = proposed_threshold(current_value, movements)
    now = datetime.now(UTC)
    change = AppliedChange(
        change_id=f"ac-{now.strftime('%Y%m%d%H%M%S%f')}",
        kpi_id=kpi_id,
        target=proposal.target,
        field_path=CONSUMABLE[proposal.target],
        from_value=round(current_value, 2),
        to_value=round(to_value, 2),
        applied_by=applied_by.strip(),
        applied_at=now,
        supporting=proposal.supporting,
        submitters=proposal.submitters,
        runs=proposal.runs,
        basis=(
            f"raised to 1% clear of the largest movement "
            f"({max(abs(m) for m in movements):,.0f}) that "
            f"{proposal.supporting} independent readers reported as not worth "
            f"diagnosing, capped at {MAX_RAISE_MULTIPLE:g}x the previous floor"
        ),
    )
    return (store or AppliedStore()).record(change)


__all__ = [
    "CONSUMABLE",
    "MAX_RAISE_MULTIPLE",
    "WHY_NOT",
    "AppliedChange",
    "AppliedStore",
    "ApplyRefused",
    "apply_proposal",
    "proposed_threshold",
]
