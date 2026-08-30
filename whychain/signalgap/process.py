"""Reading a planning document to find out what the process consumes.

`SignalsConsumed` has claimed since it was written that it is "derived at
contract registration by reading a real SOP, never hand-written". Until now
that was aspirational: the spans were typed into YAML by a person who had read
the document. Answer 2's whole premise is that we know what a process ingests,
so the premise was being asserted rather than established, and a reader who
asked how we knew would have got an uncomfortable answer.

This module establishes it. A model reads the document and reports which inputs
the cycle consumes, quoting the sentence that says so. Then deterministic code
does the part that matters:

**Every quote is located in the source.** The span comes from `str.find`, never
from the model. A model that paraphrases, summarises, or invents an input
produces a sentence that is not in the document, the span will not resolve, and
the signal is dropped with a reason. This is the same discipline as the ticket
extractor and for the same reason: a citation that cannot be checked is worse
than no citation, because it looks like one.

**The model is not asked what is missing.** It reports what the document says
is consumed, and nothing else. The gap, which is the finding, is a set
difference computed later against the external feed. Asking a model "is this
process missing a weather signal?" would be asking it to make the finding, and
the finding is the one thing that must not come from a model.

**No backend means UNKNOWN, not a guess.** With no model reachable this returns
`Coverage.UNKNOWN`, `find_gap` then returns `coverage_unknown`, and Answer 2
declines rather than inferring a gap from a document nobody read. That path
already exists and is tested; this module simply feeds it honestly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from whychain.contracts.models import Coverage, ExtractedSignal, SignalsConsumed
from whychain.llm import MAX_TOKENS, ChatModel, default_model

SYSTEM = """\
You read business process documents and report which inputs the process \
consumes.

An input is data the process takes in to do its work: sales history, inventory \
levels, capacity figures, budgets, forecasts, external feeds, anything the \
document says is gathered, assembled, extracted, supplied or provided.

For each one, return:

- `signal`: a short snake_case identifier, e.g. historical_sales, \
inventory_position, capacity_metrics, financial_plan, competitor_pricing, \
weather_forecast
- `quote`: the sentence from the document that says this input is consumed, \
copied **character for character**. Do not fix spelling, do not tidy grammar, \
do not join two sentences. The quote is checked against the document and the \
entry is discarded if it does not appear there verbatim.

Rules:

1. Report only inputs the document actually names. Do not add inputs a process \
like this usually has. An input you infer rather than read is a fabrication, \
and it will be checked.
2. Do not report what the process is missing, and do not comment on gaps. You \
are transcribing what the document says, not assessing it.
3. Outputs, steps, meetings and escalation paths are not inputs. "Agree a \
single plan of record" is a step; "Historical sales are extracted" is an input.\
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["signal", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["signals"],
    "additionalProperties": False,
}

_SNAKE = re.compile(r"[^a-z0-9]+")


def _identifier(raw: str) -> str:
    """Normalise the model's id. Presentation, not meaning."""
    return _SNAKE.sub("_", str(raw).strip().lower()).strip("_")


@dataclass
class ProcessReading:
    """What was read, what was discarded, and what it cost."""

    consumed: SignalsConsumed
    dropped: tuple[str, ...] = field(default_factory=tuple)
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    note: str = ""

    def as_yaml(self) -> str:
        """The block to paste into a contract, ready to be reviewed by a human.

        Deliberately not written to the contract file automatically. A change to
        what a KPI's process is believed to consume changes what Answer 2 will
        accuse that process of missing, and that is a claim somebody should put
        their name to.
        """
        c = self.consumed
        if not c.extracted:
            return "signals_consumed:\n  coverage: unknown\n"
        lines = [
            "signals_consumed:",
            f"  derived_from: {c.derived_from}",
            f"  coverage: {c.coverage.value}",
            f"  extracted_at: {c.extracted_at.isoformat() if c.extracted_at else ''}",
            "  extracted:",
        ]
        lines.extend(
            f"    - {{signal: {s.signal}, span: [{s.span[0]}, {s.span[1]}]}}"
            for s in c.extracted
        )
        return "\n".join(lines) + "\n"


def read_process(
    path: str | Path,
    *,
    backend: ChatModel | None = None,
) -> ProcessReading:
    """Read a process document and return what it says the cycle consumes."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    backend = backend or default_model()

    if backend is None:
        return ProcessReading(
            consumed=SignalsConsumed(coverage=Coverage.UNKNOWN),
            note=(
                "no model backend reachable; the document was not read and "
                "coverage is reported as unknown rather than assumed"
            ),
        )

    completion = backend.complete(
        system=SYSTEM,
        user=f"Document: {path.name}\n\n{text}",
        schema=SCHEMA,
        max_tokens=MAX_TOKENS["signalgap"],
    )
    payload = json.loads(completion.text or "{}")

    extracted: list[ExtractedSignal] = []
    dropped: list[str] = []
    seen: set[str] = set()

    for row in payload.get("signals", []):
        signal = _identifier(row.get("signal", ""))
        quote = str(row.get("quote", "")).strip()
        if not signal or not quote:
            dropped.append("entry with no signal or no quote")
            continue

        start = text.find(quote)
        if start < 0:
            # Not in the document. Whether the model paraphrased or invented it,
            # the claim cannot be shown to a reader, so it does not ship.
            dropped.append(f"{signal}: quote not found in {path.name}")
            continue
        if signal in seen:
            dropped.append(f"{signal}: reported twice")
            continue

        seen.add(signal)
        extracted.append(ExtractedSignal(signal=signal, span=(start, start + len(quote))))

    # Coverage is evidence about our own reading, not about the process. Some
    # entries discarded means we did not fully read the document, and saying so
    # is what stops a partial reading being used as a complete one.
    if not extracted:
        coverage, derived = Coverage.UNKNOWN, None
    elif dropped:
        coverage, derived = Coverage.PARTIAL, str(path)
    else:
        coverage, derived = Coverage.COMPLETE, str(path)

    return ProcessReading(
        consumed=SignalsConsumed(
            derived_from=derived,
            extracted=tuple(extracted),
            extracted_at=datetime.now(UTC) if derived else None,
            coverage=coverage,
        ),
        dropped=tuple(dropped),
        model_calls=1,
        tokens_in=completion.tokens_in,
        tokens_out=completion.tokens_out,
        note=(
            f"{completion.backend} · {completion.model}; "
            f"{len(extracted)} input(s) read from {path.name}"
            + (f", {len(dropped)} discarded" if dropped else "")
        ),
    )


def main() -> int:
    """`python -m whychain.signalgap.process <document>`.

    Prints the block a human reviews and pastes into the contract, plus what was
    discarded, because the discards are the interesting part when checking
    whether the reading can be trusted.
    """
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m whychain.signalgap.process <process-document>")
        return 2

    reading = read_process(sys.argv[1])
    print(f"# {reading.note}\n")
    print(reading.as_yaml())
    if reading.dropped:
        print("# discarded, and why:")
        for reason in reading.dropped:
            print(f"#   {reason}")
    if reading.consumed.coverage is Coverage.UNKNOWN:
        print("# Answer 2 will return coverage_unknown for a contract in this state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
