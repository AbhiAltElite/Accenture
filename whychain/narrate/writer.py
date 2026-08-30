"""Who writes the sentences, and what they are allowed to write from.

Two writers implement the same protocol and produce the same shape: a list of
sentences, each carrying the fact ids it rests on. Both are then put through the
same validator. That symmetry is the point; the model does not get a looser
contract than the template, it gets the identical one, and the validator cannot
tell which produced what.

`TemplateWriter` is deterministic and always available. It is not a placeholder
for the model: it is the fallback the system runs on when there is no API key,
when the call fails, and when every model sentence is rejected. A diagnosis
never depends on a network call succeeding.

`ModelWriter` is the second of the design's two model calls. It receives the
brief and nothing else, no warehouse access, no tools, no conversation, and is
constrained by a JSON schema to emit sentences with citations. It is instructed
to copy figures verbatim rather than compute, and the validator assumes it will
sometimes fail to.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from whychain.llm import MAX_TOKENS, UNSET, ChatModel, default_model
from whychain.narrate.brief import Brief
from whychain.narrate.validate import Sentence

MAX_SENTENCES = 8

SYSTEM = """\
You write the summary paragraph of a business diagnosis for a finance audience.

You are given a table of facts. Every fact has an id, a claim, and a `display`
string that is the ONLY way its number may be written.

Rules, all of which are checked mechanically after you answer:

1. Every sentence must cite at least one fact id from the table.
2. Any figure you print must be copied character for character from the
   `display` field of a fact that same sentence cites. Do not convert, round,
   restate as a proportion, or combine figures. You cannot do arithmetic here;
   arithmetic already happened.
3. Do not name a person, role, region, channel or category that does not appear
   in the table.
4. Facts whose state is `rejected` were tested and ruled out. You may say they
   were ruled out. You may not state them as causes.
5. If the verdict is `unknown`, say the engine could not identify a cause and
   say what would settle it. Do not offer a best guess.

Write plainly, in the register of an internal memo: short sentences, no
adjectives that are not load-bearing, no summary of your own reasoning.\
"""

# `strict: true` plus a closed schema means the response either matches this
# shape or the request fails; there is no partially-parsed middle state to
# handle downstream.
SENTENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "maxItems": MAX_SENTENCES,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "cites"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentences"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Written:
    """Sentences plus what producing them cost. Both go on the receipt."""

    sentences: tuple[Sentence, ...]
    model_calls: int
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    writer: str = "template"
    note: str = ""


class Writer(Protocol):
    def write(self, brief: Brief) -> Written: ...


class TemplateWriter:
    """Deterministic prose, assembled from the same brief the model would read.

    Every sentence here is built by concatenating a fact's own `display` string,
    so it passes the numeral check by construction. That is not a trick to
    satisfy the validator; it is what the validator is asserting about the
    model's output too.
    """

    name = "template"

    def write(self, brief: Brief) -> Written:
        sentences: list[Sentence] = []
        movement = brief.by_id("f-movement")
        pct = brief.by_id("f-movement-pct")
        where = f" in {brief.region}" if brief.region else ""

        if movement is not None:
            cites = ["f-movement"] + (["f-movement-pct"] if pct else [])
            tail = f" ({pct.display})" if pct else ""
            sentences.append(
                Sentence(
                    text=(
                        f"{brief.kpi.replace('_', ' ').capitalize()}{where} moved "
                        f"{movement.display}{tail} per day between "
                        f"{brief.window[0]} and {brief.window[1]}."
                    ),
                    cites=tuple(cites),
                )
            )

        if brief.verdict == "unknown":
            sentences.append(
                Sentence(
                    text=(
                        "No cause passed every causal test, so the engine is "
                        "reporting an unknown rather than its best guess."
                    ),
                    cites=("f-confidence",),
                )
            )
        else:
            causes = [f for f in brief.facts if f.kind == "cause"]
            for fact in causes[:3]:
                label = fact.claim.removeprefix("verified cause: ").rstrip(".")
                sentences.append(
                    Sentence(
                        text=f"{label}, {fact.display} per day.",
                        cites=(fact.id,),
                    )
                )
            explained = brief.by_id("f-explained")
            if explained is not None and causes:
                # Three different sentences, because the old single one asserted
                # a remainder unconditionally and so contradicted itself the
                # moment coverage reached 100%: "causes account for all of it;
                # the remainder is unexplained". Worse, the case where that
                # happened most often was the one where the causes overlap, and
                # there the per-cause figures a reader can add up do not
                # reconcile with the total at all unless they are told why.
                overlap = brief.by_id("f-overlap")
                movement = brief.by_id("f-movement")
                if overlap is not None:
                    text = (
                        f"Verified causes account for {explained.display} of the "
                        f"total movement, but their individual contributions sum "
                        f"to {overlap.display} of it, so they overlap and the "
                        f"split between them is unresolved."
                    )
                    cites = ("f-explained", "f-overlap")
                elif movement is not None and explained.value == movement.value:
                    text = (
                        f"Verified causes account for {explained.display}, which "
                        f"is the whole of the movement."
                    )
                    cites = ("f-explained",)
                else:
                    text = (
                        f"Verified causes account for {explained.display} of "
                        "the total movement; the remainder is unexplained."
                    )
                    cites = ("f-explained",)
                sentences.append(Sentence(text=text, cites=cites))

        ruled_out = [f for f in brief.facts if f.kind == "ruled_out"]
        if ruled_out:
            sentences.append(
                Sentence(
                    text=(
                        f"{len(ruled_out)} other candidate(s) were tested and "
                        "ruled out before this conclusion was reached."
                    ),
                    cites=tuple(f.id for f in ruled_out[:4]),
                )
            )

        decision = brief.by_id("f-decision-1")
        if decision is not None:
            sentences.append(
                Sentence(
                    text=decision.claim.removeprefix("decision: ").capitalize()
                    + ".",
                    cites=("f-decision-1",),
                )
            )

        gap = brief.by_id("f-gap")
        if gap is not None:
            # The verdict string is a machine label; the reason after it is the
            # sentence a person reads. Printing both is printing the schema.
            _, _, reason = gap.claim.partition(": ")
            sentences.append(Sentence(text=reason or gap.claim, cites=("f-gap",)))

        confidence = brief.by_id("f-confidence")
        if confidence is not None:
            sentences.append(
                Sentence(
                    text=(
                        f"Confidence in this diagnosis is {confidence.display} "
                        f"({confidence.state})."
                    ),
                    cites=("f-confidence",),
                )
            )

        return Written(
            sentences=tuple(sentences),
            model_calls=0,
            writer=self.name,
            note="deterministic template over the evidence table; no model call",
        )


class ModelWriter:
    """The constrained call. Reads the brief, writes cited sentences, nothing else.

    The call is not retried on a validation failure. A writer that invented a
    figure once is not more trustworthy on the second attempt, and the template
    already covers the fallback.
    """

    name = "model"

    def __init__(self, backend: ChatModel | None = UNSET):
        # `UNSET` means "decide for me"; `None` means "run without a model".
        # Written as `backend or default_model(...)` these were the same thing,
        # so a request that explicitly asked for the deterministic path got the
        # model anyway -- 30 seconds of narration on a page whose other eight
        # stages had already finished in under a second.
        self.backend = (
            default_model(os.environ.get("WHYCHAIN_NARRATIVE_MODEL"))
            if backend is UNSET else backend
        )

    @property
    def model(self) -> str:
        return self.backend.name if self.backend else "none"

    @property
    def available(self) -> bool:
        return self.backend is not None

    def write(self, brief: Brief) -> Written:
        if self.backend is None:
            raise RuntimeError("no model backend reachable")

        completion = self.backend.complete(
            system=SYSTEM,
            user=(
                "Facts available to you:\n"
                + json.dumps(brief.as_dict(), indent=1)
                + "\n\nWrite the summary."
            ),
            schema=SENTENCE_SCHEMA,
            max_tokens=MAX_TOKENS["narrate"],
        )
        payload = json.loads(completion.text or "{}")
        sentences = tuple(
            Sentence(text=str(s["text"]), cites=tuple(str(c) for c in s["cites"]))
            for s in payload.get("sentences", [])[:MAX_SENTENCES]
        )
        return Written(
            sentences=sentences,
            model_calls=1,
            cache_hits=1 if completion.cached else 0,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
            writer=self.name,
            note=(
                f"constrained call to {completion.backend} · {completion.model} "
                "over the evidence table"
            ),
        )


def default_writer() -> Writer:
    """The model when it is configured, the template when it is not.

    Availability is decided once, here, rather than being discovered halfway
    through a diagnosis by an exception.
    """
    model = ModelWriter()
    return model if model.available else TemplateWriter()
