"""Turning a question into a query the engine can actually run.

Everywhere else in this console the reader must already know the KPI id, the
region and the window before they can ask anything. That is the analyst's
interface, not the business user's, and the brief names "LLM-assisted intent
understanding" as its own solutioning area for exactly this reason: *"why did
West revenue drop last week?"* is a sentence, and turning a sentence into a
structured query is a language problem.

**The model proposes; the contract registry decides.** That division is what
makes this safe, and it is stronger here than anywhere else the model is used,
because the proposal is constrained twice over:

1. **The schema cannot express an invalid answer.** `kpi_id` and `region` are
   JSON-schema enums built from the registry and the warehouse at request time,
   so a KPI this business does not have is not a thing the model can return. It
   is not validated away afterwards; it is unrepresentable.
2. **Everything it does return is checked anyway.** The KPI must resolve in the
   registry, the region must be one the caller is entitled to see, and the dates
   must parse, be ordered, and fall inside the coverage the warehouse actually
   has. A schema is a contract with a cooperative counterparty; the checks are
   for the other case.

**Ambiguity is answered, not guessed at.** "Why are sales down?" names no
region and no window. The honest response is to ask which, and the engine
already has somewhere to put that: objective 5 requires it to request
clarification rather than proceed on insufficient evidence, and `Abstention`
already carries a `question` the console renders. An unclear question routes
into the same mechanism as unclear evidence, which is the behaviour the brief
asks for rather than a special case bolted on beside it.

**Nothing here reaches a number.** The output is a query. The engine then runs
exactly as it would have if the reader had filled the form in by hand, and every
figure is computed by the same deterministic path. The worst a bad
interpretation can do is answer a question the reader did not ask -- which the
console shows them, in words, before the answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from whychain.llm import MAX_TOKENS, UNSET, ChatModel, Task, model_for

# Long enough for "the last quarter", short enough that a mis-parsed date cannot
# ask for a scan of the whole warehouse.
MAX_WINDOW_DAYS = 120
# What "recently" means when a question implies a window without naming one.
DEFAULT_WINDOW_DAYS = 7

SYSTEM = """\
You turn a business question about a metric into a structured query. You do not \
answer the question and you do not analyse anything: something else does that.

Return:

- `kpi_id`: which metric the question is about. Choose only from the list given.
- `region`: which region, or null if the question does not name one.
- `start` and `end`: the window, as YYYY-MM-DD. Resolve relative phrases like \
"last week" or "in July" against TODAY, which is given to you.
- `clarification`: null if the question is clear enough to run. Otherwise ONE \
short question back to the reader naming exactly what is missing or ambiguous.
- `reading`: one plain sentence restating what you understood, so the reader can \
see whether you understood them.

Rules:

1. If the question does not identify a metric, set `clarification` and name the \
metrics available. Do not guess.
2. If it names no window, use the most recent {default_days} days and say so in \
`reading`. That is a default, not a guess, and it does not need clarification.
3. If a question could reasonably mean two different metrics, ask rather than \
choose.
4. Never invent a metric or a region that is not in the lists given.\
"""


def _first_json_object(text: str) -> dict:
    """The first balanced JSON object in a response, whatever surrounds it.

    `json.loads` on the whole body assumes the model returns JSON and nothing
    else. Several of the free open-weight models are reasoning models: they emit
    their working first and the object afterwards, and one of them wrapped it in
    a fenced code block. Both are reasonable behaviours from the model and a
    parse failure here would report them as "the question could not be read",
    which is a lie about whose fault it is.

    Scanning for the first balanced object is not a repair of bad output; the
    object still has to parse and still has to satisfy the checks below. It only
    stops the surrounding prose from being treated as a failure.
    """
    text = (text or "").strip()
    if not text:
        return {}
    start = text.find("{")
    if start < 0:
        return {}
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:index + 1])
                except ValueError:
                    return {}
    return {}


@dataclass(frozen=True)
class Intent:
    """What a question was understood to mean, and whether it can be run."""

    question: str
    kpi_id: str | None = None
    region: str | None = None
    start: date | None = None
    end: date | None = None
    reading: str = ""
    clarification: str | None = None
    # Why the engine could not run this, when the failure is ours rather than a
    # genuine ambiguity in the question.
    problem: str | None = None
    model: str = ""
    model_calls: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    rejected: tuple[str, ...] = field(default_factory=tuple)

    @property
    def runnable(self) -> bool:
        return bool(
            self.kpi_id and self.start and self.end
            and not self.clarification and not self.problem
        )

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "runnable": self.runnable,
            "kpi_id": self.kpi_id,
            "region": self.region,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "reading": self.reading,
            "clarification": self.clarification,
            "problem": self.problem,
            "rejected": list(self.rejected),
            "model": self.model,
            "model_calls": self.model_calls,
            "cache_hits": self.cache_hits,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


def _schema(kpi_ids: list[str], regions: list[str]) -> dict:
    """A schema in which an invalid query cannot be expressed.

    The enums come from this deployment's registry and warehouse, so "which
    metrics exist" is answered by the same source the engine runs on rather than
    by anything the model believes about the world.
    """
    return {
        "type": "object",
        "properties": {
            "kpi_id": {"type": ["string", "null"], "enum": [*kpi_ids, None]},
            "region": {"type": ["string", "null"], "enum": [*regions, None]},
            "start": {"type": ["string", "null"]},
            "end": {"type": ["string", "null"]},
            "clarification": {"type": ["string", "null"]},
            "reading": {"type": "string"},
        },
        "required": ["kpi_id", "region", "start", "end", "clarification", "reading"],
        "additionalProperties": False,
    }


def _as_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def interpret(
    question: str,
    *,
    kpi_ids: list[str],
    regions: list[str],
    today: date,
    coverage: tuple[date, date] | None = None,
    backend: ChatModel | None = UNSET,
) -> Intent:
    """Read a question into a query, or say why it cannot be read.

    `coverage` is the span the warehouse actually holds. A window outside it is
    not a model error and is not reported as one: it is a real limit of the
    data, and the reader is told which rather than being handed an empty chart.
    """
    question = (question or "").strip()
    if not question:
        return Intent(question, problem="no question was asked")

    chosen = model_for(Task.INTENT) if backend is UNSET else backend
    if chosen is None:
        # Deliberately not a keyword fallback. Every other stage degrades to
        # deterministic code because there is a deterministic way to do the job;
        # here there is not, and a regex pretending to understand a sentence
        # would answer confidently about the wrong metric. Saying the feature is
        # off is the honest degradation.
        return Intent(
            question,
            problem="no model backend is reachable, so a question cannot be read. "
                    "Choose a metric and window directly instead.",
        )

    try:
        completion = chosen.complete(
            system=SYSTEM.format(default_days=DEFAULT_WINDOW_DAYS),
            user=(
                f"TODAY: {today.isoformat()}\n"
                f"METRICS: {', '.join(kpi_ids)}\n"
                f"REGIONS: {', '.join(regions)}\n\n"
                f"QUESTION: {question}"
            ),
            schema=_schema(kpi_ids, regions),
            # Reasoning models spend most of their budget before the object,
            # and a truncated object is indistinguishable from a refusal.
            max_tokens=MAX_TOKENS["intent"],
        )
        payload = _first_json_object(completion.text)
    except Exception as exc:
        return Intent(
            question,
            problem=f"the question could not be read ({type(exc).__name__}: {exc})",
        )

    base = {
        "model": chosen.name,
        # A reading served from disk is a cache hit, not a model call.
        "model_calls": 0 if getattr(completion, "cached", False) else 1,
        "cache_hits": 1 if getattr(completion, "cached", False) else 0,
        "tokens_in": completion.tokens_in,
        "tokens_out": completion.tokens_out,
    }

    kpi_id = payload.get("kpi_id")
    region = payload.get("region")
    reading = str(payload.get("reading") or "")
    clarification = payload.get("clarification") or None

    # The schema should have made these impossible. Checked anyway, because a
    # schema binds a cooperative counterparty and this one is a language model.
    rejected: list[str] = []
    if kpi_id is not None and kpi_id not in kpi_ids:
        rejected.append(f"metric {kpi_id!r} is not in this registry")
        kpi_id = None
    if region is not None and region not in regions:
        rejected.append(f"region {region!r} is not one this reader may see")
        region = None

    if kpi_id is None and not clarification:
        clarification = (
            "Which metric did you mean? This business tracks "
            + ", ".join(kpi_ids) + "."
        )

    start, end = _as_date(payload.get("start")), _as_date(payload.get("end"))
    if start is None or end is None:
        end = today
        start = today - timedelta(days=DEFAULT_WINDOW_DAYS)
    if start > end:
        start, end = end, start
    if (end - start).days > MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS)
        rejected.append(
            f"the window was longer than {MAX_WINDOW_DAYS} days and was trimmed"
        )

    problem = None
    if coverage:
        first, last = coverage
        if end < first or start > last:
            problem = (
                f"that window is outside the data this deployment holds, which "
                f"runs {first.isoformat()} to {last.isoformat()}"
            )
        else:
            start, end = max(start, first), min(end, last)

    return Intent(
        question=question, kpi_id=kpi_id, region=region, start=start, end=end,
        reading=reading, clarification=clarification, problem=problem,
        rejected=tuple(rejected), **base,
    )


__all__ = ["DEFAULT_WINDOW_DAYS", "MAX_WINDOW_DAYS", "Intent", "interpret"]
