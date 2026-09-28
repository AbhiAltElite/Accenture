"""A zip built with --no-key carries the model settings and no credential."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("package", Path(__file__).parent.parent / "app" / "package.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

ENV = """# model
WHYCHAIN_LLM_BACKEND=openai
WHYCHAIN_LLM_BASE_URL=https://openrouter.ai/api/v1
WHYCHAIN_LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
WHYCHAIN_LLM_API_KEY=sk-or-v1-secretsecret
export OPENROUTER_API_KEY = sk-or-v1-other
WHYCHAIN_PROXY_SECRET=hunter2
WHYCHAIN_TEAMS_WEBHOOK_TOKEN=abc
"""


def test_no_credential_survives():
    out = package.settings_without_secrets(ENV)
    for secret in ("sk-or-v1", "hunter2", "abc"):
        assert secret not in out


def test_the_model_settings_stay_so_the_cache_still_matches():
    out = package.settings_without_secrets(ENV)
    for line in ("WHYCHAIN_LLM_BACKEND=openai", "WHYCHAIN_LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free",
                 "WHYCHAIN_LLM_BASE_URL=https://openrouter.ai/api/v1", "# model"):
        assert line in out
