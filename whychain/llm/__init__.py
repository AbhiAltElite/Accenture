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


def default_model(model: str | None = None) -> ChatModel | None:
    """The backend to use, decided once and explained.

    `WHYCHAIN_LLM_BACKEND` forces one (`ollama`, `openai`, `none`). Otherwise an
    explicitly configured hosted endpoint wins, because setting one is a
    deliberate act, and the local runtime is tried after it. `None` means
    neither is reachable, which callers handle by running their deterministic
    path rather than by failing.

    Forcing `none` is what a benchmark run wants: measuring the engine against a
    model that changes underneath it is measuring two things at once.
    """
    forced = os.environ.get("WHYCHAIN_LLM_BACKEND", "").strip().lower()
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


def describe(backend: ChatModel | None) -> str:
    """A line for the receipt. Says what ran, or that nothing did and why."""
    if backend is None:
        return (
            "no model backend reachable; deterministic path used. Run "
            "`ollama serve` with a pulled model, or point "
            "WHYCHAIN_LLM_BASE_URL at an OpenAI-compatible endpoint"
        )
    return f"{backend.backend} · {backend.name}"


__all__ = ["ChatModel", "Completion", "default_model", "describe"]
