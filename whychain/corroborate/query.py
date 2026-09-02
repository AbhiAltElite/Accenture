"""Turning an operational note into the words the people affected would use.

The corroboration stage searches a ticket corpus for text supporting a candidate
cause. What it searches *with* is the problem this module exists for.

An operational note and the complaint it produces are written in different
registers. A terminal writes "turnaround extended by nine days; downstream
allocation reduced to 55 per cent of indent". The dealer writes "no stock at the
depot since Monday, allocation cut to half". They describe one event and share
almost no vocabulary, so a term-frequency query built from the first retrieves
the second only by accident.

The deterministic writer handles this by subtraction: drop the identifier, drop
words that belong to the operational record, search on what is left. That works
where the two registers overlap, which in retail they largely do -- a release
note saying "card entry on the Android checkout flow" and a customer saying "the
card bit just spins" share `card`. It works much less well where they do not,
and the gap was measured rather than assumed: every externally-caused event in
petroleum and power returned an empty record until the missing phrasings were
written into the vocabulary by hand (B-020). That hand-written table is real
per-industry work, and it is the part of onboarding a new business that does not
scale.

So this is a language problem, which is where a model belongs. It proposes the
complaint vocabulary; nothing downstream trusts it:

- retrieval is unchanged and deterministic, and a bad query returns bad matches
  rather than wrong ones
- every retrieved document still goes through the extractor and the verbatim
  citation check before it can support anything
- the proposal is filtered before use -- no digits, no identifiers, bounded
  length -- and an empty or unusable one falls back to the deterministic writer

The worst a failed expansion can do is retrieve nothing, which is the same
outcome as the corpus being silent. It cannot put a number anywhere.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from whychain.corroborate.extract import RETAIL_VOCABULARY, Vocabulary
from whychain.llm import MAX_TOKENS, UNSET, ChatModel, Task, model_for

# The proposal is words, and only words. Anything carrying a digit or an
# underscore is an identifier rather than language, and identifiers are the one
# thing guaranteed not to appear in a complaint.
_NOT_LANGUAGE = re.compile(r"[\d_]")
# Enough to describe a problem, short enough that no single term dominates the
# term-frequency scoring.
MAX_TERMS = 14

SYSTEM = """\
You are given a short internal note describing something that went wrong in a \
business, and a list of the problem categories that business recognises.

Return the words a CUSTOMER or a DEALER would use when writing in to complain \
about the *consequence* of that note. Not the words the note uses.

Rules:

1. Output lowercase words and short phrases separated by spaces. No punctuation, \
no identifiers, no numbers, no explanation, no sentences.
2. Write what the person affected experienced, not what the company did. A note \
about a refinery turnaround becomes "no stock dry out allocation cut supply \
delayed", never "turnaround refinery maintenance".
3. Stay concrete. Do not add sentiment, urgency or apology.
4. At most 14 words in total.\
"""

SCHEMA = {
    "type": "object",
    "properties": {"terms": {"type": "string"}},
    "required": ["terms"],
    "additionalProperties": False,
}


@runtime_checkable
class QueryWriter(Protocol):
    """The whole surface the corroboration stage depends on."""

    def write(self, description: str, fallback: str) -> str: ...


@dataclass
class TemplateQueryWriter:
    """The deterministic writer. `fallback` is already the query it would build."""

    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    note: str = "deterministic query, internal vocabulary subtracted"

    def write(self, description: str, fallback: str) -> str:
        return fallback


@dataclass
class ModelQueryWriter:
    """Model-proposed complaint vocabulary, filtered, with the template beneath it."""

    backend: ChatModel | None = UNSET      # UNSET means "decide"; None means "no model"
    vocabulary: Vocabulary = RETAIL_VOCABULARY

    calls: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    note: str = ""
    proposals: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.backend is UNSET:
            self.backend = model_for(Task.EXPAND)

    @property
    def available(self) -> bool:
        return self.backend is not None

    def write(self, description: str, fallback: str) -> str:
        if not self.available or not description.strip():
            self.note = "no model backend reachable: deterministic query"
            return fallback
        try:
            categories = ", ".join(i for i, _ in self.vocabulary.issue_terms)
            completion = self.backend.complete(
                system=SYSTEM,
                user=f"Categories: {categories}\n\nNote: {description}",
                schema=SCHEMA,
                max_tokens=MAX_TOKENS["expand"],
            )
            # A reading served from disk is a cache hit, not a model call.
            if completion.cached:
                self.cache_hits += 1
            else:
                self.calls += 1
            self.tokens_in += completion.tokens_in
            self.tokens_out += completion.tokens_out
            proposed = _usable(completion.text)
        except Exception as exc:
            # A failed expansion must never fail a diagnosis. The deterministic
            # query is always available and always correct-if-narrow, so the
            # engine degrades to it and the receipt says which was used.
            self.note = f"query expansion failed ({type(exc).__name__}): deterministic query"
            return fallback

        if not proposed:
            self.note = "model proposed nothing usable: deterministic query"
            return fallback

        # Both, not either. The proposal adds the complaint register; the
        # deterministic query keeps whatever vocabulary the two registers already
        # share, so an expansion that misses cannot lose ground the old query held.
        combined = f"{fallback} {proposed}".strip()
        self.proposals[description[:60]] = proposed
        self.note = "model-proposed complaint vocabulary, added to the deterministic query"
        return combined


def _usable(text: str) -> str:
    """Everything the model returned that is language, and little enough of it.

    Applied to the model's output before it reaches retrieval, so an expansion
    that returns prose, an identifier or a paragraph cannot degrade the search.
    """
    raw = text.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            raw = str(parsed.get("terms", ""))
    except (ValueError, TypeError):
        pass

    words: list[str] = []
    for word in re.split(r"[^A-Za-z]+", raw.lower()):
        if len(word) < 3 or _NOT_LANGUAGE.search(word) or word in words:
            continue
        words.append(word)
        if len(words) >= MAX_TERMS:
            break
    return " ".join(words)
