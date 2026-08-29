"""Build the dataset: `make gen`.

Writes the source tables to DuckDB and the ground truth to a directory the
engine has no code path to read. The separation is the point; the labels are
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
    emit_ext_signals,
    emit_plan_ops,
    emit_pos_txn,
    emit_sessions,
    emit_shipments,
    emit_voice_ops,
    source_freshness,
)
from datagen.world import RETAIL_WORLD, World

WAREHOUSE = Path("data/warehouse/whychain.duckdb")
GROUND_TRUTH = Path("data/ground_truth")


def _json_default(value):
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, frozenset | set):
        return sorted(value)
    return str(value)


def write_ground_truth(
    scenarios: tuple[Scenario, ...], target: Path = GROUND_TRUTH
) -> Path:
    """Write the labels. `target` may be the directory or the file itself.

    Each vertical keeps its own labels, and T-04 still holds for all of them:
    there is no import path from `whychain/` to any of these files.
    """
    path = target if target.suffix == ".json" else target / "cases.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(s) for s in scenarios]
    path.write_text(json.dumps(payload, indent=2, default=_json_default))
    return path


def build(
    warehouse: Path = WAREHOUSE,
    scenarios: tuple[Scenario, ...] = DEMO_SCENARIOS,
    world: World = RETAIL_WORLD,
    ground_truth: Path = GROUND_TRUTH,
) -> None:
    events = tuple(e for s in scenarios for e in s.events)

    print(f"building {world.id} panel with {len(events)} planted events "
          f"({sum(1 for e in events if e.is_decoy)} decoys)...")
    panel = build_panel(events=events, world=world)

    print("emitting sources...")
    pos_txn = emit_pos_txn(panel, world=world)
    sessions = emit_sessions(panel, world=world)
    shipments = emit_shipments(panel, events, world=world)
    plan_ops = emit_plan_ops(panel, events, world=world)
    voice_ops = emit_voice_ops(panel, events, world=world)
    declared = tuple(sig for s in scenarios for sig in s.signals)
    ext_signals = emit_ext_signals(panel, events, declared=declared, world=world)
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
        ("ext_signals", ext_signals),
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

    path = write_ground_truth(scenarios, ground_truth)
    print(f"\nground truth: {len(scenarios)} labelled cases -> {path}")
    print(f"warehouse:    {warehouse}")


# Where each world's warehouse and labels live. Retail keeps the original
# paths so nothing that refers to them has to change.
TARGETS: dict[str, tuple[Path, Path]] = {
    "retail": (WAREHOUSE, GROUND_TRUTH / "cases.json"),
    "petroleum": (
        Path("data/warehouse/petroleum.duckdb"),
        Path("data/ground_truth/petroleum/cases.json"),
    ),
    "power": (
        Path("data/warehouse/power.duckdb"),
        Path("data/ground_truth/power/cases.json"),
    ),
}


def build_world(world_id: str) -> None:
    """Build one named world into its own warehouse and label file."""
    from datagen.worlds import WORLDS
    from datagen.worlds.petroleum_cases import PETROLEUM_SCENARIOS
    from datagen.worlds.power_cases import POWER_SCENARIOS

    scenarios = {
        "retail": DEMO_SCENARIOS,
        "petroleum": PETROLEUM_SCENARIOS,
        "power": POWER_SCENARIOS,
    }[world_id]
    warehouse, labels = TARGETS[world_id]
    build(warehouse, scenarios, WORLDS[world_id], labels)


if __name__ == "__main__":
    import sys

    wanted = sys.argv[1:] or ["retail"]
    if wanted == ["all"]:
        wanted = list(TARGETS)
    for world_id in wanted:
        build_world(world_id)
