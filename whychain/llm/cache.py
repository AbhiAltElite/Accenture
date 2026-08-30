"""A content-addressed cache in front of any model backend.

The brief names this directly: *"LLM economics, including model choice, token
consumption, latency, caching and cost per insight"*. It is also, measured, the
difference between a model path that can be demonstrated and one that cannot.

The numbers that motivated it, on `mistral:7b-instruct` over Ollama on a laptop:
one diagnosis of the flagship retail case makes ten constrained calls -- an
expansion and an extraction per candidate -- and each generates structured JSON
carrying verbatim quotes. Uncached, that diagnosis took over ten minutes. The
same page composed deterministically takes 1.7 seconds. No amount of explaining
that the model is doing something worthwhile survives a ten-minute page load.

Two properties make caching legitimate here rather than a way of hiding a
problem:

**The call is a pure function of its inputs.** Temperature is fixed, the schema
is fixed, and the prompt is built from the note being read. The same note read
twice should produce the same reading; if it does not, the non-determinism is
itself a defect. So a hit returns what a call would have returned.

**It is keyed on everything that could change the answer.** The model name, the
backend, the system prompt, the user message, the schema and the token ceiling.
Changing any of them is a different question and misses. A cache keyed on less
would serve one industry's reading under another's heading, which is the failure
`T-06` calls a P0 and which the series cache already guards against.

What it deliberately does not do is pretend the work was free. `Completion`
carries a `cached` flag, the run receipt counts hits separately from calls, and
the token figures still report what the reading costs when it is not cached.
A receipt claiming zero tokens for work a model did would be the same class of
dishonesty as an uncalibrated probability.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from whychain.llm import ChatModel, Completion

DEFAULT_DIR = Path(os.environ.get("WHYCHAIN_LLM_CACHE", "data/llm_cache"))


def key_for(
    *, model: str, backend: str, system: str, user: str, schema: dict, max_tokens: int
) -> str:
    """Everything that could change the answer, and nothing that could not."""
    payload = json.dumps(
        {
            "model": model,
            "backend": backend,
            "system": system,
            "user": user,
            "schema": schema,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CachedModel:
    """Any `ChatModel`, with its answers remembered on disk.

    Implements the same protocol as the thing it wraps, so nothing downstream
    knows it is there -- which is the point of there being a protocol.
    """

    inner: ChatModel
    directory: Path = field(default_factory=lambda: DEFAULT_DIR)
    hits: int = 0
    misses: int = 0

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def backend(self) -> str:
        return self.inner.backend

    @property
    def available(self) -> bool:
        return self.inner.available

    def complete(
        self, *, system: str, user: str, schema: dict, max_tokens: int = 4096
    ) -> Completion:
        key = key_for(
            model=self.inner.name, backend=self.inner.backend,
            system=system, user=user, schema=schema, max_tokens=max_tokens,
        )
        path = self.directory / f"{key}.json"

        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.hits += 1
            return Completion(
                text=stored["text"], model=stored["model"],
                tokens_in=stored.get("tokens_in", 0),
                tokens_out=stored.get("tokens_out", 0),
                backend=stored.get("backend", self.inner.backend),
                cached=True,
            )
        except (OSError, ValueError, KeyError):
            # A missing, unreadable or malformed entry is a miss, never an
            # error. The cache is an optimisation and must not be able to fail
            # a diagnosis.
            pass

        completion = self.inner.complete(
            system=system, user=user, schema=schema, max_tokens=max_tokens
        )
        self.misses += 1
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "text": completion.text,
                        "model": completion.model,
                        "tokens_in": completion.tokens_in,
                        "tokens_out": completion.tokens_out,
                        "backend": completion.backend,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
        return completion
