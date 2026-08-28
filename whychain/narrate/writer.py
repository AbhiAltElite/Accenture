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

from whychain.narrate.brief import Brief
from whychain.narrate.validate import Sentence

DEFAULT_MODEL = "claude-opus-5"
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
                sentences.append(
                    Sentence(
                        text=(
                            f"Verified causes account for {explained.display} of "
                            "the total movement; the remainder is unexplained."
                        ),
                        cites=("f-explained",),
                    )
                )

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

    Adaptive thinking is on and effort is left at the default: the task is
    short, and the expensive part is being careful with numbers rather than
    reasoning at length. The call is not retried on a validation failure,
    a writer that invented a figure once is not more trustworthy on the second
    attempt, and the template already covers the fallback.
    """

    name = "model"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("WHYCHAIN_NARRATIVE_MODEL", DEFAULT_MODEL)
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or None

    @property
    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def write(self, brief: Brief) -> Written:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": SENTENCE_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Facts available to you:\n"
                        + json.dumps(brief.as_dict(), indent=1)
                        + "\n\nWrite the summary."
                    ),
                }
            ],
        )
        text = next((b.text for b in response.content if b.type == "text"), "{}")
        payload = json.loads(text)
        sentences = tuple(
            Sentence(text=str(s["text"]), cites=tuple(str(c) for c in s["cites"]))
            for s in payload.get("sentences", [])[:MAX_SENTENCES]
        )
        return Written(
            sentences=sentences,
            model_calls=1,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            writer=self.name,
            note=f"constrained call to {self.model} over the evidence table",
        )


def default_writer() -> Writer:
    """The model when it is configured, the template when it is not.

    Availability is decided once, here, rather than being discovered halfway
    through a diagnosis by an exception.
    """
    model = ModelWriter()
    return model if model.available else TemplateWriter()
