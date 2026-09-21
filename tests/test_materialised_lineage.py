"""A materialised transform must be the transform the contract declares.

Computing a contract's lineage once at ingest instead of on every read is worth
roughly a hundredfold at scale, and it introduces one risk that did not exist
before: the stored table and the declared transforms can diverge. Nothing would
fail. The engine would serve rows derived from an older definition while every
contract, every receipt and `docs/REQUIREMENTS.md` continued to claim the
current one. A lineage claim that is false while still looking true is the exact
failure `access_policy.row_filter` once had, and BUGS.md T-26 names it.

So the equivalence is asserted rather than trusted. These tests are the reason
the optimisation is allowed to exist.
"""

from __future__ import annotations

import duckdb
import pytest

from whychain.contracts.registry import ContractRegistry
from whychain.ingest.warehouse import TRANSFORMS, prepared_name
from whychain.verticals import VERTICALS


def _prepared_verticals():
    """Only industries whose warehouse exists and has been prepared."""
    out = []
    for vertical in VERTICALS:
        if not vertical.warehouse.exists():
            continue
        con = duckdb.connect(str(vertical.warehouse), read_only=True)
        names = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables").fetchall()}
        con.close()
        if any(n.startswith("_prepared_") for n in names):
            out.append(vertical)
    return out


@pytest.mark.invariant
@pytest.mark.parametrize("vertical", _prepared_verticals(), ids=lambda v: v.id)
def test_materialised_matches_the_declared_transforms(vertical):
    """Row for row, the stored table equals the subquery it replaced."""
    contracts = list(ContractRegistry.from_directory(vertical.contracts_dir))
    con = duckdb.connect(str(vertical.warehouse), read_only=True)
    try:
        stored = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables").fetchall()}
        checked = 0
        for contract in contracts:
            chain = tuple(contract.lineage.transforms)
            if not chain:
                continue
            base = contract.lineage.upstream[0].split(".")[0]
            table = prepared_name(base, chain)
            if table not in stored:
                continue

            sql = base
            for name in chain:
                sql = f"({TRANSFORMS[name].format(table=sql)})"

            # EXCEPT ALL in both directions: same rows, same multiplicities.
            # A plain count would pass on two tables holding different rows.
            left = con.execute(
                f"SELECT count(*) FROM (SELECT * FROM {table} "
                f"EXCEPT ALL SELECT * FROM {sql})").fetchone()[0]
            right = con.execute(
                f"SELECT count(*) FROM (SELECT * FROM {sql} "
                f"EXCEPT ALL SELECT * FROM {table})").fetchone()[0]
            assert left == 0 and right == 0, (
                f"{vertical.id}/{contract.kpi_id}: the materialised table "
                f"{table} differs from the transforms it claims to be "
                f"({left} rows only in the table, {right} only in the query). "
                f"Rebuild with `make prepare`."
            )
            checked += 1
        assert checked, (
            f"{vertical.id} has _prepared_ tables but none matched a contract's "
            f"declared chain, so this test proved nothing"
        )
    finally:
        con.close()


def test_the_name_changes_when_a_transform_is_redefined():
    """A redefined transform must miss, not serve rows built under the old SQL.

    The chain's names alone would collide: editing what `dedupe_order_id` does
    while leaving it called that would hash identically and the engine would
    happily serve the previous definition. The SQL is in the payload for this
    reason, and this test is what stops someone removing it as redundant.
    """
    before = prepared_name("pos_txn", ("dedupe_order_id",))
    original = TRANSFORMS["dedupe_order_id"]
    try:
        TRANSFORMS["dedupe_order_id"] = original.replace("ORDER BY order_ts", "ORDER BY 1")
        after = prepared_name("pos_txn", ("dedupe_order_id",))
    finally:
        TRANSFORMS["dedupe_order_id"] = original
    assert before != after


def test_order_matters_in_the_chain():
    """Transforms compose, so two orderings are two different tables."""
    a = prepared_name("pos_txn", ("dedupe_order_id", "tz_normalise"))
    b = prepared_name("pos_txn", ("tz_normalise", "dedupe_order_id"))
    assert a != b
