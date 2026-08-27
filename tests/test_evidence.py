"""Evidence model and store behaviour, including hard invariants."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from whychain.evidence import (
    ClaimState,
    Evidence,
    EvidenceError,
    EvidenceKind,
    EvidenceStore,
    Freshness,
    MethodClass,
    Provenance,
    Unit,
)

RUN = "run_test"


def make(store: EvidenceStore, **overrides) -> Evidence:
    kwargs = {
        "id": store.next_id(),
        "kind": EvidenceKind.DECOMPOSITION,
        "claim": "Volume effect of -8.2 lakh",
        "value": -820000.0,
        "unit": Unit.INR,
        "method": "pvm_bridge",
        "method_class": MethodClass.DETERMINISTIC,
        "provenance": Provenance(source_id="pos_txn", query="SELECT 1", row_count=10),
        "run_id": RUN,
    }
    kwargs.update(overrides)
    return Evidence(**kwargs)


class TestProvenance:
    def test_requires_a_trail(self):
        with pytest.raises(ValidationError, match=r"query.*or a doc_id"):
            Provenance(source_id="pos_txn")

    def test_document_provenance_requires_span(self):
        with pytest.raises(ValidationError, match="character span"):
            Provenance(source_id="voice_ops", doc_id="tk_1")

    def test_document_provenance_with_span_is_valid(self):
        p = Provenance(source_id="voice_ops", doc_id="tk_1", span=(0, 29), quote="Checkout fails")
        assert p.span == (0, 29)


@pytest.mark.invariant
class TestUnitMethodAgreement:
    """BUGS.md T-03: a method cannot produce a unit it has no business producing."""

    def test_bridge_cannot_produce_counts(self):
        store = EvidenceStore(RUN)
        with pytest.raises(ValidationError, match="cannot produce unit"):
            make(store, method="pvm_bridge", unit=Unit.COUNT, value=18100.0)

    def test_bridge_produces_currency(self):
        store = EvidenceStore(RUN)
        assert make(store, method="pvm_bridge", unit=Unit.INR).unit is Unit.INR

    def test_did_may_report_percentage_points_not_percent(self):
        """BUGS.md T-02: percent and percentage point are different units."""
        store = EvidenceStore(RUN)
        make(store, method="did", unit=Unit.PCT_POINT, value=-7.0)
        with pytest.raises(ValidationError):
            make(store, method="did", unit=Unit.PCT, value=-7.0)


class TestFreshness:
    def test_sla_met(self):
        f = Freshness(
            source_id="pos_txn",
            as_of=datetime(2026, 8, 14, 8, 0, tzinfo=UTC),
            observed_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            sla=timedelta(hours=6),
        )
        assert f.lag == timedelta(hours=4)
        assert f.sla_met is True

    def test_sla_breached(self):
        f = Freshness(
            source_id="plan_ops",
            as_of=datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
            observed_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            sla=timedelta(hours=72),
        )
        assert f.sla_met is False


class TestStore:
    def test_append_only(self):
        store = EvidenceStore(RUN)
        e = store.add(make(store))
        with pytest.raises(EvidenceError, match="append-only"):
            store.add(e)

    def test_rejects_foreign_run(self):
        store = EvidenceStore(RUN)
        with pytest.raises(EvidenceError, match="belongs to run"):
            store.add(make(store, run_id="other_run"))

    def test_references_must_exist(self):
        store = EvidenceStore(RUN)
        with pytest.raises(EvidenceError, match="does not exist"):
            store.add(make(store, supports=("ev_9999",)))

    def test_resolve_all_reports_missing(self):
        store = EvidenceStore(RUN)
        first = store.add(make(store))
        with pytest.raises(EvidenceError, match="unresolvable"):
            store.resolve_all([first.id, "ev_9999"])

    def test_evidence_is_immutable(self):
        store = EvidenceStore(RUN)
        e = store.add(make(store))
        with pytest.raises(ValidationError):
            e.claim = "something else"


@pytest.mark.invariant
class TestGraphIntegrity:
    """Invariant 12: the support graph is acyclic."""

    def test_dependency_chain_is_acyclic(self):
        store = EvidenceStore(RUN)
        a = store.add(make(store))
        b = store.add(make(store, supports=(a.id,)))
        store.add(make(store, supports=(a.id, b.id)))
        store.assert_acyclic()

    def test_states_are_distinct(self):
        """DECISIONS.md D-006: cannot_verify is not rejected."""
        assert ClaimState.CANNOT_VERIFY != ClaimState.REJECTED
        store = EvidenceStore(RUN)
        store.add(make(store, method="did", unit=Unit.INR, state=ClaimState.CANNOT_VERIFY))
        store.add(make(store, method="did", unit=Unit.INR, state=ClaimState.REJECTED))
        assert len(store.in_state(ClaimState.CANNOT_VERIFY)) == 1
        assert len(store.in_state(ClaimState.REJECTED)) == 1
        assert store.verified_claims() == []
