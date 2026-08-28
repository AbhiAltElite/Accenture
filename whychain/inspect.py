"""Inspect what the engine currently knows.

Built for checking progress before there is a UI: it reads the real contracts
through the real loader, so if this prints, the governance layer genuinely works.

    python -m whychain.inspect
"""

from __future__ import annotations

import sys
from pathlib import Path

from whychain.contracts import ContractError, ContractRegistry

DIM = "\033[2m"
BOLD = "\033[1m"
OFF = "\033[0m"


def _tree(registry: ContractRegistry, kpi_id: str, prefix: str = "", last: bool = True) -> None:
    contract = registry.get(kpi_id)
    branch = "└── " if last else "├── "
    grain = f"{contract.grain.time} by {'/'.join(contract.grain.dims)}"
    print(f"{prefix}{branch}{BOLD}{kpi_id}{OFF}  {DIM}{grain}{OFF}")

    children = contract.children
    child_prefix = prefix + ("    " if last else "│   ")
    for i, child in enumerate(children):
        _tree(registry, child, child_prefix, i == len(children) - 1)


def main() -> int:
    try:
        registry = ContractRegistry.from_directory(Path("contracts"))
    except ContractError as exc:
        print(f"contracts failed to load: {exc}", file=sys.stderr)
        return 1

    print(f"\n{BOLD}KPI graph{OFF}  ({len(registry)} contracts)")
    roots = registry.roots()
    for i, root in enumerate(roots):
        _tree(registry, root, "", i == len(roots) - 1)

    print(f"\n{BOLD}Drivers by metric{OFF}")
    for contract in registry:
        actionable = {d.id for d in contract.controllable_drivers()}
        rendered = [
            f"{d.id}{DIM}→{d.owner_role}{OFF}" if d.id in actionable else f"{DIM}{d.id}{OFF}"
            for d in contract.drivers
        ]
        print(f"  {contract.kpi_id:22s} {'  '.join(rendered)}")
    print(f"  {DIM}dimmed = observable only, no lever and no owner{OFF}")

    print(f"\n{BOLD}Freshness SLAs{OFF}")
    sources = sorted({s for c in registry for s in c.freshness_sla})
    for source in sources:
        slas = {c.freshness_sla[source] for c in registry if source in c.freshness_sla}
        shown = ", ".join(sorted(str(s) for s in slas))
        print(f"  {source:16s} {shown}")

    print(f"\n{BOLD}Signal coverage{OFF}  {DIM}what each planning process is known to consume{OFF}")
    for contract in registry:
        sc = contract.signals_consumed
        if sc.coverage.value == "unknown":
            print(f"  {contract.kpi_id:22s} {DIM}unknown, no process document registered{OFF}")
            continue
        print(f"  {contract.kpi_id:22s} {sc.coverage.value}: {', '.join(sorted(sc.signal_ids))}")
        print(f"  {'':22s} {DIM}from {sc.derived_from}{OFF}")

    print(f"\n{BOLD}Access policy{OFF}")
    for contract in registry:
        ap = contract.access_policy
        bits = []
        if ap.row_filter:
            bits.append(f"rows: {ap.row_filter}")
        if ap.column_masks:
            bits.append(f"masked: {', '.join(ap.column_masks)}")
        if ap.domain_restriction:
            bits.append(f"excluded from prompts: {', '.join(ap.domain_restriction)}")
        print(f"  {contract.kpi_id:22s} {'  ·  '.join(bits) or DIM + 'none' + OFF}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
