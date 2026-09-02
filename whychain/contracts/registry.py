"""Loading and cross-checking the set of contracts.

Individual contracts validate themselves. The registry validates the things that
only make sense across contracts: that the KPI graph agrees with itself, that it
has no cycles, and that nothing references a metric that does not exist.

It is also where an applied feedback proposal reaches the engine. Corrections
that clear quorum are recorded as an overlay rather than written into the YAML,
and composed here at load: the contract file stays the reviewed definition, and
the change carries who applied it and on what evidence. The overlay is applied
before validation, so an overlaid contract has to satisfy every rule an
authored one does -- feedback cannot produce a contract a person could not have
written.
"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from whychain.contracts.models import KPIContract


class ContractError(Exception):
    """A contract or the contract set is invalid. Raised at load, never later."""


def _parse_durations(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept '6h' / '72h' / '30m' in YAML rather than ISO 8601.

    Contracts are meant to be edited by an analyst, not only by a developer.
    """
    sla = raw.get("freshness_sla")
    if not isinstance(sla, dict):
        return raw
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    parsed = {}
    for source, value in sla.items():
        if isinstance(value, str) and value[-1] in units and value[:-1].isdigit():
            parsed[source] = timedelta(**{units[value[-1]]: int(value[:-1])})
        else:
            parsed[source] = value
    return {**raw, "freshness_sla": parsed}


def _compose(raw: dict[str, Any], fields: dict[str, float]) -> dict[str, Any]:
    """Set dotted `field_path`s on a raw contract mapping, without mutating it.

    Deliberately dumb: it walks an existing path and refuses to create anything
    that is not already there. An overlay may change a value the contract's
    author declared; it may not introduce a section they never wrote. A typo in
    a field path is therefore a change that does nothing, rather than a new key
    the model would reject at a confusing distance from its cause.
    """
    out = deepcopy(raw)
    for path, value in fields.items():
        *parents, leaf = path.split(".")
        cursor: Any = out
        for key in parents:
            cursor = cursor.get(key) if isinstance(cursor, dict) else None
            if not isinstance(cursor, dict):
                break
        if isinstance(cursor, dict) and leaf in cursor:
            cursor[leaf] = value
    return out


def load_contract(
    path: Path, overlay: dict[str, float] | None = None
) -> KPIContract:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ContractError(f"{path.name}: not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ContractError(f"{path.name}: expected a mapping at the top level")
    if overlay:
        raw = _compose(raw, overlay)
    try:
        return KPIContract(**_parse_durations(raw))
    except Exception as exc:
        raise ContractError(f"{path.name}: {exc}") from exc


class ContractRegistry:
    """Every contract, with the KPI graph checked for consistency."""

    def __init__(self, contracts: dict[str, KPIContract]) -> None:
        self._contracts = contracts
        self._validate_graph()

    @classmethod
    def from_directory(
        cls,
        directory: Path | str,
        overlay: dict[str, dict[str, float]] | None = None,
    ) -> ContractRegistry:
        """Load every contract, with any applied feedback composed over it.

        `overlay` is keyed by kpi_id, and comes from
        `whychain.feedback.apply.AppliedStore.overlay()`. Passed in rather than
        read here so that loading a contract set stays a pure function of its
        arguments: a test, the benchmark and the console can each decide whether
        applied feedback is in scope, and none of them gets it by accident.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise ContractError(f"no such contract directory: {directory}")
        paths = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
        if not paths:
            raise ContractError(f"no contracts found in {directory}")

        overlay = overlay or {}
        contracts: dict[str, KPIContract] = {}
        for path in paths:
            contract = load_contract(path)
            if contract.kpi_id in overlay:
                contract = load_contract(path, overlay[contract.kpi_id])
            if contract.kpi_id in contracts:
                raise ContractError(
                    f"{path.name}: duplicate kpi_id {contract.kpi_id!r}; "
                    "a metric with two definitions has no definition"
                )
            contracts[contract.kpi_id] = contract
        return cls(contracts)

    def _validate_graph(self) -> None:
        known = set(self._contracts)

        for kpi_id, contract in self._contracts.items():
            unknown = sorted((set(contract.parents) | set(contract.children)) - known)
            if unknown:
                raise ContractError(f"{kpi_id}: references unknown KPIs: {unknown}")

            # Parent/child must be declared from both ends. A one-sided edge means
            # a cascade traversal finds different graphs depending on direction.
            for child_id in contract.children:
                if kpi_id not in self._contracts[child_id].parents:
                    raise ContractError(
                        f"{kpi_id} lists {child_id} as a child, but {child_id} "
                        f"does not list {kpi_id} as a parent"
                    )
            for parent_id in contract.parents:
                if kpi_id not in self._contracts[parent_id].children:
                    raise ContractError(
                        f"{kpi_id} lists {parent_id} as a parent, but {parent_id} "
                        f"does not list {kpi_id} as a child"
                    )

        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        colour: dict[str, int] = {}  # 0 = on the current path, 1 = fully explored

        def visit(kpi_id: str, path: list[str]) -> None:
            mark = colour.get(kpi_id)
            if mark == 1:
                return
            if mark == 0:
                raise ContractError(
                    "cycle in the KPI graph: " + " -> ".join([*path, kpi_id])
                )
            colour[kpi_id] = 0
            for child in self._contracts[kpi_id].children:
                visit(child, [*path, kpi_id])
            colour[kpi_id] = 1

        for kpi_id in self._contracts:
            visit(kpi_id, [])

    def get(self, kpi_id: str) -> KPIContract:
        try:
            return self._contracts[kpi_id]
        except KeyError:
            raise ContractError(f"no contract for KPI {kpi_id!r}") from None

    def descendants(self, kpi_id: str) -> list[str]:
        """Every KPI below this one, breadth-first.

        Used by materiality: a movement that cascades through several child
        metrics is broader, and breadth is part of the priority score.
        """
        seen: list[str] = []
        queue = list(self.get(kpi_id).children)
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.append(current)
            queue.extend(self.get(current).children)
        return seen

    def roots(self) -> list[str]:
        return [k for k, c in self._contracts.items() if not c.parents]

    def __len__(self) -> int:
        return len(self._contracts)

    def __iter__(self) -> Iterator[KPIContract]:
        return iter(self._contracts.values())

    def __contains__(self, kpi_id: object) -> bool:
        return kpi_id in self._contracts
