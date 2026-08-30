"""Ollama: the local, keyless default.

Chosen because it removes every barrier between a reader and a working system.
No account, no billing, no egress, and a clone of this repository exercises the
full pipeline after one `ollama pull`. For a submission that will be run by
someone who did not write it, that matters more than a few points of model
quality, and the parts of this engine that must be right are not the parts a
model does.

Two details are load-bearing rather than incidental.

**Structured output is requested from the server, not hoped for.** Ollama takes
a JSON schema in `format` and constrains decoding to it, so a small model
returns parseable output as reliably as a large one. Without that, a 7B model
asked politely for JSON produces prose about a third of the time, and the
engine would spend its error budget on parsing instead of on the analysis.

**Temperature is zero and the seed is fixed.** A diagnosis that reads
differently on a second run of identical inputs is not auditable, and
auditability is the whole point. This does not make the model deterministic in
the strict sense, but it removes the sampling variance that would otherwise
make two runs of the same evidence disagree in wording.

No dependency is added for this. Ollama speaks HTTP and JSON, both of which are
in the standard library.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from whychain.llm import Completion

DEFAULT_BASE_URL = "http://localhost:11434"

# Apache 2.0, unrestricted commercial use, no user ceiling, no restriction on
# what the outputs may be used for. `qwen2.5:7b-instruct` is the same licence
# and a drop-in alternative. Llama is deliberately not the default: its
# community licence is not an open-source licence. See the package docstring.
DEFAULT_MODEL = "mistral:7b-instruct"

# Long enough for a cold model load on a laptop, short enough that a demo does
# not appear to have hung.
TIMEOUT_SECONDS = float(__import__("os").environ.get("WHYCHAIN_LLM_TIMEOUT", 45.0))


@dataclass
class OllamaModel:
    """A local Ollama server, reached over plain HTTP."""

    name: str | None = None
    base_url: str | None = None
    backend: str = "ollama"

    def __post_init__(self) -> None:
        self.name = self.name or os.environ.get("WHYCHAIN_LLM_MODEL", DEFAULT_MODEL)
        self.base_url = (
            self.base_url
            or os.environ.get("WHYCHAIN_LLM_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")

    @property
    def available(self) -> bool:
        """Whether the server is up *and* has the model pulled.

        Both halves matter. A running server with no model produces a 404 at
        the moment of use, which in a demo looks like the engine failing rather
        than like a missing `ollama pull`.
        """
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/api/tags", timeout=3
            ) as response:
                tags = json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return False

        pulled = {m.get("name", "") for m in tags.get("models", [])}
        # Ollama reports "mistral:7b-instruct"; a request for "mistral" resolves
        # to a tag, so match on the prefix rather than demanding an exact string.
        stem = str(self.name).split(":")[0]
        return any(p == self.name or p.split(":")[0] == stem for p in pulled)

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
                # Constrained decoding against the schema, so the response
                # parses or the server fails; there is no middle state where a
                # small model returns an apology instead of JSON.
                "format": schema,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "seed": 20260828,
                    "num_predict": max_tokens,
                },
            }
        ).encode()

        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())

        return Completion(
            text=payload.get("message", {}).get("content", ""),
            model=str(self.name),
            # Ollama reports token counts under its own names. Absent on some
            # versions, so default to zero rather than guessing: the receipt
            # reporting nothing is better than the receipt reporting an
            # estimate that reads like a measurement.
            tokens_in=int(payload.get("prompt_eval_count") or 0),
            tokens_out=int(payload.get("eval_count") or 0),
            backend=self.backend,
        )
