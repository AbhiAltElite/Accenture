"""The model layer, kept swappable because the vendor is not the point.

Two stages use a language model: reading unstructured support tickets, and
writing the narrative. Both are constrained by deterministic code that runs
afterwards, and that constraint is what the design rests on. Which model
produced the text is, deliberately, an implementation detail, so the engine
depends on one small protocol and has never heard of a vendor.

**Why the default is an Apache-2.0 model you host yourself.**

Model choice here is a governance decision before it is a quality one, and two
published Accenture positions point the same way: Responsible AI, which asks for
auditable controls and documented governance over what the model may do, and
Sovereign AI, which asks where inference happens and which providers a workload
depends on. A locally hosted open-weight model answers both directly. No client
data leaves the boundary, the call is reproducible, and there is no third-party
dependency to audit.

Licence cleanliness is the second half of it, and it separates models that get
described interchangeably:

- **Mistral 7B Instruct** and **Qwen2.5** below 35B are **Apache 2.0**:
  unrestricted commercial use, no user ceiling, no restriction on what the
  outputs may be used for.
- **Llama is not open source**, whatever it is usually called. Its community
  licence caps free commercial use at 700 million monthly active users, forbids
  using its outputs to train a competing model, and fails the Open Source
  Definition on field-of-use grounds. Defensible for many projects; a poor
  default for one that will be read as a template for client delivery.

So the default is Mistral 7B Instruct over Ollama, Apache 2.0 both ways, and
Qwen2.5 is a drop-in alternative under the same licence. Neither needs an
account.

**A hosted endpoint is configuration, not a rewrite.** `OpenAICompatibleModel`
speaks the API that Groq, Together, OpenRouter, vLLM and LM Studio all
implement, so the same open-weight models can be run against a free hosted tier
when a laptop cannot spare the memory. The engine cannot tell the difference.

**Absence is a supported state.** With no backend reachable, both stages fall
back to deterministic code, the receipt reports zero model calls, and the
console names the writer. An engine that cannot answer without a network call
is not one you would put in front of a finance team.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class _Unset:
    """Distinguishes "no backend was specified" from "explicitly no backend".

    Both were written as `None`, and a component that re-resolved a `None`
    backend from the environment therefore could not tell a caller saying
    "decide for yourself" from one saying "run without a model". The second is
    what `backend=none` means, and silently overriding it made a deterministic
    request call the model anyway: measured, a diagnosis that takes 1.1 seconds
    took 78. An explicit choice must beat a default; that is the whole point of
    it being explicit.
    """

    def __repr__(self) -> str:                        # pragma: no cover - debug aid
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET = _Unset()


class ModelError(RuntimeError):
    """The backend did not return a usable answer.

    A subclass of `RuntimeError` so every existing degradation path catches it
    unchanged, and named so the receipt says which kind of failure it was.
    """


def require_content(text: str | None, *, backend: str, model: str) -> str:
    """A completion with no content is a failure, not an answer.

    Both backends can return HTTP 200 carrying nothing: a free tier shedding
    load, a provider putting an error object in a 200 body, a reasoning model
    truncated before it reaches the object it was asked for. Returning that as
    an empty `Completion` makes it indistinguishable from a model that read the
    brief and had nothing to say -- and the two must not look alike, because the
    first is a fault to report and the second is an answer to print.

    This is the fault that produced the worst possible output here: an empty
    narrative on the page, and a receipt calling it clean, model-written and not
    fallen back. Raising instead routes it into the fallback every caller
    already has, and the reason lands on the receipt.
    """
    if text and text.strip():
        return text
    raise ModelError(
        f"{backend} \u00b7 {model} returned an empty completion"
    )


@dataclass(frozen=True)
class Completion:
    """What a model returned, and what it cost to get it."""

    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    backend: str = "unknown"
    # Whether this came back from the cache rather than the model. Reported
    # rather than hidden: the token figures below still say what the reading
    # costs when it is not cached, and a receipt claiming free work would be the
    # same dishonesty as an uncalibrated probability.
    cached: bool = False


@runtime_checkable
class ChatModel(Protocol):
    """The whole surface the engine is allowed to depend on."""

    name: str
    backend: str

    @property
    def available(self) -> bool:
        """Whether this backend can actually be called right now."""
        ...

    def complete(
        self, *, system: str, user: str, schema: dict, max_tokens: int = 4096
    ) -> Completion: ...


# Output ceilings per task, in tokens.
#
# These were originally sized for a model that emits the object and nothing
# else, which several of the open-weight models on a free tier are not: they are
# reasoning models and spend most of a budget working before they answer. A
# truncated object is indistinguishable from a refusal -- the parse fails and
# the engine reports "the model returned nothing usable" -- so a ceiling set too
# low reads as a broken feature rather than as a budget.
#
# They are ceilings, not reservations: nothing is charged for headroom, and the
# receipt reports the tokens actually spent. Sized as roughly three times the
# longest well-formed answer observed for each task.
MAX_TOKENS: dict[str, int] = {
    # A dozen words out, but "after the working" is the whole point and 512 did
    # not pay for it. A reasoning model spends its budget before the object, so
    # against the configured default this stage truncated every time, fell back
    # to the deterministic query on every call, and query expansion -- the one
    # thing here a keyword table genuinely cannot do -- was dead in a
    # configuration that reported itself as working. The ceiling that fixed
    # `intent` for exactly this reason is the ceiling this needs.
    "expand": 4096,
    "intent": 4096,     # one small object, after the working
    "extract": 12000,   # up to 25 documents, each with a verbatim quote
    "narrate": 8000,    # a handful of sentences, each with citations
    "signalgap": 6000,
}


class Task(StrEnum):
    """The two jobs a model does here, which are not equally hard.

    Naming them lets each be routed to the cheapest model that can do it, which
    is how Accenture's Spotlight platform describes its own architecture:
    dynamic selection between task-specific models and foundation models
    according to task complexity and latency. The principle is sound and cheap
    to adopt, and it is the opposite of sending every request to the largest
    model available because that is the one in the config.
    """

    EXPAND = "expand"
    INTENT = "intent"
    EXTRACT = "extract"
    NARRATE = "narrate"


# What each task actually demands, and therefore what it should be given. These
# are statements about the work, not about any vendor's tiers, so they survive a
# change of backend.
TASK_PROFILE: dict[Task, dict] = {
    Task.INTENT: {
        "needs": "one sentence into a structured query over a closed vocabulary",
        "tier": "small",
        "env": "WHYCHAIN_INTENT_MODEL",
        "why_small": (
            "the answer space is an enum of this deployment's own metrics and "
            "regions plus two dates, so the schema makes an invalid query "
            "unrepresentable rather than merely unlikely. The registry then "
            "checks what comes back, and an unclear question is answered with a "
            "clarification rather than a guess"
        ),
    },
    Task.EXPAND: {
        "needs": "vocabulary translation between two registers, a dozen words out",
        "tier": "small",
        "env": "WHYCHAIN_EXPANSION_MODEL",
        "why_small": (
            "the output is a bag of words that a deterministic filter strips to "
            "language before retrieval ever sees it, and retrieval is unchanged "
            "underneath. A poor expansion retrieves less, never wrong: it cannot "
            "reach a number, and the deterministic query remains in place beneath "
            "whatever it proposes"
        ),
    },
    Task.EXTRACT: {
        "needs": "classification against a closed vocabulary over short passages",
        "tier": "small",
        "env": "WHYCHAIN_EXTRACTION_MODEL",
        "why_small": (
            "the output space is seven issue types and a verbatim quote, both "
            "constrained by schema and both checked afterwards against the "
            "source, so a larger model buys accuracy the validator already "
            "guarantees"
        ),
    },
    Task.NARRATE: {
        "needs": "constrained writing over a table of facts, with citations",
        "tier": "standard",
        "env": "WHYCHAIN_NARRATIVE_MODEL",
        "why": (
            "the harder of the two: it has to select what matters, order it, "
            "and copy every figure exactly. Sentences that fail are dropped, so "
            "a weaker model costs coverage rather than correctness"
        ),
    },
}


def model_for(task: Task, backend: str | None = None) -> ChatModel | None:
    """The model this task should use, routed by what the task needs.

    A per-task environment variable overrides the default, so a deployment can
    put extraction on a small local model and the narrative on something larger
    without either stage knowing it happened.
    """
    override = os.environ.get(str(TASK_PROFILE[task]["env"]), "").strip()
    return default_model(override or None, backend)


def routing() -> list[dict]:
    """How each task is currently routed. Rendered on the receipt."""
    out = []
    for task, profile in TASK_PROFILE.items():
        chosen = model_for(task)
        out.append(
            {
                "task": task.value,
                "needs": profile["needs"],
                "tier": profile["tier"],
                "model": chosen.name if chosen else "deterministic fallback",
                "backend": chosen.backend if chosen else "none",
            }
        )
    return out


def default_model(
    model: str | None = None, backend: str | None = None
) -> ChatModel | None:
    """The backend to use, decided once and explained.

    `WHYCHAIN_LLM_BACKEND` forces one (`ollama`, `openai`, `none`). Otherwise an
    explicitly configured hosted endpoint wins, because setting one is a
    deliberate act, and the local runtime is tried after it. `None` means
    neither is reachable, which callers handle by running their deterministic
    path rather than by failing.

    Forcing `none` is what a benchmark run wants: measuring the engine against a
    model that changes underneath it is measuring two things at once.

    Whatever is returned is wrapped in the disk cache, because every call here is
    a pure function of its inputs and an uncached path takes minutes rather than
    seconds. `WHYCHAIN_LLM_CACHE=off` disables it, which is what you want when
    measuring what the model actually costs rather than what a warm demo costs.
    """
    forced = (backend or os.environ.get("WHYCHAIN_LLM_BACKEND", "")).strip().lower()
    if forced == "none":
        return None

    if forced == "openai" or (not forced and os.environ.get("WHYCHAIN_LLM_BASE_URL")):
        from whychain.llm.hosted import OpenAICompatibleModel

        hosted = OpenAICompatibleModel(name=model)
        if hosted.available:
            return _cached(hosted)
        if forced:
            return None

    if forced in ("", "ollama"):
        from whychain.llm.local import OllamaModel

        local = OllamaModel(name=model)
        if local.available:
            return _cached(local)

    return None


def _cached(backend: ChatModel) -> ChatModel:
    """Wrap a reachable backend in the disk cache, unless it is switched off."""
    if os.environ.get("WHYCHAIN_LLM_CACHE", "").strip().lower() in ("off", "0", "none"):
        return backend
    from whychain.llm.cache import CachedModel

    return CachedModel(inner=backend)


# Where an enterprise platform would attach. Named rather than implemented,
# because a backend nobody has run is a claim rather than a capability, and this
# project's whole argument is against those.
#
# Accenture's AI Refinery is the closest fit, and the fit is structural rather
# than a matter of branding. Its four published components line up with what is
# already here: **Models**, described as switching between foundation models on
# performance factors, is the routing in `model_for` below; **Governance**,
# described as oversight of cost, accuracy and security, is what the run receipt
# reports per diagnosis; **Knowledge** is the KPI semantic contract; **Agents**
# are the pipeline stages. GenWizard is the other candidate, aimed at technology
# delivery rather than at analysis.
#
# The division of labour is worth stating, because it is the reason this is a
# complement and not a duplicate. A platform promises governance at the level of
# the estate. This engine produces the per-insight evidence that makes such a
# promise checkable: what one diagnosis cost, how calibrated its confidence was,
# which share of it a model touched, and what it refused to answer. A platform
# can report that governance exists; only the workload can show it held.
#
# Neither backend is implemented and neither is claimed to be. Adding one is a
# file implementing three methods against the protocol above, which is the
# entire point of there being a protocol.
ENTERPRISE_BACKENDS = ("genwizard", "ai-refinery")


# Open-weight model families, by the prefix their names carry. Membership here
# is a licence claim, so it is a short list of families actually checked rather
# than a guess from the string.
_OPEN_WEIGHTS = {
    "mistral": "Apache 2.0",
    "mixtral": "Apache 2.0",
    "qwen": "Apache 2.0",
    "gemma": "Gemma Terms of Use",
    "phi": "MIT",
    "llama": "Meta Community Licence (not open source)",
    "nemotron": "NVIDIA Open Model Licence",
    "nvidia": "NVIDIA Open Model Licence",
    "glm": "MIT",
}

# Hosts whose identity can be stated rather than inferred. The point is not
# completeness: it is that a host we recognise is named, and one we do not is
# described as unknown instead of being described as something it might not be.
_KNOWN_HOSTS = (
    ("generativelanguage.googleapis.com", "Google Gemini", False),
    ("api.groq.com", "Groq", True),
    ("api.together.xyz", "Together", True),
    ("openrouter.ai", "OpenRouter", None),
    ("api.openai.com", "OpenAI", False),
    ("localhost", "a local OpenAI-compatible server", True),
    ("127.0.0.1", "a local OpenAI-compatible server", True),
)


def _hosted_identity() -> dict:
    """What the configured hosted endpoint actually is, rather than what it was.

    This row used to read "Hosted, same open weights · mistral-7b-instruct ·
    Apache 2.0" whatever `WHYCHAIN_LLM_BASE_URL` pointed at. Pointed at Gemini it
    stated, in the console, that the run was on Apache-2.0 open weights while it
    was running a proprietary hosted model. The console exists to make the model
    choice visible *because* it is a governance decision; a governance claim that
    is wrong is worse than none, and `make audit` checks that the copy is factual.

    So the licence is claimed only where the model name is a family we actually
    check, and the host is named only where we recognise it. Everything else is
    reported as unknown, which is a true statement about a backend the operator
    configured and we did not.
    """
    from whychain.llm.hosted import DEFAULT_MODEL as HOSTED_MODEL

    base_url = os.environ.get("WHYCHAIN_LLM_BASE_URL", "").strip()
    model = os.environ.get("WHYCHAIN_LLM_MODEL", "").strip() or HOSTED_MODEL

    provider, open_weights = None, None
    for fragment, name, is_open in _KNOWN_HOSTS:
        if fragment in base_url:
            provider, open_weights = name, is_open
            break

    # OpenRouter and friends namespace ids as "vendor/model[:free]", so the
    # family name sits after the slash and a prefix match on the whole id misses
    # it -- "meta-llama/llama-3.2-3b-instruct:free" would have been reported as
    # unknown while being a model whose licence we do check.
    stem = model.lower().rsplit("/", 1)[-1].removesuffix(":free")
    vendor = model.lower().split("/", 1)[0]
    licence = next(
        (lic for prefix, lic in _OPEN_WEIGHTS.items()
         if stem.startswith(prefix) or vendor.startswith(prefix)),
        None,
    )
    if licence is None:
        licence = "open weights" if open_weights else "as published by the provider"

    if provider and open_weights is True:
        label = f"Hosted, open weights ({provider})"
    elif provider:
        label = f"Hosted ({provider})"
    else:
        label = "Hosted, OpenAI-compatible"

    from whychain.llm.hosted import _free_only_refusal

    refusal = _free_only_refusal(model)
    if base_url:
        note = f"Configured endpoint: {base_url}."
        if refusal:
            note = f"Refusing to call it: {refusal}"
        elif model.endswith(":free"):
            note += " Free tier, enforced: a paid model id would be refused."
    else:
        note = "Groq, Together, OpenRouter, vLLM, LM Studio or Gemini."

    return {
        "id": "openai",
        "label": label,
        "model": model,
        "licence": licence,
        "available": bool(base_url) and not refusal,
        "sovereignty": "inference leaves the boundary",
        "note": note,
    }


def catalogue() -> list[dict]:
    """Every backend, whether it is reachable, and what it implies.

    Rendered by the console so the choice of model is visible and switchable at
    run time rather than buried in an environment variable. Model choice is a
    governance decision, and a governance decision nobody can see is not one.
    """
    from whychain.llm.local import DEFAULT_MODEL as LOCAL_MODEL
    from whychain.llm.local import OllamaModel

    local = OllamaModel()
    return [
        {
            "id": "ollama",
            "label": "Local, open weights",
            "model": LOCAL_MODEL,
            "licence": "Apache 2.0",
            "available": local.available,
            "sovereignty": "inference inside the boundary; no data leaves",
            "note": "Default. No account, no key, no egress.",
        },
        _hosted_identity(),
        {
            "id": "none",
            "label": "No model",
            "model": "deterministic",
            "licence": "n/a",
            "available": True,
            "sovereignty": "nothing leaves; nothing is read",
            "note": "Rule-based extraction and the template writer. The "
                    "benchmark is produced in this mode.",
        },
        {
            "id": "enterprise",
            "label": "Enterprise platform",
            "model": " / ".join(ENTERPRISE_BACKENDS),
            "licence": "per platform",
            "available": False,
            "sovereignty": "per platform",
            "note": "Not implemented. A platform backend is three methods "
                    "against the protocol; nothing in the engine changes.",
        },
    ]


def describe(backend: ChatModel | None) -> str:
    """A line for the receipt. Says what ran, or that nothing did and why."""
    if backend is None:
        return (
            "no model backend reachable; deterministic path used. Run "
            "`ollama serve` with a pulled model, or point "
            "WHYCHAIN_LLM_BASE_URL at an OpenAI-compatible endpoint"
        )
    return f"{backend.backend} · {backend.name}"


__all__ = [
    "ENTERPRISE_BACKENDS",
    "MAX_TOKENS",
    "TASK_PROFILE",
    "UNSET",
    "ChatModel",
    "Completion",
    "ModelError",
    "Task",
    "catalogue",
    "default_model",
    "describe",
    "model_for",
    "require_content",
    "routing",
]
