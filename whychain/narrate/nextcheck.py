"""What to look at next, when the engine cannot say what happened.

The most useful sentence this product produces is not the diagnosis. It is the
one an analyst gets on the days there *is* no diagnosis: what was ruled out, and
therefore what is worth the next hour. An abstention that only says "unknown"
wastes the hour as surely as a wrong answer does.

That sentence was three template branches -- untestable candidate, thin
coverage, everything else -- and templates are exactly wrong for it. The useful
next check depends on which candidates were rejected and *why*, which dimensions
the movement is concentrated in, which sources were stale and which documents
were read; on the particular shape of a particular failure, in other words,
which is what language is for and what a three-way branch cannot reach.

So the model writes it, under the same contract as everything else it writes
here: it is given a closed set of facts, it may name nothing outside them, and a
deterministic check rejects the sentence before a reader sees it. Three rules,
and the third is the one that matters:

**It may not propose a cause.** This is the one place in the engine where a
model is asked to be constructive about a movement nobody has explained, which
is precisely where a plausible-sounding suggestion becomes a stated cause in
somebody's retelling. The sentence must be an *action* -- something to look at,
pull, or ask -- and a sentence that reads as an explanation is dropped.

**It may name only what it was given.** Candidate ids, dimension values, source
names, roles. Anything else is an invention and the check finds it, because the
allowed set is assembled from the run rather than from a vocabulary.

**It falls back to the template.** The template branches are still there and
still correct. This improves the sentence when it can and never blocks the
answer, which is the same bargain every other model stage here makes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from whychain.llm import MAX_TOKENS, UNSET, ChatModel, ModelError, Task, model_for

SYSTEM = """An analyst has asked why a business metric moved and the engine could not tell
them. You write the single next thing worth checking.

You are given what was ruled out and why, what is blocking, and the names that
exist in this run. Rules, all checked mechanically after you answer:

1. Propose an ACTION, not an explanation. Something to pull, compare, ask or
   confirm. "Check whether X" is an action. "X caused the fall" is not, and is
   rejected.
2. Never state or imply a cause. Candidates listed as ruled out were tested and
   failed; you may say they were ruled out and you may not revive them.
3. Name only identifiers, dimensions, sources and roles that appear in the facts
   you are given. Do not invent a system, a team, a region or a report.
4. Any figure you print must appear in the facts you were given, character
   for character. Do not convert, round or restate one.
5. One sentence, under 30 words, imperative, no preamble.

Write as one analyst leaving a note for another.
"""

SCHEMA = {
    "type": "object",
    "properties": {"next_check": {"type": "string"}},
    "required": ["next_check"],
    "additionalProperties": False,
}

MAX_WORDS = 30

# Phrasings that assert rather than propose. A sentence containing one of these
# is making a claim about why the metric moved, which is the single thing this
# stage may not do.
CAUSAL_PHRASES = (
    "caused by", "because of", "due to", "driven by", "explains the",
    "was caused", "is the cause", "responsible for", "resulted from",
    "attributable to", "led to the",
)


@dataclass(frozen=True)
class NextCheck:
    """A proposed next step, and the audit of where it came from."""

    text: str
    writer: str
    model_calls: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    rejected: str = ""

    @property
    def fell_back(self) -> bool:
        return bool(self.rejected) or self.writer == "template"

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "writer": self.writer,
            "model_calls": self.model_calls,
            "cache_hits": self.cache_hits,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "rejected": self.rejected,
            "fell_back": self.fell_back,
        }


def _words(text: str) -> list[str]:
    """Tokens, with sentence punctuation stripped from the ends.

    Identifiers here really do contain dots and dashes -- `rel-4.05`,
    `pos_txn` -- so they cannot simply be excluded from a token, and a token
    that keeps its full stop is reported as an unknown entity called
    "window." rather than as the word "window".
    """
    return [
        w.strip(".,;:-_")
        for w in re.findall(r"[A-Za-z][A-Za-z0-9._-]*", text)
        if w.strip(".,;:-_")
    ]


# An invention is a *name*, and a name looks like one. Checking every word
# against the run's own vocabulary was tried first and is wrong: it rejected
# "shipped", "request" and "affected", so almost nothing the model wrote could
# pass, and widening the allowed list until they did would have left the check
# doing nothing.
#
# A hallucinated system, team, region or report is capitalised, or carries an
# underscore, a dash or a digit -- `Salesforce`, `pos_txn`, `rel-4.05`,
# `Region-4`. Ordinary lowercase English cannot name one. So only tokens that
# look like names are checked, and they are checked strictly.
def _looks_like_a_name(token: str, first_in_sentence: bool) -> bool:
    # An underscore or a digit is a name marker on its own: ordinary English has
    # neither. A hyphen is not -- "re-running" and "re-post" are words, and
    # treating them as inventions rejected sentences that were perfectly good.
    # A hyphenated token is a name only when something else says so.
    if "_" in token or any(ch.isdigit() for ch in token):
        return True
    return token[:1].isupper() and not first_in_sentence


def _names(text: str) -> list[str]:
    """The tokens in `text` that are claiming to be something's name."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for i, token in enumerate(_words(sentence)):
            if _looks_like_a_name(token, first_in_sentence=i == 0):
                out.append(token)
    return out


def validate(text: str, allowed: frozenset[str], facts: str = "") -> str:
    """Empty when the sentence may be shown; otherwise why it may not be.

    Deterministic, and it runs whatever wrote the sentence. The model does not
    mark its own work here any more than it does anywhere else in this engine.
    """
    stripped = text.strip()
    if not stripped:
        return "the writer returned nothing"
    if len(_words(stripped)) > MAX_WORDS:
        return f"longer than {MAX_WORDS} words"

    # Before the figure check, and deliberately: asserting a cause is the more
    # serious fault and should be what a reader is told about, and a candidate
    # id like `rel-4.05` would otherwise get the sentence rejected as arithmetic.
    lowered = stripped.lower()
    for phrase in CAUSAL_PHRASES:
        if phrase in lowered:
            return f"asserts a cause ({phrase!r}); this sentence proposes an action"

    # Before the figure check. An invented identifier that happens to carry a
    # digit -- `orders_v2` -- was being reported as arithmetic, which is a true
    # statement about the sentence and the wrong thing to tell anyone about it.
    unknown = [n for n in _names(stripped) if n.lower() not in allowed]
    if unknown:
        return f"names {', '.join(sorted(set(unknown))[:4])}, which this run does not contain"

    # Figures are allowed, and must be copied. This began as a blanket ban and
    # the ban was wrong: "the two systems disagree by 39%" is the most useful
    # thing this sentence can say, and the deterministic template it replaces
    # says exactly that. What must not happen is a figure the run does not
    # contain, which is the same rule the narrative validator enforces -- a
    # numeral has to appear in the facts, character for character.
    #
    # Known identifiers are removed first, or the `4.05` in a candidate id
    # counts as arithmetic.
    residue = lowered
    for term in sorted(allowed, key=len, reverse=True):
        if any(ch.isdigit() for ch in term):
            residue = residue.replace(term, " ")
    invented = [
        n for n in re.findall(r"\d+(?:[.,]\d+)*", residue) if n not in facts
    ]
    if invented:
        return (
            f"prints {', '.join(sorted(set(invented))[:3])}, which does not "
            f"appear in the facts"
        )
    return ""


def _facts(result: dict) -> dict:
    """The closed set the model may write from. Assembled from the run."""
    abstention = result.get("abstention") or {}
    return {
        "metric": result.get("kpi_id"),
        "region": result.get("region"),
        "window": result.get("window"),
        "verdict": result.get("verdict"),
        "coverage": abstention.get("coverage"),
        "blocking": abstention.get("blocking") or [],
        "ruled_out": [
            {
                "candidate": r.get("candidate"),
                "verdict": r.get("verdict"),
                "reason": r.get("reason"),
            }
            for r in (abstention.get("ruled_out") or [])
        ],
        "reconciliation": (result.get("reconciliation") or {}).get("state"),
        "template_suggestion": abstention.get("next_check"),
    }


def allowed_terms(result: dict, extra: frozenset[str] = frozenset()) -> frozenset[str]:
    """Every name this run actually contains, lowercased."""
    out: set[str] = set()

    def add(value):
        if isinstance(value, str):
            out.update(w.lower() for w in _words(value))
        elif isinstance(value, dict):
            for v in value.values():
                add(v)
        elif isinstance(value, list | tuple):
            for v in value:
                add(v)

    add(_facts(result))
    add(list(extra))
    return frozenset(out)


def propose(
    result: dict,
    *,
    fallback: str,
    backend: ChatModel | None = UNSET,
    extra_terms: frozenset[str] = frozenset(),
) -> NextCheck:
    """Write the next check, or hand back the template and say why.

    `fallback` is the deterministic sentence, which is always correct and often
    generic. Nothing here is allowed to make the answer worse than it.
    """
    model = model_for(Task.NARRATE) if backend is UNSET else backend
    if model is None:
        return NextCheck(text=fallback, writer="template")

    facts = _facts(result)
    serialised = json.dumps(facts, indent=1)
    try:
        completion = model.complete(
            system=SYSTEM,
            user="Facts:\n" + serialised + "\n\nWrite the next check.",
            schema=SCHEMA,
            max_tokens=MAX_TOKENS["intent"],
        )
        proposed = str(json.loads(completion.text or "{}").get("next_check", ""))
    except (ModelError, ValueError, KeyError, TypeError) as exc:
        return NextCheck(
            text=fallback, writer="template",
            rejected=f"the model could not be read ({type(exc).__name__})",
        )
    except Exception as exc:                       # a backend failure, not a bug
        return NextCheck(
            text=fallback, writer="template",
            rejected=f"the model failed ({type(exc).__name__})",
        )

    why = validate(proposed, allowed_terms(result, extra_terms), facts=serialised)
    calls = 0 if completion.cached else 1
    if why:
        return NextCheck(
            text=fallback, writer="model -> template", rejected=why,
            model_calls=calls, cache_hits=1 if completion.cached else 0,
            tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
        )
    return NextCheck(
        text=proposed.strip(), writer="model",
        model_calls=calls, cache_hits=1 if completion.cached else 0,
        tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
    )


__all__ = ["MAX_WORDS", "NextCheck", "allowed_terms", "propose", "validate"]
