"""The finding every rehearsal opens, scored against the causes planted in it.

`make bench` scores 160 generated panels, and `/uat`, `make smoke` and
`test_scenarios.py` check the demo for consistency: the page equals the API and
the promised verdict appears. None of them asked whether the demo's answer was
*right*, which is how a SKU event tested as the whole West reached the flagship
as a verified cause worth four times the SKU's own movement (B-056, B-063, T-35).

This reads `data/ground_truth/`, which the engine must never do
(`test_no_label_leakage`). A test may: it is the examiner, not the examined.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

TRUTH = Path("data/ground_truth/cases.json")
WINDOW = {"kpi": "net_revenue", "region": "West", "start": "2026-08-13",
          "end": "2026-08-15", "industry": "retail", "persona": "analyst", "backend": "none"}


@pytest.fixture(scope="module")
def scored():
    if not TRUTH.exists() or not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse or answer key not generated")
    from fastapi.testclient import TestClient

    from api.main import app
    c = TestClient(app)
    cases = {k["case_id"]: k for k in json.loads(TRUTH.read_text(encoding="utf-8"))}
    return c.get("/api/candidates", params=WINDOW).json(), c.get("/api/diagnose", params=WINDOW).json(), cases


def _planted(cases, case_id):
    return {e["event_id"]: e for e in cases[case_id]["causes"]}


def test_every_verified_cause_was_planted_in_this_window(scored):
    candidates, _, cases = scored
    real = {cid for cid, e in _planted(cases, "demo-01-multi-factor").items() if not e["is_decoy"]}
    verified = {v["candidate_id"] for v in candidates["verified"]}
    assert verified, "the flagship explained nothing"
    assert verified <= real, f"verified causes not planted here: {sorted(verified - real)}"


def test_the_decoy_is_not_verified(scored):
    candidates, _, _ = scored
    assert "promo-monsoon-sale" not in {v["candidate_id"] for v in candidates["verified"]}
    assert "promo-monsoon-sale" in {v["candidate_id"] for v in candidates["rejected"]}


def test_a_three_week_old_sku_is_not_verified(scored):
    """Its own case expects `cannot_verify`: there is no history to test it on."""
    candidates, _, cases = scored
    assert cases["demo-03-sparse-history"]["expected"] == "cannot_verify"
    states = {v["candidate_id"]: state for state in ("verified", "rejected", "cannot_verify")
              for v in candidates[state]}
    assert states.get("pc1099-launch-dip") == "cannot_verify"


def test_no_cause_is_sized_beyond_the_slice_it_touched(scored):
    """A cause cannot account for more rupees than its own slice lost and more.

    The SKU was credited with ₹23,391 a day while the SKU itself fell ₹5,304.
    Here each verified cause's contribution is bounded by its slice's baseline
    revenue, which is the weakest statement that would have caught it.
    """
    _, diagnosis, _ = scored
    base = diagnosis["movement"]["base_revenue"]
    for v in diagnosis["verified"]:
        assert abs(v["contribution"]) < base, v["candidate_id"]
    assert diagnosis["movement"]["overlap"] < 1.5, "causes overlap as if one borrowed another's movement"


def test_a_rollback_is_not_a_cause_and_is_reported_as_done(scored):
    """B-057: the 19 Aug rollback note was a verified cause of the opposite sign."""
    from fastapi.testclient import TestClient

    from api.main import app
    c = TestClient(app)
    wide = {**WINDOW, "channel": "app", "end": "2026-08-20"}
    ids = {v["candidate_id"] for s in ("verified", "rejected", "cannot_verify")
           for v in c.get("/api/candidates", params=wide).json()[s]}
    assert "4.05" not in ids
    _, diagnosis, _ = scored
    card = next(d for d in diagnosis["decisions"] if d["candidate_id"] == "rel-4.05")
    assert card["already_actioned"]["on"] == "2026-08-19"
