"""Contract loading, cross-contract graph checks, and span resolution."""

from datetime import timedelta
from pathlib import Path

import pytest

from whychain.contracts import (
    ContractError,
    ContractRegistry,
    Coverage,
    Driver,
    KPIContract,
    load_contract,
)

CONTRACTS = Path("contracts")


@pytest.fixture(scope="module")
def registry() -> ContractRegistry:
    return ContractRegistry.from_directory(CONTRACTS)


class TestRealContracts:
    def test_all_five_load(self, registry):
        assert len(registry) == 5
        assert {c.kpi_id for c in registry} == {
            "net_revenue", "orders", "aov", "checkout_conversion", "on_time_delivery",
        }

    def test_durations_parse_from_shorthand(self, registry):
        assert registry.get("net_revenue").freshness_sla["pos_txn"] == timedelta(hours=6)

    def test_revenue_cascade(self, registry):
        assert registry.descendants("net_revenue") == ["orders", "aov", "checkout_conversion"]

    def test_conversion_runs_at_a_finer_grain_than_its_parent(self, registry):
        """The grain mismatch is deliberate; it is what the reconciler must handle."""
        assert registry.get("checkout_conversion").grain.time == "hour"
        assert registry.get("orders").grain.time == "day"


class TestDrivers:
    def test_controllable_driver_needs_an_owner(self):
        with pytest.raises(ValueError, match="an action nobody owns"):
            Driver(id="unit_price", source="pos_txn", controllable_lever="pricing")

    def test_observable_driver_needs_neither(self):
        d = Driver(id="severe_weather", source="ext_signals")
        assert d.controllable_lever is None and d.owner_role is None

    def test_only_actionable_drivers_are_returned(self, registry):
        controllable = {d.id for d in registry.get("net_revenue").controllable_drivers()}
        assert "unit_price" in controllable
        assert "severe_weather" not in controllable, "nobody has a weather lever"


class TestContractValidation:
    def _minimal(self, **overrides) -> dict:
        base = {
            "kpi_id": "test_kpi", "version": 1, "owner_role": "analyst",
            "definition": "A test metric.",
            "calculation": {"canonical_sql": "SELECT 1", "dialect_targets": ["duckdb"]},
            "grain": {"time": "day", "dims": ["region"]},
            "dimensions": ["region"],
            "drivers": [{"id": "d1", "source": "pos_txn"}],
            "materiality": {"min_abs_robust_z": 3.0, "min_abs_delta_inr": 1000.0},
            "freshness_sla": {"pos_txn": timedelta(hours=6)},
            "lineage": {"upstream": ["pos_txn"]},
        }
        return {**base, **overrides}

    def test_driver_source_must_have_an_sla(self):
        with pytest.raises(ValueError, match="no freshness SLA"):
            KPIContract(**self._minimal(drivers=[{"id": "d1", "source": "unknown_src"}]))

    def test_grain_dims_must_be_declared(self):
        with pytest.raises(ValueError, match="undeclared dimensions"):
            KPIContract(**self._minimal(grain={"time": "day", "dims": ["region", "ghost"]}))

    def test_duplicate_driver_ids_rejected(self):
        with pytest.raises(ValueError, match="duplicate driver ids"):
            KPIContract(**self._minimal(
                drivers=[{"id": "d1", "source": "pos_txn"}, {"id": "d1", "source": "pos_txn"}]
            ))

    def test_execution_dialect_required(self):
        with pytest.raises(ValueError, match="must include 'duckdb'"):
            KPIContract(**self._minimal(
                calculation={"canonical_sql": "SELECT 1", "dialect_targets": ["snowflake"]}
            ))


@pytest.mark.invariant
class TestGraphIntegrity:
    def _pair(self, a_children=(), b_parents=()) -> dict[str, KPIContract]:
        def build(kpi_id, parents, children):
            return KPIContract(
                kpi_id=kpi_id, version=1, owner_role="analyst", definition="x",
                calculation={"canonical_sql": "SELECT 1", "dialect_targets": ["duckdb"]},
                grain={"time": "day", "dims": ["region"]}, dimensions=["region"],
                parents=parents, children=children,
                drivers=[{"id": "d1", "source": "pos_txn"}],
                materiality={"min_abs_robust_z": 3.0, "min_abs_delta_inr": 1000.0},
                freshness_sla={"pos_txn": timedelta(hours=6)},
                lineage={"upstream": ["pos_txn"]},
            )
        return {"a": build("a", (), a_children), "b": build("b", b_parents, ())}

    def test_one_sided_edge_rejected(self):
        """A cascade must find the same graph travelling in either direction."""
        with pytest.raises(ContractError, match="does not list"):
            ContractRegistry(self._pair(a_children=("b",), b_parents=()))

    def test_consistent_edge_accepted(self):
        assert len(ContractRegistry(self._pair(a_children=("b",), b_parents=("a",)))) == 2

    def test_unknown_reference_rejected(self):
        with pytest.raises(ContractError, match="unknown KPIs"):
            ContractRegistry(self._pair(a_children=("ghost",)))

    def test_real_graph_is_acyclic(self, registry):
        registry._assert_acyclic()


@pytest.mark.invariant
class TestSignalConsumption:
    """D-005: consumption must be evidenced against a document, never asserted."""

    def test_spans_resolve_to_the_named_signal(self, registry):
        """A span that does not contain its signal is a decorative reference."""
        contract = registry.get("net_revenue")
        sop = Path(contract.signals_consumed.derived_from).read_text()

        for extracted in contract.signals_consumed.extracted:
            start, end = extracted.span
            assert 0 <= start < end <= len(sop), f"{extracted.signal}: span outside the document"
            passage = sop[start:end].lower()
            words = extracted.signal.split("_")
            assert all(w in passage for w in words), (
                f"{extracted.signal}: span does not mention it, {passage[:70]!r}"
            )

    def test_coverage_requires_a_source_document(self):
        from whychain.contracts import SignalsConsumed

        with pytest.raises(ValueError, match="must be evidenced"):
            SignalsConsumed(coverage=Coverage.COMPLETE)

    def test_unknown_coverage_is_a_valid_honest_state(self, registry):
        """No SOP registered means Answer 2 declines, not that it infers a gap.

        Asserted over the registry rather than against a named KPI. The property
        that matters is that the state exists, is reachable, and carries no
        extracted signals, not which contract happens to be in it this week.
        Pinning it to `on_time_delivery` made registering that KPI's SOP look
        like a regression when it was the point.
        """
        unknown = [
            c for c in registry
            if c.signals_consumed.coverage is Coverage.UNKNOWN
        ]
        assert unknown, (
            "no contract has unknown signal coverage, so the branch of Answer 2 "
            "that declines for lack of a process document is now unreachable "
            "from the demo data"
        )
        for contract in unknown:
            assert contract.signals_consumed.signal_ids == frozenset()
            assert contract.signals_consumed.derived_from is None

    def test_a_registered_sop_makes_answer_two_decidable(self, registry):
        """The other half: a contract with a document can reach a gap verdict."""
        registered = [
            c for c in registry
            if c.signals_consumed.coverage is not Coverage.UNKNOWN
        ]
        assert registered, "no contract carries a process document"
        for contract in registered:
            assert contract.signals_consumed.derived_from
            assert contract.signals_consumed.signal_ids

    def test_standard_cycle_consumes_no_external_risk_signal(self, registry):
        """The Answer 2 finding, asserted against the document itself.

        The registered process consumes sales, inventory, capacity and financials.
        Nothing external. If someone adds a weather input to the SOP, this test
        fails and the demo's central claim gets revisited rather than quietly
        becoming false.
        """
        consumed = registry.get("net_revenue").signals_consumed.signal_ids
        assert consumed == {
            "historical_sales", "inventory_position", "capacity_metrics", "financial_plan",
        }
        assert not any("weather" in s or "external" in s for s in consumed)


class TestLoaderErrors:
    def test_missing_directory(self):
        with pytest.raises(ContractError, match="no such contract directory"):
            ContractRegistry.from_directory("does/not/exist")

    def test_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("kpi_id: [unclosed")
        with pytest.raises(ContractError, match="not valid YAML"):
            load_contract(bad)

    def test_duplicate_kpi_id(self, tmp_path):
        for name in ("a.yml", "b.yml"):
            (tmp_path / name).write_text(
                (CONTRACTS / "aov.yml").read_text()
            )
        with pytest.raises(ContractError, match="two definitions"):
            ContractRegistry.from_directory(tmp_path)
