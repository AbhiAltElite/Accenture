"""Append-only evidence store with a lookup index and DAG integrity checks."""

from __future__ import annotations

from collections.abc import Iterator

from whychain.evidence.types import ClaimState, Evidence, EvidenceKind


class EvidenceError(Exception):
    """Raised when the evidence graph would be left in an invalid state."""


class EvidenceStore:
    """Holds every fact produced during one diagnosis run.

    Append-only by design: evidence is never mutated or removed, so a run can be
    replayed and a rejected candidate cannot quietly become a verified cause
    later (BUGS.md T-12).
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._by_id: dict[str, Evidence] = {}
        self._seq = 0

    def next_id(self) -> str:
        self._seq += 1
        return f"ev_{self._seq:04d}"

    def add(self, evidence: Evidence) -> Evidence:
        if evidence.id in self._by_id:
            raise EvidenceError(f"evidence {evidence.id} already recorded; store is append-only")
        if evidence.run_id != self.run_id:
            raise EvidenceError(
                f"evidence {evidence.id} belongs to run {evidence.run_id}, not {self.run_id}"
            )
        for ref in (*evidence.supports, *evidence.contradicts):
            if ref not in self._by_id:
                raise EvidenceError(
                    f"evidence {evidence.id} references {ref}, which does not exist. "
                    "Evidence must be added in dependency order."
                )
        self._by_id[evidence.id] = evidence
        return evidence

    def get(self, evidence_id: str) -> Evidence:
        try:
            return self._by_id[evidence_id]
        except KeyError:
            raise EvidenceError(f"no such evidence: {evidence_id}") from None

    def resolve_all(self, ids: list[str]) -> list[Evidence]:
        """Resolve every id or fail. Used by the narrative validator."""
        missing = [i for i in ids if i not in self._by_id]
        if missing:
            raise EvidenceError(f"unresolvable evidence ids: {missing}")
        return [self._by_id[i] for i in ids]

    def of_kind(self, kind: EvidenceKind) -> list[Evidence]:
        return [e for e in self._by_id.values() if e.kind == kind]

    def in_state(self, state: ClaimState) -> list[Evidence]:
        return [e for e in self._by_id.values() if e.state == state]

    def verified_claims(self) -> list[Evidence]:
        return self.in_state(ClaimState.VERIFIED)

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Evidence]:
        return iter(self._by_id.values())

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._by_id

    def assert_acyclic(self) -> None:
        """The support graph must be a DAG.

        Adding in dependency order makes cycles impossible, so this is a guard
        against a future change that relaxes that ordering.
        """
        colour: dict[str, int] = {}  # 0 = visiting, 1 = done

        def visit(node: str, path: list[str]) -> None:
            mark = colour.get(node)
            if mark == 1:
                return
            if mark == 0:
                cycle = " -> ".join([*path, node])
                raise EvidenceError(f"cycle in evidence graph: {cycle}")
            colour[node] = 0
            for ref in self._by_id[node].supports:
                visit(ref, [*path, node])
            colour[node] = 1

        for eid in self._by_id:
            visit(eid, [])
