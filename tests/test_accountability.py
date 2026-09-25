"""Sign-off, decision rights, the audit chain, and identity from single sign-on.

These are the rules the decision view presents as enforced. Each is asserted
here through HTTP, the way a browser meets it, so a rule that only the page
honoured would fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from whychain.audit import AuditLog, evidence_fingerprint

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

WEST = {"kpi": "net_revenue", "region": "West", "start": "2026-08-13",
        "end": "2026-08-15", "industry": "retail"}
QUERY = {k: WEST[k] for k in ("kpi", "region", "start", "end", "industry")}


def as_(user: str) -> dict:
    return {"X-WhyChain-User": user}


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api.main as m
    if not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse not generated")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(m, "_audit", AuditLog(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("WHYCHAIN_IDENTITY", raising=False)
    monkeypatch.delenv("WHYCHAIN_TEAMS_WEBHOOK", raising=False)
    return TestClient(m.app), m


class TestSignoff:
    def test_only_the_accountable_owner_signs(self, client):
        c, _ = client
        r = c.post("/api/signoff", json=WEST, headers=as_("fpa.analyst"))
        assert r.status_code == 403
        assert r.json()["detail"]["accountable"] == "finance_director"

    def test_signature_records_the_evidence_and_holds(self, client):
        c, _ = client
        r = c.post("/api/signoff", json=WEST, headers=as_("finance.director"))
        assert r.status_code == 200
        signed = r.json()["signed"]
        assert signed["actor"]["source"] == "demo", "a laptop signature must say it is a demo"
        diag = c.get("/api/diagnose", params={**QUERY, "backend": "none"}).json()
        assert signed["payload"]["evidence"] == diag["evidence_fingerprint"]
        status = c.get("/api/signoff", params={**QUERY, "evidence": diag["evidence_fingerprint"]}).json()
        assert status["unchanged"] is True
        assert c.get("/api/signoff", params={**QUERY, "verify": True}).json()["unchanged"] is True

    def test_a_changed_fingerprint_is_reported(self, client):
        c, _ = client
        c.post("/api/signoff", json=WEST, headers=as_("finance.director"))
        status = c.get("/api/signoff", params={**QUERY, "evidence": "0" * 64}).json()
        assert status["unchanged"] is False

    def test_an_empty_entitlement_in_a_body_grants_nothing(self, client):
        # The server reads a present but empty entitlement as "nothing"; the
        # decision view once sent "" and every sign-off was refused. The rule
        # is right and stays; the client drops empty fields.
        c, _ = client
        r = c.post("/api/signoff", json={**WEST, "entitled": ""}, headers=as_("finance.director"))
        assert r.status_code == 403


class TestFingerprint:
    def test_identical_for_every_reader(self, client):
        c, _ = client
        prints = {c.get("/api/diagnose", params={**QUERY, "persona": p, "backend": "none"}).json()
                  ["evidence_fingerprint"] for p in ("analyst", "cfo", "ops")}
        assert len(prints) == 1

    def test_ignores_the_run_id_and_the_prose(self):
        base = {"kpi_id": "k", "region": "West", "verdict": "explained",
                "movement": {"total_change": -1.0}, "verified": [], "run_id": "a",
                "narrative": {"text": "one"}}
        other = {**base, "run_id": "b", "narrative": {"text": "two"}}
        assert evidence_fingerprint(base) == evidence_fingerprint(other)
        assert evidence_fingerprint(base) != evidence_fingerprint({**base, "verdict": "unknown"})


class TestDecisionRights:
    def test_only_the_assigned_role_decides(self, client):
        c, _ = client
        body = {**WEST, "action_id": "act-rel-4.05", "decision": "accept"}
        r = c.post("/api/decision", json=body, headers=as_("finance.director"))
        assert r.status_code == 403
        assert r.json()["detail"]["assigned_to"] == "ecommerce_lead"
        r = c.post("/api/decision", json=body, headers=as_("ecommerce.lead"))
        assert r.status_code == 200
        assert r.json()["recorded"]["payload"]["executed"] is False

    def test_a_modification_needs_a_note(self, client):
        c, _ = client
        r = c.post("/api/decision", json={**WEST, "action_id": "act-rel-4.05", "decision": "modify"},
                   headers=as_("ecommerce.lead"))
        assert r.status_code == 422

    def test_unknown_card_is_refused(self, client):
        c, _ = client
        r = c.post("/api/decision", json={**WEST, "action_id": "act-nope", "decision": "accept"},
                   headers=as_("ecommerce.lead"))
        assert r.status_code == 404


class TestAuditChain:
    def test_an_edited_entry_breaks_the_chain(self, client):
        c, m = client
        c.post("/api/signoff", json=WEST, headers=as_("finance.director"))
        c.post("/api/decision", json={**WEST, "action_id": "act-rel-4.05", "decision": "accept"},
               headers=as_("ecommerce.lead"))
        assert c.get("/api/audit").json()["chain"]["intact"] is True
        lines = m._audit.path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["payload"]["verdict"] = "unknown"
        lines[0] = json.dumps(first)
        m._audit.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        chain = c.get("/api/audit").json()["chain"]
        assert chain["intact"] is False and chain["broken_at"] == 1

    def test_a_deleted_entry_breaks_the_chain(self, client):
        c, m = client
        for _ in range(3):
            c.post("/api/signoff", json=WEST, headers=as_("finance.director"))
        lines = m._audit.path.read_text(encoding="utf-8").splitlines()
        del lines[1]
        m._audit.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert c.get("/api/audit").json()["chain"]["intact"] is False


SOUTH = {"X-Forwarded-Email": "reader@client.example", "X-Forwarded-User": "Reader",
             "X-Forwarded-Groups": "whychain:role:finance_director,whychain:region:South"}


class TestSingleSignOn:
    def test_no_identity_no_answer(self, client, monkeypatch):
        c, _ = client
        monkeypatch.setenv("WHYCHAIN_IDENTITY", "proxy")
        assert c.get("/api/kpis").status_code == 401
        assert c.get("/api/health").status_code == 200, "the platform's probe stays open"

    def test_regions_come_from_groups_and_cannot_be_widened(self, client, monkeypatch):
        c, _ = client
        monkeypatch.setenv("WHYCHAIN_IDENTITY", "proxy")
        q = {**QUERY, "backend": "none"}
        assert c.get("/api/diagnose", params=q, headers=SOUTH).status_code == 403
        widened = c.get("/api/diagnose", params={**q, "entitled": "West,South"}, headers=SOUTH)
        assert widened.status_code == 403

    def test_demo_headers_are_ignored_under_sso(self, client, monkeypatch):
        c, _ = client
        monkeypatch.setenv("WHYCHAIN_IDENTITY", "proxy")
        me = c.get("/api/me", headers={**SOUTH, "X-WhyChain-User": "finance.director"}).json()
        assert me["identity"]["source"] == "proxy"
        assert me["identity"]["regions"] == ["South"]
        assert me["demo_users"] == []


class TestService:
    def test_teams_says_when_it_did_not_send(self, client):
        c, _ = client
        # The release card: the SKU card this used was a cause the engine should
        # never have verified (B-056), and no longer exists.
        r = c.post("/api/dispatch/teams", json={**WEST, "action_id": "act-rel-4.05"},
                   headers=as_("fpa.analyst"))
        assert r.status_code == 200
        assert r.json()["sent"] is False
        assert r.json()["card"]["type"] == "AdaptiveCard"
        link = r.json()["card"]["actions"][0]["url"]
        assert "/finding?" in link and "8765" not in link

    def test_the_teams_card_carries_the_decision_as_it_stands(self, client):
        # It said "awaiting approval" after the owner had accepted.
        c, _ = client
        body = {**WEST, "action_id": "act-rel-4.05"}
        card = c.post("/api/dispatch/teams", json=body, headers=as_("fpa.analyst")).json()["card"]
        assert card["body"][0]["text"] == "Decision awaiting approval"
        assert c.post("/api/decision", json={**body, "decision": "accept"},
                      headers=as_("ecommerce.lead")).status_code == 200
        card = c.post("/api/dispatch/teams", json=body, headers=as_("fpa.analyst")).json()["card"]
        assert card["body"][0]["text"].startswith("Decision accepted by E-commerce Lead")
        facts = {f["title"]: f["value"] for f in card["body"][2]["facts"]}
        assert facts["Finding"].endswith("13 to 15 Aug 2026") and "₹" in facts["Expected recovery"]

    def test_only_an_accepted_decision_becomes_a_change_request(self, client):
        # A ticket for a decision nobody has taken would put a change in the
        # service desk's queue that its owner never agreed to.
        c, _ = client
        body = {**WEST, "action_id": "act-rel-4.05"}
        assert c.post("/api/dispatch/ticket", json=body, headers=as_("fpa.analyst")).status_code == 409
        assert c.post("/api/decision", json={**body, "decision": "accept"},
                      headers=as_("ecommerce.lead")).status_code == 200
        r = c.post("/api/dispatch/ticket", json=body, headers=as_("ecommerce.lead"))
        assert r.status_code == 200 and r.json()["sent"] is False
        t = r.json()["ticket"]
        assert t["reference"].startswith("WC-") and t["assignee_role"].startswith("E-commerce")
        assert t["decision"].startswith("Accepted by E-commerce Lead") and "₹" in t["expected_recovery"]
        assert t["done_when"] and "/finding?" in t["evidence"]["link"]
        entry = next(e for e in c.get("/api/audit").json()["entries"]
                     if e["event"] == "decision_accepted")
        assert t["evidence"]["audit_entry"] == entry["hash"]

    def test_a_rejected_decision_raises_no_ticket(self, client):
        c, _ = client
        body = {**WEST, "action_id": "act-rel-4.05"}
        assert c.post("/api/decision", json={**body, "decision": "reject"},
                      headers=as_("ecommerce.lead")).status_code == 200
        assert c.post("/api/dispatch/ticket", json=body, headers=as_("ecommerce.lead")).status_code == 409

    def test_trackrecord_is_read_not_typed(self, client):
        c, _ = client
        t = c.get("/api/trackrecord").json()
        report = json.loads(Path("bench/report.json").read_text(encoding="utf-8"))
        assert t["cases"] == report["counts"]["cases"]
        assert t["decoys_rejected"] == report["rates"]["negative_control_rejection"]
        named = [c for c in report["cases"] if c["verdict"] == "explained"]
        assert t["named_a_cause"] == len(named)
        assert t["exactly_right"] == sum(1 for c in named if set(c["verified"]) == {c["case_id"] + "-cause"})
        assert 0 <= t["decoy_let_through"] <= t["named_a_cause"]

    def test_headers_and_metrics(self, client):
        c, _ = client
        r = c.get("/api/health", headers={"X-Request-ID": "abc123"})
        assert r.headers["x-request-id"] == "abc123"
        assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "SAMEORIGIN"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "whychain_requests_total" in c.get("/api/metrics").text

    def test_pages_are_served(self, client):
        c, _ = client
        for path in ("/", "/finding", "/workbench", "/slide", "/uat", "/kpi/net_revenue"):
            r = c.get(path)
            assert r.status_code == 200 and b"WhyChain" in r.content, path


JUL = {"kpi": "net_revenue", "region": "West", "start": "2026-07-08", "end": "2026-07-12", "industry": "retail"}


class TestFairTarget:
    def test_a_warned_condition_is_flagged_not_excused(self, client):
        c, _ = client
        ft = c.get("/api/diagnose", params={**QUERY, "backend": "none"}).json()["fair_target"]
        weather = ft["factors"][0]
        assert weather["warned"] and not weather["excused_by_policy"]
        assert ft["policy_inr_per_day"] == ft["net_inr_per_day"]
        # scaled for the overlap: never more than the movement itself
        assert abs(weather["amount_inr_per_day"]) < abs(ft["net_inr_per_day"])
        assert ft["all_excused_inr_per_day"] == round(ft["net_inr_per_day"] - weather["amount_inr_per_day"], 2)

    def test_only_the_owner_adjusts_and_a_reason_is_required(self, client):
        c, _ = client
        body = {**JUL, "excuse": ["wx-flood-jul"]}
        assert c.post("/api/adjustment", json=body, headers=as_("fpa.analyst")).status_code == 403
        assert c.post("/api/adjustment", json=body, headers=as_("finance.director")).status_code == 422
        r = c.post("/api/adjustment", json={**body, "note": "Both DCs closed by order"}, headers=as_("finance.director"))
        assert r.status_code == 200
        assert r.json()["recorded"]["payload"]["team_inr_per_day"] == 0.0

    def test_a_controllable_cause_cannot_be_excused(self, client):
        c, _ = client
        r = c.post("/api/adjustment", json={**WEST, "excuse": ["rel-4.05"], "note": "x"},
                   headers=as_("finance.director"))
        assert r.status_code == 422

    def test_withheld_whole_under_partial_entitlement(self, client):
        # The net less the visible factors would recover a withheld cause's
        # exact value, so no figure is shown at all.
        c, _ = client
        q = {"kpi": "net_revenue", "start": "2026-08-13", "end": "2026-08-16",
             "backend": "none", "entitled": "South"}
        for persona in ("analyst", "cfo", "ops"):
            ft = c.get("/api/diagnose", params={**q, "persona": persona}).json()["fair_target"]
            assert ft["withheld"] is True and ft["factors"] == []
            assert not {"net_inr_per_day", "policy_inr_per_day", "all_excused_inr_per_day"} & set(ft)
        r = c.post("/api/adjustment", json={**WEST, "entitled": "South", "excuse": ["wx-mumbai-aug"],
                                            "note": "x"}, headers=as_("finance.director"))
        assert r.status_code == 403
