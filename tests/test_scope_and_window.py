"""Scope a candidate carries, the timezone a contract corrects, the window a filter keeps.

Each is a place where something true of one slice was applied to another:
B-056 (a SKU event tested as its region), B-058 (East orders read 5.5 hours off
their sessions) and B-059 (a filter that moved the window it narrowed within).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from whychain.contracts import ContractRegistry
from whychain.narrate.brief import grouped
from whychain.verify.candidates import _sku, from_operations, is_remediation
from whychain.verify.tests import Candidate, narrow_to

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


class TestSku:
    SKUS = ("PC-1099", "PC-101", "BV-2201")

    @pytest.mark.parametrize("text, sku", [
        ("pc1099-launch-dip: Introductory pricing ended", "PC-1099"),
        ("PC 1099 relaunched in the West", "PC-1099"),
        ("bv-2201 out of stock", "BV-2201"),
        ("PC-10990 is a different product", None),
        ("Release 4.05 broke card entry", None),
    ])
    def test_reads_the_code_however_it_is_typed(self, text, sku):
        assert _sku(text, self.SKUS) == sku

    def test_only_codes_the_warehouse_holds(self):
        assert _sku("ZZ-999 withdrawn", self.SKUS) is None

    def test_a_note_carries_its_sku_onto_the_candidate(self):
        notes = pd.DataFrame([{
            "doc_id": "OPS1", "doc_type": "ops_note", "ts": "2026-08-14 13:30:00+05:30",
            "region": "West", "text": "pc1099-launch-dip: Introductory pricing ended on a SKU.",
        }])
        [c] = from_operations(notes, date(2026, 8, 13), date(2026, 8, 15), skus=self.SKUS)
        assert c.sku == "PC-1099" and c.scope() == {"sku": "PC-1099"}


class TestNarrowing:
    PANEL = pd.DataFrame({"sku": ["A", "B"], "channel": ["app", "app"], "revenue": [1.0, 2.0]})

    def test_narrows_on_every_recorded_dimension(self):
        c = Candidate("x", "ops_note", date(2026, 1, 1), date(2026, 1, 2), ("West",), sku="B")
        assert narrow_to(self.PANEL, c)["revenue"].tolist() == [2.0]

    def test_a_dimension_the_panel_lacks_narrows_to_nothing(self):
        """Not to everything: widening is the defect this exists to prevent."""
        c = Candidate("x", "ops_note", date(2026, 1, 1), date(2026, 1, 2), ("West",), category="snacks")
        assert narrow_to(self.PANEL, c).empty


class TestRemediation:
    def test_a_rollback_is_a_remediation(self):
        assert is_remediation("Release note 4.05: rollback of the card entry component applied.")
        assert is_remediation("Hotfix shipped for the payment page")

    def test_the_regression_itself_is_not(self):
        assert not is_remediation("rel-4.05: Release 4.05 broke card entry on the Android checkout flow.")

    def test_a_remediation_is_not_offered_as_a_cause(self):
        notes = pd.DataFrame([{
            "doc_id": "OPS2", "doc_type": "release_log", "ts": "2026-08-19 20:30:00+05:30",
            "region": "West", "text": "Release note 4.05: rollback of the card entry component applied.",
        }])
        assert from_operations(notes, date(2026, 8, 12), date(2026, 8, 20)) == []


def test_every_contract_on_order_times_corrects_the_east_extract():
    """T-34. `orders` got `tz_normalise` in B-019; `aov` and `checkout_conversion`
    read the same timestamps and did not, until B-058."""
    for contract in ContractRegistry.from_directory(Path("contracts")):
        if contract.lineage.upstream[0].split(".")[0] == "pos_txn" or any(
            u.startswith("pos_txn") for u in contract.lineage.upstream
        ):
            assert contract.lineage.upstream[0].split(".")[0] == "pos_txn", (
                f"{contract.kpi_id}: transforms apply to the first upstream source, "
                "so pos_txn must be first for its correction to apply"
            )
            assert "tz_normalise" in contract.lineage.transforms, contract.kpi_id


@pytest.mark.parametrize("value, text", [
    (999, "999"), (36381, "36,381"), (271320, "2,71,320"), (46800895, "4,68,00,895"),
])
def test_prose_groups_digits_as_the_page_does(value, text):
    assert grouped(value) == text


def test_a_filter_does_not_move_the_window():
    """B-059: 90 days began on 1 Jun unfiltered and 18 May for one metric."""
    if not Path("data/warehouse/whychain.duckdb").exists():
        pytest.skip("warehouse not generated")
    from fastapi.testclient import TestClient

    from api.main import app
    c = TestClient(app)

    def earliest(**q):
        r = c.get("/api/triage", params={"industry": "retail", "limit": 50, "days": 90,
                                         "direction": "both", **q}).json()
        return min((f["end"] for f in r["findings"]), default="9999")

    floor = earliest()
    for q in ({"kpi": "on_time_delivery"}, {"region": "East"}, {"kpi": "aov"}):
        assert earliest(**q) >= floor, q


def test_a_word_inside_another_word_names_no_driver():
    """"suspended" contains "spend": a courier's collapse was put on the
    marketing budget, and the card told the marketing lead to apply media
    budget for South (B-073)."""
    from datetime import date
    from pathlib import Path

    from whychain.actions import _driver_for
    from whychain.contracts import load_contract
    from whychain.verify.tests import Candidate

    contract = load_contract(Path("contracts/net_revenue.yml"))
    note = Candidate("carrier-collapse-may", "ops_note", date(2026, 5, 18), date(2026, 5, 22),
                     ("South",), "A regional carrier suspended operations without notice.")
    assert _driver_for(note, contract) is None
    spend = Candidate("mk-1", "ops_note", date(2026, 5, 18), date(2026, 5, 22),
                      ("South",), "Marketing spend was cut in the South.")
    assert _driver_for(spend, contract).id == "marketing_spend"
