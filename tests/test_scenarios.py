"""Every scenario a presenter can click lands where its label says it does.

The coordinates live in the two pages, not in Python, so they are read from
there: a scenario edited in the page and not here fails here. Three demo
defects reached the finale branch because nothing checked this (B-039: the
"why nobody saw it coming" button opened a metric that cannot be diagnosed),
and the cache warmer's cases are checked here too, since a case that cannot be
answered warms nothing (B-040).
"""

from __future__ import annotations

import importlib.util
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

UI = Path("ui")

# What each scenario promises, in its own words. `status` is the HTTP answer to
# the diagnosis; `verdict` and `gap` are what the page then says.
WORKBENCH_EXPECT = {
    "trap": {"status": 200, "verdict": "explained", "rejected_at_least": 1,
             "cannot_verify_at_least": 1},
    "channel": {"status": 200, "verdict": "explained", "set_aside_at_least": 1},
    "graph": {"status": 422},
    "refusal": {"status": 200, "verdict": "unknown"},
    "contradiction": {"status": 200, "verdict": "contradicted"},
    "hourly": {"status": 422},
    "cfo": {"status": 200, "verdict": "explained"},
    "ops": {"status": 200, "verdict": "explained"},
    "entitled": {"status": 200},
    "blanked": {"status": 403},
    "gap": {"status": 200, "verdict": "explained", "gap": "gap_found"},
    "petroleum": {"status": 200, "verdict": "explained", "rejected_at_least": 1},
}
DECISION_EXPECT = {
    # Two verified, the decoy rejected, the three-week-old SKU unverifiable. It
    # was "three causes" while the SKU was tested as the whole West (B-056).
    "Two causes, and a trap": {"status": 200, "verdict": "explained", "rejected_at_least": 1,
                               "cannot_verify_at_least": 1},
    "Why nobody saw it coming": {"status": 200, "verdict": "explained", "gap": "gap_found"},
    # Explained now: it abstained only because the 19 Aug rollback note was
    # tested as a second, opposite cause (B-057).
    "The same finding, asked about the app": {"status": 200, "verdict": "explained",
                                              "set_aside_at_least": 1},
    "Abstains: no cause survives": {"status": 200, "verdict": "unknown"},
    "Two systems disagree": {"status": 200, "verdict": "contradicted"},
    "Detected, not diagnosed": {"status": 422},
    "Scoped to South": {"status": 200},
    "South reader asks about the West": {"status": 403},
    "Another industry": {"status": 200, "verdict": "explained", "rejected_at_least": 1},
}


def _js_fields(obj: str) -> dict:
    return dict(re.findall(r"(\w+):'([^']*)'", obj))


def workbench_demos() -> dict[str, dict]:
    block = (UI / "index.html").read_text(encoding="utf-8").split("const DEMOS = [", 1)[1].split("];", 1)[0]
    demos = {}
    for chunk in re.split(r"\n\s*\{id:", block)[1:]:
        fields = _js_fields("id:" + chunk.split("},", 1)[0])
        demos[fields["id"]] = fields
    return demos


def decision_scenarios() -> dict[str, dict]:
    block = (UI / "app.html").read_text(encoding="utf-8").split("const SCEN = [", 1)[1].split("];", 1)[0]
    out = {}
    for line in block.strip().splitlines():
        if not line.strip().startswith(("{g:", "{id:")):
            continue
        q = _js_fields(re.search(r"q:\{([^}]*)\}", line).group(1))
        top = _js_fields(re.sub(r"q:\{[^}]*\}", "", line))
        out[top["t"]] = {"q": q, "industry": top.get("industry", "retail")}
    return out


@pytest.fixture(scope="module")
def client():
    if not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse not generated")
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def _window(client, demo: dict) -> tuple[str, str]:
    """The window the workbench derives for a demo's day, the way `windowFor` does:
    flagged days no more than two apart are one episode."""
    days = int(demo.get("range") or 90)
    to = date(2026, 8, 31)
    params = {"kpi": demo["kpi"], "industry": demo.get("industry") or "retail",
              "from": (to - timedelta(days=days)).isoformat(), "to": to.isoformat()}
    for k in ("region", "channel", "entitled"):
        if demo.get(k):
            params[k] = demo[k]
    r = client.get("/api/series", params=params)
    if r.status_code != 200:
        return demo["day"], demo["day"]
    flagged = sorted(a["day"] for a in r.json()["anomalies"])
    assert demo["day"] in flagged, f"{demo['id']}: {demo['day']} is not a flagged day"
    i = flagged.index(demo["day"])
    lo = hi = i
    gap = lambda a, b: (date.fromisoformat(b) - date.fromisoformat(a)).days  # noqa: E731
    while lo > 0 and gap(flagged[lo - 1], flagged[lo]) <= 2:
        lo -= 1
    while hi < len(flagged) - 1 and gap(flagged[hi], flagged[hi + 1]) <= 2:
        hi += 1
    return flagged[lo], flagged[hi]


def _check(client, params: dict, expect: dict, name: str) -> None:
    r = client.get("/api/diagnose", params={**params, "backend": "none"})
    assert r.status_code == expect["status"], f"{name}: {r.status_code} {r.text[:160]}"
    if r.status_code != 200:
        return
    body = r.json()
    if "verdict" in expect:
        assert body["verdict"] == expect["verdict"], f"{name}: verdict {body['verdict']}"
    if "gap" in expect:
        assert body["signal_gap"]["verdict"] == expect["gap"], f"{name}: gap {body['signal_gap']['verdict']}"
    if "set_aside_at_least" in expect:
        assert len(body.get("set_aside") or []) >= expect["set_aside_at_least"], name
    for state in ("rejected", "cannot_verify"):
        if f"{state}_at_least" in expect:
            c = client.get("/api/candidates", params={**params, "persona": "analyst", "backend": "none"})
            assert c.json()["counts"][state] >= expect[f"{state}_at_least"], f"{name}: {state}"


def test_every_workbench_scenario_is_covered():
    assert set(workbench_demos()) == set(WORKBENCH_EXPECT)


def test_every_decision_scenario_is_covered():
    assert set(decision_scenarios()) == set(DECISION_EXPECT)


@pytest.mark.parametrize("demo_id", sorted(WORKBENCH_EXPECT))
def test_workbench_scenario_lands(client, demo_id):
    demo = workbench_demos()[demo_id]
    start, end = _window(client, demo)
    params = {"kpi": demo["kpi"], "start": start, "end": end,
              "industry": demo.get("industry") or "retail",
              "persona": demo.get("persona") or "analyst"}
    for k in ("region", "channel", "entitled"):
        if demo.get(k):
            params[k] = demo[k]
    _check(client, params, WORKBENCH_EXPECT[demo_id], demo_id)


@pytest.mark.parametrize("title", sorted(DECISION_EXPECT))
def test_decision_scenario_lands(client, title):
    s = decision_scenarios()[title]
    _check(client, {**s["q"], "industry": s["industry"], "persona": "analyst"},
           DECISION_EXPECT[title], title)


def test_warm_ai_cases_are_answerable(client):
    """B-040: each case the cache warmer sends must be a real, answerable request."""
    # Loaded by path: it is a script, not a package, and not a dependency.
    spec = importlib.util.spec_from_file_location("warm_ai", "scripts/warm_ai.py")
    warm_ai = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(warm_ai)
    for name, query in warm_ai.CASES:
        r = client.get(f"/api/diagnose?{query}&backend=none")
        assert r.status_code == 200, f"warm_ai case {name!r} returns {r.status_code}"
