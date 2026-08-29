"""An OpenAI-compatible endpoint, for the same open models on someone else's GPU.

A 7B model wants roughly 5GB of memory to run comfortably, which not every
laptop can spare during a live demo. The escape hatch is to run the *same
open-weight models* against a hosted endpoint: Groq, Together, OpenRouter and
Hugging Face all serve Mistral and Qwen on a free tier, and vLLM or LM Studio
serve them on infrastructure you control.

All of those speak one API, so this is one class rather than four. The engine
cannot tell which is behind it, and `WHYCHAIN_LLM_BASE_URL` is the whole switch.

**The licence argument survives the move; the sovereignty argument does not.**
Running Mistral 7B on Groq is still Apache 2.0 with no user ceiling and no
restriction on outputs. It is no longer inference inside your own boundary, and
for a workload carrying client data that is the distinction that matters. This
backend is therefore the documented alternative rather than the default, and
`describe()` names the endpoint on the receipt so a reader can see where the
call went.

A key is expected here and is read from the environment. It is never logged,
never included in an error message, and never written to the run receipt.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from whychain.llm import Completion

# Apache 2.0, and served by every free tier worth using. The hosted providers
# name it slightly differently, so the id is configuration rather than a
# constant baked into the engine.
DEFAULT_MODEL = "mistral-7b-instruct"

TIMEOUT_SECONDS = 90.0


@dataclass
class OpenAICompatibleModel:
    """Any endpoint implementing `/chat/completions`."""

    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    backend: str = "openai-compatible"

    def __post_init__(self) -> None:
        self.name = self.name or os.environ.get("WHYCHAIN_LLM_MODEL", DEFAULT_MODEL)
        self.base_url = (self.base_url or os.environ.get("WHYCHAIN_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = self.api_key or os.environ.get("WHYCHAIN_LLM_API_KEY") or None

    @property
    def available(self) -> bool:
        """A configured endpoint. Reachability is proven by using it.

        Deliberately not a live probe: a health check against a hosted provider
        costs a round trip on every diagnosis to answer a question the next
        call answers anyway, and a failure there falls back to the
        deterministic path exactly as a failure here would.
        """
        return bool(self.base_url)

    def complete(
        self, *, system: str, user: str, schema: dict, max_tokens: int = 4096
    ) -> Completion:
        body = json.dumps(
            {
                "model": self.name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # The OpenAI-compatible spelling of constrained decoding. Some
                # providers honour the schema strictly and others treat it as a
                # strong hint, which is why every caller still parses
                # defensively and the validator runs regardless.
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "extraction", "schema": schema},
                },
                "temperature": 0,
                "max_tokens": max_tokens,
            }
        ).encode()

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # Re-raised without the response body: a provider error can echo
            # request headers, and the key is in them.
            raise RuntimeError(
                f"{self.backend} endpoint returned HTTP {exc.code}"
            ) from None

        choice = (payload.get("choices") or [{}])[0]
        usage = payload.get("usage") or {}
        return Completion(
            text=(choice.get("message") or {}).get("content", ""),
            model=str(self.name),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            backend=self.backend,
        )
