"""The same question, asked again, gives the same figures to the paisa (B-079).

A float SUM across DuckDB's threads adds in the order the threads finish, so a
petroleum total came back ...437.49 on most requests and ...437.50 on about one
in twelve. The evidence fingerprint is computed over those figures, and a signed
finding compares its fingerprint on every open: the wobble alone could tell a
signer their evidence had changed.
"""

from __future__ import annotations

from datetime import date

import pytest

from whychain.contracts.registry import ContractRegistry
from whychain.ingest.warehouse import Warehouse
from whychain.verticals import VERTICALS

PETROLEUM = next(v for v in VERTICALS if v.id == "petroleum")


@pytest.mark.skipif(not PETROLEUM.warehouse.exists(), reason="warehouse not generated")
def test_a_repeated_read_is_identical_to_the_paisa():
    contract = ContractRegistry.from_directory(PETROLEUM.contracts_dir).get("net_realisation")
    totals = set()
    with Warehouse(PETROLEUM.warehouse) as wh:
        first = wh.bridge_facts(contract, since=date(2026, 7, 1), until=date(2026, 8, 15))
        for _ in range(60):
            facts = wh.bridge_facts(contract, since=date(2026, 7, 1), until=date(2026, 8, 15))
            # Exactly, not rounded: rounding would hide a wobble that lands on a
            # rounding boundary, which is how this one reached the fingerprint.
            totals.add((float(facts["revenue"].sum()), float(facts["units"].sum())))
            assert facts.equals(first)
    assert len(totals) == 1, f"one question, {len(totals)} different totals: {sorted(totals)[:3]}"
