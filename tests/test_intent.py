"""Reading a typed question, and each way it is designed to fail.

The question box is the one feature with no deterministic fallback (see
`interpret`), so how it fails is what a reader meets when the model is not
there. Each failure must say what happened in words, and none may return a
query the registry does not hold.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date

from whychain.intent import interpret
from whychain.llm import Completion

KPIS = ["net_revenue", "orders"]
REGIONS = ["North", "South", "West"]
TODAY = date(2026, 8, 31)


class Stub:
    name = "stub"
    backend = "stub"
    available = True

    def __init__(self, answer=None, raises=None):
        self.answer, self.raises = answer, raises

    def complete(self, *, system, user, schema, max_tokens=4096):
        if self.raises:
            raise self.raises
        return Completion(text=json.dumps(self.answer), model="stub")


def ask(backend, q="Why did revenue fall in West in August?"):
    return interpret(q, kpi_ids=KPIS, regions=REGIONS, today=TODAY, backend=backend)


def test_offline_says_so_in_words_and_points_to_what_still_works():
    for down in (urllib.error.URLError("nodename nor servname provided"),
                 TimeoutError("timed out"), ConnectionResetError()):
        got = ask(Stub(raises=down))
        assert not got.runnable
        assert "needs the internet" in got.problem and "Error" not in got.problem, got.problem


def test_a_used_up_allowance_is_not_called_a_fault_in_the_question():
    got = ask(Stub(raises=RuntimeError("openai endpoint returned HTTP 429")))
    assert "allowance is used up" in got.problem


def test_no_model_means_no_guess():
    got = ask(None)
    assert not got.runnable and "no model backend" in got.problem


def test_a_metric_or_region_the_registry_lacks_is_never_run():
    got = ask(Stub({"kpi_id": "ebitda", "region": "Mars", "start": "2026-08-01",
                    "end": "2026-08-31", "reading": "x", "clarification": None}))
    assert got.kpi_id is None and got.region is None
    assert not got.runnable
    assert any("ebitda" in r for r in got.rejected) and any("Mars" in r for r in got.rejected)


def test_a_clean_reading_runs():
    got = ask(Stub({"kpi_id": "net_revenue", "region": "West", "start": "2026-08-01",
                    "end": "2026-08-31", "reading": "Net revenue, West, August",
                    "clarification": None}))
    assert got.runnable and got.kpi_id == "net_revenue" and got.region == "West"
