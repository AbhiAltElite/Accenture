"""Personal data is masked for the person reading exactly as it is for the model.

The synthetic tickets carry none, so each case here writes its own. What is
asserted: every Indian identifier a support ticket plausibly holds is masked;
business figures survive; and the evidence drawer, which used to return the
ticket raw, never receives the original.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest

from whychain.corroborate.quarantine import redact

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

TICKET = ("Refund to priya.s@okhdfcbank or 9876543210@ybl. PAN ABCDE1234F. "
          "Mail priya@example.com, call +91 98765 43210. Card 4111 1111 1111 1111. "
          "Aadhaar 1234 5678 9012. Order 28,307 rupees on 2026-08-13, SKU PC1099.")
ORIGINALS = ("priya.s@okhdfcbank", "9876543210@ybl", "ABCDE1234F", "priya@example.com",
             "98765 43210", "4111 1111 1111 1111", "1234 5678 9012")


class TestPatterns:
    def test_every_identifier_is_masked(self):
        out, removed = redact(TICKET, ("pii",))
        for original in ORIGINALS:
            assert original not in out, original
        kinds = {r.split(":")[1].split(" ")[0] for r in removed}
        assert {"upi", "pan", "email", "phone", "card", "id-number"} <= kinds

    def test_a_number_based_upi_handle_is_masked_whole(self):
        out, _ = redact("refund 9876543210@ybl today", ("pii",))
        assert out == "refund [upi] today", "the phone pattern must not take the digits first"

    @pytest.mark.invariant
    def test_business_text_survives(self):
        for text in ("Order 28,307 rupees on 2026-08-13, down 10.4%.",
                     "SKU PC1099 launched; release 4.05 broke card entry",
                     "price @ 99 each, see @brandhandle"):
            assert redact(text, ("pii",)) == (text, ())


@pytest.fixture
def client(monkeypatch):
    if not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse not generated")
    from fastapi.testclient import TestClient

    import api.main as m

    doc = pd.DataFrame([{"doc_id": "TKPII1", "doc_type": "support_ticket", "region": "West",
                         "ts": pd.Timestamp("2026-08-14"), "text": TICKET}])

    class Fake:
        def table(self, name, **_):
            return doc

    @contextmanager
    def fake_warehouse(_vertical):
        yield Fake()

    monkeypatch.setattr(m, "warehouse", fake_warehouse)
    return TestClient(m.app)


def test_the_evidence_drawer_never_receives_the_original(client):
    body = client.get("/api/document/TKPII1").json()
    for original in ORIGINALS:
        assert original not in body["text"], original
    assert body["personal_data"]["scanned_for"] == ["pii"]
    assert len(body["personal_data"]["masked"]) >= 6
    assert "28,307 rupees" in body["text"] and "PC1099" in body["text"]


def test_a_clean_ticket_says_the_scan_ran(client, monkeypatch):
    import api.main as m
    clean = pd.DataFrame([{"doc_id": "TKOK", "doc_type": "support_ticket", "region": "West",
                           "ts": pd.Timestamp("2026-08-14"), "text": "Checkout page is blank."}])

    class Fake:
        def table(self, name, **_):
            return clean

    @contextmanager
    def fake_warehouse(_vertical):
        yield Fake()

    monkeypatch.setattr(m, "warehouse", fake_warehouse)
    body = client.get("/api/document/TKOK").json()
    assert body["personal_data"] == {"scanned_for": ["pii"], "masked": []}
