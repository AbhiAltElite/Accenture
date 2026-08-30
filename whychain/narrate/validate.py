"""The gate every sentence passes before a reader sees it.

This is the stage that makes "the model never decides what is true" an
enforced property rather than a slogan. The writer produces sentences; this
module decides whether each one is allowed out. A sentence that fails is
dropped, and the drop is reported, never silently patched into something that
passes.

Four checks, and each exists because of a specific way this goes wrong.

**Binding.** Every sentence must cite at least one fact id that exists in the
brief. An uncited sentence is fluent text with no accountable source, which is
exactly the output this project treats as worse than silence.

**Numerals.** Every number printed in a sentence must appear verbatim in a
fact that sentence cites, in its formatted `display` value, or inside the text
of its claim. Not "be close to", appear. The writer is given the formatted
string and copies it; it is not permitted to do arithmetic, so a number it
produced by any other route is by definition invented. Unit suffixes are
compared too, so `5%` cannot satisfy a fact whose display is `+5.0 percentage
points` (BUGS.md T-02).

**Entities.** Named regions, roles, channels and categories must come from the
brief's entity set. A narrative that names the wrong owner is more damaging than
one that names none, because somebody acts on it.

**Rejected causes.** A sentence may not state a rejected candidate as a cause.
The brief already withholds that framing, so this check catches the case where a
writer paraphrases a `ruled_out` fact into an assertion (BUGS.md T-12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from whychain.narrate.brief import Brief

# Numerals as a reader sees them: an optional sign, digits with separators, an
# optional decimal, and an optional unit marker that is part of the claim.
# The separator must sit *between* digits. Written as `\d[\d,]*` it also
# swallowed a trailing comma, so "accounts for ₹35,323, which is all of it"
# scanned as the numeral "₹35,323," -- a token that appears in no fact, and the
# sentence was rejected as fabricated for having a comma after the figure. A
# validator with a false positive is a validator someone switches off, and this
# one would have quietly dropped model-written sentences for their punctuation.
_NUMERAL = re.compile(
    r"[+-]?₹?\s?\d+(?:,\d+)*(?:\.\d+)?\s*(?:percentage points?|%|hours?)?",
    re.IGNORECASE,
)

# Bare small integers inside prose ("3 candidates were ruled out") are counts of
# things the reader can see listed, not claims about the data.
_ALLOWED_BARE = frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "24", "48"})

# ISO dates are removed before the numeral scan. A date is not a measurement,
# and leaving it in makes the check fire on the year, which taught us that a
# validator with a false positive is a validator someone will switch off.
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Words that turn a mention into an assertion of cause.
_CAUSAL_VERBS = (
    "caused", "drove", "was the cause", "is the cause", "explains",
    "responsible for", "led to", "resulted in", "because of",
)


class Failure(StrEnum):
    UNBOUND = "unbound"
    INVENTED_NUMERAL = "invented_numeral"
    UNKNOWN_ENTITY = "unknown_entity"
    REJECTED_AS_CAUSE = "rejected_as_cause"


@dataclass(frozen=True)
class Sentence:
    """One unit of narrative and the facts it rests on."""

    text: str
    cites: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"text": self.text, "cites": list(self.cites)}


@dataclass(frozen=True)
class Rejection:
    sentence: str
    failure: Failure
    detail: str

    def as_dict(self) -> dict:
        return {
            "sentence": self.sentence,
            "failure": self.failure.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ValidationResult:
    """What survived, what did not, and why."""

    accepted: tuple[Sentence, ...]
    rejected: tuple[Rejection, ...]

    @property
    def clean(self) -> bool:
        return not self.rejected

    def as_dict(self) -> dict:
        return {
            "accepted": [s.as_dict() for s in self.accepted],
            "rejected": [r.as_dict() for r in self.rejected],
            "checks_run": [f.value for f in Failure],
            "clean": self.clean,
        }


def _normalise(numeral: str) -> str:
    """Compare numbers the way a reader reads them, not byte for byte."""
    text = numeral.strip().lower().replace(",", "").replace(" ", "")
    text = text.replace("percentagepoints", "pp").replace("percentagepoint", "pp")
    text = text.replace("hours", "h").replace("hour", "h")
    return text.lstrip("+")


def _numerals(text: str) -> list[str]:
    return [m.group(0) for m in _NUMERAL.finditer(_ISO_DATE.sub(" ", text))]


def _cited_text(sentence: Sentence, brief: Brief) -> str:
    """Everything the cited facts actually say, claim and display together.

    The rule the checks below enforce is one sentence long: *a token that
    appears verbatim in a fact this sentence cites is not invented*. A cause
    described as "Release 4.05 broke card entry" carries `4.05` inside the
    evidence itself; flagging it as a fabricated figure would be the validator
    failing to distinguish quoting from computing, and would train a reader to
    ignore its verdicts.
    """
    return " ".join(
        f"{f.claim} {f.display}"
        for c in sentence.cites
        if (f := brief.by_id(c)) is not None
    ).lower()


def check_binding(sentence: Sentence, brief: Brief) -> Rejection | None:
    if not sentence.cites:
        return Rejection(sentence.text, Failure.UNBOUND, "cites no evidence")
    unknown = [c for c in sentence.cites if brief.by_id(c) is None]
    if unknown:
        return Rejection(
            sentence.text,
            Failure.UNBOUND,
            f"cites {', '.join(unknown)}, which is not in the evidence table",
        )
    return None


def check_numerals(sentence: Sentence, brief: Brief) -> Rejection | None:
    allowed = {
        _normalise(f.display)
        for c in sentence.cites
        if (f := brief.by_id(c)) is not None
    }
    # A cited fact's own display may be split by the writer across a currency
    # symbol; compare on the digits too, but only for facts it actually cites.
    allowed |= {a.lstrip("₹") for a in allowed}

    quoted = _cited_text(sentence, brief)
    for numeral in _numerals(sentence.text):
        norm = _normalise(numeral)
        if norm in _ALLOWED_BARE or norm.lstrip("₹") in allowed or norm in allowed:
            continue
        # Quoted verbatim from the evidence rather than computed from it.
        if numeral.strip().lower() in quoted:
            continue
        return Rejection(
            sentence.text,
            Failure.INVENTED_NUMERAL,
            f"{numeral.strip()!r} does not appear in any fact this sentence cites",
        )
    return None


def check_entities(sentence: Sentence, brief: Brief, known: frozenset[str]) -> Rejection | None:
    """Capitalised or snake_case names must be ones the brief supplied.

    Deliberately narrow: it looks for the shapes real entities take in this
    system, a proper noun and a role identifier, rather than trying to parse
    English. A check that flags ordinary words gets switched off, and a check
    that is switched off protects nothing.
    """
    vocabulary = {e.lower() for e in known} | {e.lower() for e in brief.entities}
    quoted = _cited_text(sentence, brief)
    candidates = re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", sentence.text)
    for candidate in candidates:
        if candidate.lower() in vocabulary or candidate.lower() in quoted:
            continue
        return Rejection(
            sentence.text,
            Failure.UNKNOWN_ENTITY,
            f"names {candidate!r}, which is not an entity in the evidence table",
        )
    return None


def check_rejected(sentence: Sentence, brief: Brief) -> Rejection | None:
    lowered = sentence.text.lower()
    for cite in sentence.cites:
        fact = brief.by_id(cite)
        if fact is None or fact.state != "rejected":
            continue
        if any(verb in lowered for verb in _CAUSAL_VERBS):
            return Rejection(
                sentence.text,
                Failure.REJECTED_AS_CAUSE,
                f"states {cite}, a rejected candidate, as a cause",
            )
    return None


def validate(
    sentences: list[Sentence], brief: Brief, *, known_entities: frozenset[str] = frozenset()
) -> ValidationResult:
    """Run every check on every sentence. First failure wins, and is reported.

    Checks are not short-circuited across sentences: one bad sentence removes
    itself, not the narrative. A diagnosis that loses a sentence to the
    validator is still a diagnosis, and the receipt says how many it lost.
    """
    accepted: list[Sentence] = []
    rejected: list[Rejection] = []

    for sentence in sentences:
        failure = (
            check_binding(sentence, brief)
            or check_numerals(sentence, brief)
            or check_entities(sentence, brief, known_entities)
            or check_rejected(sentence, brief)
        )
        if failure is None:
            accepted.append(sentence)
        else:
            rejected.append(failure)

    return ValidationResult(accepted=tuple(accepted), rejected=tuple(rejected))
