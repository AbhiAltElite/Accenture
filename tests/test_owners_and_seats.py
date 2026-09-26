"""Every owner can act in the demo, and every finding says who answers for it.

With five retail seats, no seat could sign a petroleum or power finding or
decide one of their cards, so the change-request flow could never be shown
outside retail (B-083). These assert the seat list covers every owner the
contracts and the demo decisions name, and that each finding carries its
accountability chain in the industry's own terms.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from whychain.identity import DEMO_USERS, SEATS

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

WEST = {"kpi": "net_revenue", "region": "West", "start": "2026-08-13", "end": "2026-08-15",
        "industry": "retail"}


def contract_owners() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for industry, folder in (("retail", "contracts"), ("petroleum", "contracts/petroleum"),
                             ("power", "contracts/power")):
        for path in Path(folder).glob("*.yml"):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("owner_role"):
                out.setdefault(industry, set()).add(doc["owner_role"])
    return out


def test_every_metric_owner_has_a_seat_in_their_industry():
    for industry, owners in contract_owners().items():
        seated = {s["role"] for s in SEATS.values() if industry in s["industries"]}
        assert owners <= seated, f"{industry}: no seat signs for {sorted(owners - seated)}"


def test_seats_are_complete_and_named_plainly():
    assert set(DEMO_USERS) == set(SEATS)
    for key, seat in SEATS.items():
        assert seat["view"] in ("cfo", "analyst", "ops"), key
        assert seat["what"].endswith("."), key
        assert "—" not in seat["what"], key
        assert set(seat["industries"]) <= {"retail", "petroleum", "power"}, key


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api.main as m
    if not Path("data/warehouse/petroleum.duckdb").exists():
        pytest.skip("warehouses not generated")
    from fastapi.testclient import TestClient

    from whychain.audit import AuditLog
    monkeypatch.setattr(m, "_audit", AuditLog(tmp_path / "audit.jsonl"))
    for var in ("WHYCHAIN_IDENTITY", "WHYCHAIN_TEAMS_WEBHOOK"):
        monkeypatch.delenv(var, raising=False)
    return TestClient(m.app)


def test_the_sign_in_list_says_where_each_seat_acts(client):
    users = client.get("/api/me").json()["demo_users"]
    by_id = {u["id"]: u for u in users}
    assert by_id["trading.head"]["industries"] == ["power"]
    assert by_id["supply.manager"]["view"] == "analyst"
    assert all(u["what"] for u in users)


@pytest.mark.parametrize(("industry", "query", "explains", "reviews"), [
    ("retail", "kpi=net_revenue&region=West&start=2026-08-13&end=2026-08-15",
     "Zonal Sales Manager, West", "National Sales Manager"),
    ("petroleum", "kpi=net_realisation&region=West&start=2026-08-13&end=2026-08-15",
     "Zonal Head, West", "Director, Marketing"),
    ("power", "kpi=dispatch_realisation&region=West&start=2026-08-12&end=2026-08-16",
     "Regional Executive Director, West", "Director, Commercial"),
])
def test_each_industry_names_its_own_line(client, industry, query, explains, reviews):
    for persona in ("cfo", "analyst", "ops"):
        a = client.get(f"/api/diagnose?{query}&industry={industry}&backend=none&persona={persona}").json()[
            "accountability"]
        assert a["explains"]["title"] == explains and a["reviews"]["title"] == reviews
        assert a["signs"]["role"] == "finance_director"
        # Every lever owner in every view, not only the one card a finance view shows.
        assert len(a["acts"]) >= (2 if industry != "retail" else 1), (persona, a["acts"])
        assert "Reference operating model" in a["reference"]


def test_a_finding_across_all_regions_is_explained_nationally(client):
    a = client.get("/api/diagnose?kpi=net_revenue&start=2026-07-30&end=2026-08-04&industry=retail"
                   "&backend=none&persona=cfo").json()["accountability"]
    assert a["explains"]["title"] == "National Sales Manager" and a["reviews"] is None


def test_a_contradicted_finding_says_why_nobody_acts(client):
    a = client.get("/api/diagnose?kpi=net_revenue&region=North&start=2026-06-10&end=2026-06-12"
                   "&industry=retail&backend=none&persona=cfo").json()["accountability"]
    assert a["acts"] == [] and "data engineering" in a["no_action"]


def test_the_accountability_chain_is_not_evidence(client, monkeypatch):
    # Roles and titles only: outside the fingerprint, so a change to the
    # operating model can never invalidate a signature.
    from dataclasses import replace

    import api.main as m
    q = "kpi=net_revenue&region=West&start=2026-08-13&end=2026-08-15&industry=retail&backend=none"
    before = client.get(f"/api/diagnose?{q}&persona=cfo").json()
    real = m._vertical

    def renamed(industry):
        v = real(industry)
        return replace(v, ladder=replace(v.ladder, explains=("x", "Someone else, {region}")))
    monkeypatch.setattr(m, "_vertical", renamed)
    after = client.get(f"/api/diagnose?{q}&persona=cfo").json()
    assert after["accountability"]["explains"]["title"] == "Someone else, West"
    assert after["evidence_fingerprint"] == before["evidence_fingerprint"]


def test_a_petroleum_owner_can_now_raise_a_change_request_in_the_demo(client):
    body = {"kpi": "net_realisation", "region": "West", "start": "2026-08-13", "end": "2026-08-15",
            "industry": "petroleum", "action_id": "act-TA-4411"}
    who = {"X-WhyChain-User": "supply.manager"}
    assert client.post("/api/decision", json={**body, "decision": "accept"},
                       headers={"X-WhyChain-User": "logistics.lead"}).status_code == 403
    assert client.post("/api/decision", json={**body, "decision": "accept"}, headers=who).status_code == 200
    r = client.post("/api/dispatch/ticket", json=body, headers=who)
    assert r.status_code == 200 and r.json()["ticket"]["assignee_role"] == "Supply manager"
    card = client.post("/api/dispatch/teams", json=body, headers=who).json()["card"]
    facts = {f["title"]: f["value"] for f in card["body"][2]["facts"]}
    assert facts["Explains"] == "Zonal Head, West"
