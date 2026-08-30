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
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from whychain.llm import Completion

# Apache 2.0, and served by every free tier worth using. The hosted providers
# name it slightly differently, so the id is configuration rather than a
# constant baked into the engine.
DEFAULT_MODEL = "mistral-7b-instruct"

TIMEOUT_SECONDS = float(os.environ.get("WHYCHAIN_LLM_TIMEOUT", 45.0))
# Long enough for a capacity spike to clear, short enough that the deterministic
# path is not held up twice over.
RETRY_PAUSE_SECONDS = 2.0
# Two retries after the first attempt: enough to clear a per-minute limit on a
# free tier, bounded so the deterministic path is never held up for long.
RETRY_ATTEMPTS = 3
MAX_RETRY_PAUSE_SECONDS = 20.0
# Transient by definition: rate limiting, and the provider reporting a demand
# spike. Everything else is a real error and retrying it only doubles the wait.
RETRYABLE = frozenset({429, 503})


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """The provider's own instruction, when it gives one."""
    try:
        return float(exc.headers.get("Retry-After", ""))
    except (TypeError, ValueError, AttributeError):
        return None


# A key with credit on it will happily bill for a paid model if the id is
# mistyped, and the mistake is invisible until an invoice arrives. This is a
# student submission running on a free tier, so the cost control is a refusal
# rather than a warning: with `WHYCHAIN_LLM_FREE_ONLY` set, a model id that does
# not carry the provider's free marker is not called at all.
#
# OpenRouter marks free variants with a `:free` suffix, which is exactly the
# kind of thing an engine can check. Where a provider has no such marker the
# guard cannot help and says so rather than pretending to.
FREE_SUFFIXES = (":free",)


def _free_only_enabled() -> bool:
    return os.environ.get("WHYCHAIN_LLM_FREE_ONLY", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _free_only_refusal(model: str) -> str:
    """Empty when the model may be called; otherwise why it may not be."""
    if not _free_only_enabled():
        return ""
    if any(model.endswith(suffix) for suffix in FREE_SUFFIXES):
        return ""
    return (
        f"WHYCHAIN_LLM_FREE_ONLY is set and {model!r} carries no free marker "
        f"({', '.join(FREE_SUFFIXES)}), so it was not called. Either choose a "
        f"free variant or unset the guard deliberately."
    )


def _ssl_context() -> ssl.SSLContext | None:
    """Verified TLS, using a trust store that exists on this machine.

    A python.org build on macOS ships without a usable root store: it does not
    read the system keychain, and every hosted call fails with
    `CERTIFICATE_VERIFY_FAILED` until someone runs `Install Certificates.command`
    by hand. That is a trap for anyone cloning this repository, and it fails at
    the worst moment -- the first time a demo points at a hosted backend.

    `certifi` ships the Mozilla root bundle and is already present as a
    transitive dependency, so it is used when importable and the default context
    stands in when it is not. Verification is never disabled: an unverified TLS
    connection carrying an API key is not a workaround, and the honest failure
    is better than a silent downgrade.
    """
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


@dataclass
class OpenAICompatibleModel:
    """Any endpoint implementing `/chat/completions`."""

    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    backend: str = "openai-compatible"
    # Why this backend is refusing to be used, if it is. Empty when usable.
    refusal: str = ""

    def __post_init__(self) -> None:
        self.name = self.name or os.environ.get("WHYCHAIN_LLM_MODEL", DEFAULT_MODEL)
        self.base_url = (self.base_url or os.environ.get("WHYCHAIN_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = self.api_key or os.environ.get("WHYCHAIN_LLM_API_KEY") or None
        self.refusal = _free_only_refusal(str(self.name))

    @property
    def available(self) -> bool:
        """A configured endpoint. Reachability is proven by using it.

        Deliberately not a live probe: a health check against a hosted provider
        costs a round trip on every diagnosis to answer a question the next
        call answers anyway, and a failure there falls back to the
        deterministic path exactly as a failure here would.

        A model the free-only guard refuses is reported unavailable rather than
        called and refused later: unavailable is a state the whole engine already
        handles, and it degrades to the deterministic path with the reason on the
        receipt instead of raising in the middle of a diagnosis.
        """
        return bool(self.base_url) and not self.refusal

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
        # Hosted capacity errors are transient by definition -- 429 is rate
        # limiting and 503 is the provider saying demand is spiking -- and both
        # were observed against a live endpoint while a demo was being prepared.
        # One retry after a short pause turns most of them into a slow answer
        # rather than a fallback to the template. Anything else is a real error
        # and is not retried: a 401 will not fix itself, and retrying a 400
        # schema rejection just doubles the wait before the deterministic path
        # takes over.
        payload = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS, context=_ssl_context()
                ) as response:
                    payload = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                last = attempt == RETRY_ATTEMPTS - 1
                if exc.code in RETRYABLE and not last:
                    # A free tier is measured in requests per minute and a
                    # diagnosis makes several in a row, so 429 is the ordinary
                    # case rather than an exceptional one. The provider says how
                    # long to wait when it knows; otherwise back off
                    # geometrically rather than hammering the same second.
                    delay = _retry_after(exc) or RETRY_PAUSE_SECONDS * (2**attempt)
                    time.sleep(min(delay, MAX_RETRY_PAUSE_SECONDS))
                    continue
                # Re-raised without the response body: a provider error can echo
                # request headers, and the key is in them. The status code is
                # kept because it is the whole diagnosis: 401 is a bad key, 400
                # a rejected schema, 429 a rate limit, and the receipt is where
                # a reader looks when the narrative is not the one they expected.
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
