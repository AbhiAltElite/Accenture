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


@dataclass(frozen=True)
class Completion:
    """What a model returned, and what it cost to get it."""

    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    backend: str = "unknown"


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


class Task(StrEnum):
    """The two jobs a model does here, which are not equally hard.

    Naming them lets each be routed to the cheapest model that can do it, which
    is how Accenture's Spotlight platform describes its own architecture:
    dynamic selection between task-specific models and foundation models
    according to task complexity and latency. The principle is sound and cheap
    to adopt, and it is the opposite of sending every request to the largest
    model available because that is the one in the config.
    """

    EXTRACT = "extract"
    NARRATE = "narrate"


# What each task actually demands, and therefore what it should be given. These
# are statements about the work, not about any vendor's tiers, so they survive a
# change of backend.
TASK_PROFILE: dict[Task, dict] = {
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
    """
    forced = (backend or os.environ.get("WHYCHAIN_LLM_BACKEND", "")).strip().lower()
    if forced == "none":
        return None

    if forced == "openai" or (not forced and os.environ.get("WHYCHAIN_LLM_BASE_URL")):
        from whychain.llm.hosted import OpenAICompatibleModel

        hosted = OpenAICompatibleModel(name=model)
        if hosted.available:
            return hosted
        if forced:
            return None

    if forced in ("", "ollama"):
        from whychain.llm.local import OllamaModel

        local = OllamaModel(name=model)
        if local.available:
            return local

    return None


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


def catalogue() -> list[dict]:
    """Every backend, whether it is reachable, and what it implies.

    Rendered by the console so the choice of model is visible and switchable at
    run time rather than buried in an environment variable. Model choice is a
    governance decision, and a governance decision nobody can see is not one.
    """
    from whychain.llm.hosted import DEFAULT_MODEL as HOSTED_MODEL
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
        {
            "id": "openai",
            "label": "Hosted, same open weights",
            "model": HOSTED_MODEL,
            "licence": "Apache 2.0",
            "available": bool(os.environ.get("WHYCHAIN_LLM_BASE_URL")),
            "sovereignty": "inference leaves the boundary",
            "note": "Groq, Together, OpenRouter, vLLM or LM Studio.",
        },
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
    "TASK_PROFILE",
    "ChatModel",
    "Completion",
    "Task",
    "catalogue",
    "default_model",
    "describe",
    "model_for",
    "routing",
]
