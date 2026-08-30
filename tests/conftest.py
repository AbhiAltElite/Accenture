"""Test-wide settings.

The suite runs with no model backend, always, and this is not a convenience.

Two reasons, and the second one is the one that bit. A test whose result depends
on what a 7B model happened to generate is not a test, it is a sampling of one;
the whole design puts deterministic code around every model output precisely so
that the engine's behaviour can be asserted, and asserting it against a live
model would give that up. And once `Task.EXPAND` was wired into corroboration,
every test touching the pipeline began making real calls: the suite went from 18
seconds to over ten minutes and its result depended on whether Ollama happened to
be running.

`scripts/verify_ai.py` is where the model path is exercised, deliberately
outside the suite, because it needs a backend and is allowed to fail without one.
"""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_model_backend():
    previous = os.environ.get("WHYCHAIN_LLM_BACKEND")
    os.environ["WHYCHAIN_LLM_BACKEND"] = "none"
    yield
    if previous is None:
        os.environ.pop("WHYCHAIN_LLM_BACKEND", None)
    else:
        os.environ["WHYCHAIN_LLM_BACKEND"] = previous
