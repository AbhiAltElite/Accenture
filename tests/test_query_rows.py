"""The query and rows view: the statement shown is the one that produced the rows.

The view makes two promises, and it is aggregates only: at warehouse scale the
aggregation runs where the data lives and only a figure's rows come back. The rows are the engine's own, drawn through the
same path as the chart. And the statement beside them, run in the warehouse,
returns exactly those rows. The second is checked by the server on every
request; these tests hold it to that across every contract in every industry,
and hold the governance around it: entitlement in the SQL, values always
bound, exports on the audit trail.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from whychain.audit import AuditLog

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

WINDOW = {"start": "2026-08-13", "end": "2026-08-15"}
WEST = {"kpi": "net_revenue", "region": "West", "industry": "retail", **WINDOW}


@pytest.fixture
def client(tmp_path, monkeypatch):
    if not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse not generated")
    from fastapi.testclient import TestClient

    import api.main as m
    monkeypatch.setattr(m, "_audit", AuditLog(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("WHYCHAIN_IDENTITY", raising=False)
    return TestClient(m.app), m


def _every_contract():
    import api.main as m
    out = []
    for industry in ("retail", "petroleum", "power"):
        vertical = m._vertical(industry)
        if not Path(vertical.warehouse).exists():
            continue
        out += [(industry, kpi) for kpi in sorted(m.registry(vertical)._contracts)]
    return out


@pytest.mark.invariant
@pytest.mark.parametrize(("industry", "kpi"), _every_contract())
def test_the_shown_query_returns_the_engines_rows(client, industry, kpi):
    # All regions, so a transform that only touches one region (East's clock)
    # would show up as a mismatch if the statement left it out.
    c, _ = client
    body = c.get("/api/rows", params={"kpi": kpi, "industry": industry, **WINDOW}).json()
    assert body["rows"], kpi
    assert body["reproduced"]["match"] is True, body["reproduced"]
    assert body["reproduced"]["rows"] == len(body["rows"])


def test_the_rows_are_the_charts_rows(client):
    c, _ = client
    body = c.get("/api/rows", params=WEST).json()
    series = c.get("/api/series", params={"kpi": "net_revenue", "region": "West",
                                          "from": "2026-07-30", "to": "2026-08-15"}).json()
    observed = dict(zip(series["days"], series["observed"], strict=True))
    for row in body["rows"]:
        assert row["value"] == pytest.approx(observed[row["d"]], abs=0.01), row["d"]
    assert [r["d"] for r in body["rows"] if r["in_window"]] == ["2026-08-13", "2026-08-14", "2026-08-15"]


class TestEntitlement:
    def test_a_region_outside_entitlement_is_refused(self, client):
        c, _ = client
        r = c.get("/api/rows", params={**WEST, "entitled": "South"})
        assert r.status_code == 403

    def test_all_regions_means_your_regions_and_the_sql_says_so(self, client):
        c, _ = client
        q = {k: v for k, v in WEST.items() if k != "region"}
        body = c.get("/api/rows", params={**q, "entitled": "South"}).json()
        assert "region IN ('South')" in body["sql"]
        south = c.get("/api/rows", params={**WEST, "region": "South"}).json()
        assert [r["value"] for r in body["rows"]] == pytest.approx([r["value"] for r in south["rows"]])

    def test_empty_entitlement_grants_nothing(self, client):
        c, _ = client
        q = {k: v for k, v in WEST.items() if k != "region"}
        assert c.get("/api/rows", params={**q, "entitled": ""}).status_code == 403


def test_a_request_value_is_bound_never_written_into_the_statement(client):
    import api.main as m
    from whychain.ingest import rows as query_rows
    contract = m._contract("net_revenue", m._vertical("retail"))
    hostile = "West' OR 1=1 --"
    rep = query_rows.reproduce(contract, "d", lo=date(2026, 8, 1), hi=date(2026, 8, 15), scope=None,
                               region=hostile, slice_={})
    assert hostile not in rep.sql and hostile in rep.params
    assert "'West'' OR 1=1 --'" in rep.literal()
    c, _ = client
    r = c.get("/api/rows", params={**WEST, "region": hostile})
    assert r.status_code == 404  # no such region: no rows, and nothing else ran


class TestExport:
    def test_an_export_is_on_the_audit_trail(self, client):
        c, m = client
        r = c.post("/api/rows/export", json=WEST, headers={"X-WhyChain-User": "fpa.analyst"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        lines = r.text.strip().splitlines()
        assert lines[0] == "period,value,in_window" and len(lines) == 18
        entry = m._audit.entries()[-1]
        assert entry["event"] == "rows_exported"
        assert entry["actor"]["role"] == "fpa_analyst"
        assert entry["payload"]["rows"] == 17 and entry["payload"]["reproduced"] is True
        assert len(entry["payload"]["sql_sha256"]) == 64
        assert m._audit.verify()["intact"]

    def test_an_export_outside_entitlement_is_refused_and_not_recorded(self, client):
        c, m = client
        r = c.post("/api/rows/export", json={**WEST, "entitled": "South"},
                   headers={"X-WhyChain-User": "fpa.analyst"})
        assert r.status_code == 403
        assert m._audit.entries() == []


class TestCatalog:
    def test_every_governed_metric_is_described_from_its_contract(self, client):
        c, m = client
        body = c.get("/api/catalog").json()
        ids = [x["kpi_id"] for x in body["metrics"]]
        assert ids == sorted(m.registry(m._vertical("retail"))._contracts)
        nr = next(x for x in body["metrics"] if x["kpi_id"] == "net_revenue")
        assert nr["owner_role"] == "finance_director" and nr["favourable"] == "up"
        assert [s["name"] for s in nr["lineage"]] == ["dedupe_order_id", "tz_normalise", "net_returns"]
        assert "customer_email" in nr["column_masks"] and nr["row_filter"].startswith("region IN")
        assert all({"source", "sla_hours", "lag_hours", "met"} <= set(f) for f in nr["freshness"])


class TestQueueFilters:
    def test_the_default_queue_is_falls_only(self, client):
        c, _ = client
        body = c.get("/api/triage", params={"days": 365}).json()
        assert body["findings"] and {f["direction"] for f in body["findings"]} == {"fall"}
        assert all(f["delta"] < 0 for f in body["findings"])

    def test_rises_are_a_choice_and_their_worst_day_is_the_highest(self, client):
        c, _ = client
        body = c.get("/api/triage", params={"days": 365, "direction": "spike"}).json()
        assert body["findings"] and all(f["direction"] == "rise" and f["delta"] > 0 for f in body["findings"])
        both = c.get("/api/triage", params={"days": 365, "direction": "both"}).json()
        assert {f["direction"] for f in both["findings"]} == {"fall", "rise"}

    def test_a_metric_filter_narrows_every_finding_not_only_those_shown(self, client):
        c, _ = client
        body = c.get("/api/triage", params={"days": 365, "kpi": "orders"}).json()
        assert body["total"] > 0 and {f["kpi_id"] for f in body["findings"]} == {"orders"}

    def test_the_regions_offered_are_the_readers_own(self, client):
        c, _ = client
        body = c.get("/api/triage", params={"days": 365, "entitled": "South"}).json()
        assert body["offer"]["regions"] == ["South"]
        picked = c.get("/api/triage", params={"days": 365, "region": "West"}).json()
        assert len(picked["offer"]["regions"]) == 4  # picking one does not remove the others
