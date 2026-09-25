"""Compute each contract's declared transform chain once, at ingest.

`dedupe_order_id` is a window partitioned by order id. Nothing can be pushed
below a window, so a region predicate cannot narrow it and every read
re-derived it over the whole table. Measured before this existed: sixteen times
the rows cost twenty-seven times the time for a one-region read, while the same
aggregation without the contract's transforms stayed flat at 1.3x. The work is
identical on every read and the warehouse does not change between generations.

    make prepare          # all three industries
    make prepare ARGS=retail

Safe to run twice: a chain already materialised is skipped. Safe never to run:
the read path falls back to the subquery it always used, so an unprepared
warehouse is slower and identical in every other respect.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whychain import verticals
from whychain.contracts import ContractError
from whychain.contracts.registry import ContractRegistry
from whychain.ingest import IngestError, materialise
from whychain.ingest.warehouse import Warehouse


def main(argv: list[str]) -> int:
    wanted = argv[1:] or [v.id for v in verticals.VERTICALS]
    total = 0
    for name in wanted:
        try:
            vertical = verticals.get(name)
        except (KeyError, verticals.UnknownVertical):
            print(f"  unknown industry {name!r}")
            return 2
        if not vertical.warehouse.exists():
            print(f"  {name}: no warehouse yet, run `make gen-all` first")
            continue
        try:
            contracts = list(ContractRegistry.from_directory(vertical.contracts_dir))
        except ContractError as exc:
            print(f"  {name}: {exc}")
            return 1

        started = time.monotonic()
        try:
            built = materialise(vertical.warehouse, contracts)
        except IngestError as exc:
            print(f"  {name}: {exc}")
            return 1
        elapsed = time.monotonic() - started

        size = vertical.warehouse.stat().st_size / 1e6
        if built:
            print(f"  {name}: materialised {len(built)} chain(s) in {elapsed:.1f}s "
                  f"({size:.0f}MB on disk)")
            for table in built:
                with Warehouse(vertical.warehouse) as wh:
                    rows = wh._con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                print(f"      {table}  {rows:,} rows")
        else:
            print(f"  {name}: already prepared, nothing to do")
        total += len(built)
    print(f"\n  {total} chain(s) built. Reads now hit a table instead of a window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
