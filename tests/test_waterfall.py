"""The variance bridge adds up, names its adjustments, and leaks nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

from whychain.decompose.waterfall import cause_waterfall

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _sum(w):
    return w["start"]["value"] + sum(s["value"] for s in w["steps"])


def test_steps_add_from_start_to_end():
    w = cause_waterfall({"base_revenue": 1000, "current_revenue": 900, "total_change": -100,
                         "per_cause": {"a": -60}}, {"a": "A"})
    assert _sum(w) == pytest.approx(w["end"]["value"], abs=0.05)
    assert [s["kind"] for s in w["steps"]] == ["cause", "rest"]
    assert w["steps"][1]["value"] == -40 and w["steps"][1]["label"].startswith("Not explained")


def test_overlap_is_scaled_evenly_and_the_measured_figure_kept():
    w = cause_waterfall({"base_revenue": 1000, "current_revenue": 900, "total_change": -100,
                         "per_cause": {"a": -90, "b": -60}}, {})
    assert w["scaled_for_overlap"] and w["overlap"] == 1.5
    a, b = w["steps"]
    assert (a["value"], b["value"]) == (-60, -40)
    assert (a["measured"], b["measured"]) == (-90, -60)
    assert _sum(w) == pytest.approx(900, abs=0.05)


def test_a_cause_pulling_the_other_way_is_not_overlap():
    w = cause_waterfall({"base_revenue": 1000, "current_revenue": 900, "total_change": -100,
                         "per_cause": {"a": -120, "b": 30}}, {})
    assert not w["scaled_for_overlap"]
    assert _sum(w) == pytest.approx(900, abs=0.05)


def test_a_withheld_remainder_is_not_called_unexplained():
    w = cause_waterfall({"base_revenue": 1000, "current_revenue": 900, "total_change": -100,
                         "per_cause": {}, "per_cause_withheld": 2}, {})
    assert w["steps"][-1]["label"].startswith("Not shown to you")


def test_a_bridge_that_does_not_add_up_is_not_returned():
    assert cause_waterfall({"base_revenue": 1000, "current_revenue": 950, "total_change": -100,
                            "per_cause": {"a": -60}}, {}) is None


@pytest.fixture(scope="module")
def client():
    if not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse not generated")
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


@pytest.mark.parametrize("persona", ["analyst", "cfo", "ops"])
def test_the_flagship_bridge_adds_up_for_every_reader(client, persona):
    d = client.get("/api/diagnose", params={
        "kpi": "net_revenue", "region": "West", "start": "2026-08-13", "end": "2026-08-15",
        "industry": "retail", "persona": persona, "backend": "none"}).json()
    w = d["waterfall"]
    assert _sum(w) == pytest.approx(d["movement"]["current_revenue"], abs=0.05)
    assert {s["id"] for s in w["steps"] if s["kind"] == "cause"} == {"rel-4.05", "wx-mumbai-aug"}


def test_a_withheld_cause_never_appears_in_the_bridge(client):
    d = client.get("/api/diagnose", params={
        "kpi": "net_revenue", "start": "2026-08-13", "end": "2026-08-16", "industry": "retail",
        "persona": "cfo", "backend": "none", "entitled": "South"}).json()
    text = str(d["waterfall"])
    assert "rel-4.05" not in text and "Release" not in text and "rainfall" not in text
