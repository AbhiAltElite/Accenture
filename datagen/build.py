"""Build the dataset: `make gen`.

Writes the source tables to DuckDB and the ground truth to a directory the
engine has no code path to read. The separation is the point — the labels are
what the benchmark grades against, and an engine that can see them proves
nothing.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import duckdb

from datagen.demo_cases import DEMO_SCENARIOS
from datagen.scenarios import Scenario
from datagen.series import build_panel
from datagen.sources import (
    emit_plan_ops,
    emit_pos_txn,
    emit_sessions,
    emit_shipments,
    emit_voice_ops,
    source_freshness,
)

WAREHOUSE = Path("data/warehouse/whychain.duckdb")
GROUND_TRUTH = Path("data/ground_truth")


def _json_default(value):
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, frozenset | set):
        return sorted(value)
    return str(value)


def write_ground_truth(scenarios: tuple[Scenario, ...], directory: Path = GROUND_TRUTH) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "cases.json"
    payload = [asdict(s) for s in scenarios]
    path.write_text(json.dumps(payload, indent=2, default=_json_default))
    return path


def build(warehouse: Path = WAREHOUSE, scenarios: tuple[Scenario, ...] = DEMO_SCENARIOS) -> None:
    events = tuple(e for s in scenarios for e in s.events)

    print(f"building panel with {len(events)} planted events "
          f"({sum(1 for e in events if e.is_decoy)} decoys)...")
    panel = build_panel(events=events)

    print("emitting sources...")
    pos_txn = emit_pos_txn(panel)
    sessions = emit_sessions(panel)
    shipments = emit_shipments(panel, events)
    plan_ops = emit_plan_ops(panel, events)
    voice_ops = emit_voice_ops(panel, events)
    freshness = source_freshness()

    warehouse.parent.mkdir(parents=True, exist_ok=True)
    if warehouse.exists():
        warehouse.unlink()

    con = duckdb.connect(str(warehouse))
    for name, frame in (
        ("pos_txn", pos_txn),
        ("sessions", sessions),
        ("shipments", shipments),
        ("plan_ops", plan_ops),
        ("voice_ops", voice_ops),
        ("source_freshness", freshness),
        # The panel is kept as a convenience for inspection. The engine reads the
        # source tables, exactly as it would against a real warehouse.
        ("_panel", panel),
    ):
        con.register("frame", frame)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM frame")
        rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        print(f"  {name:20s} {rows:>10,} rows")
    con.close()

    path = write_ground_truth(scenarios)
    print(f"\nground truth: {len(scenarios)} labelled cases -> {path}")
    print(f"warehouse:    {warehouse}")


if __name__ == "__main__":
    build()
