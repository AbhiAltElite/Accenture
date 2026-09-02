"""The step that turns a correction workflow into a loop that closes.

Capture, quorum and the contested state were already real and already tested.
What was missing was anything consuming a proposal, so objective 7 of the brief
rested on a mechanism that stopped one step short of mattering. These tests are
about that step, and most of them are about it refusing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from whychain.contracts.registry import load_contract
from whychain.feedback import Proposal, new_feedback, proposals
from whychain.feedback.apply import (
    CONSUMABLE,
    MAX_RAISE_MULTIPLE,
    AppliedStore,
    ApplyRefused,
    apply_proposal,
    proposed_threshold,
)

CONTRACT = Path("contracts/net_revenue.yml")


def a_proposal(**kw) -> Proposal:
    base = {
        "target": "materiality_threshold", "subject": "net_revenue",
        "change": "raise the floor", "supporting": 2, "contradicting": 0,
        "runs": ("run-1", "run-2"), "submitters": ("a.sharma", "r.iyer"),
        "contested": False, "movements": (26_963.0,),
    }
    return Proposal(**{**base, **kw})


@pytest.fixture
def store(tmp_path):
    return AppliedStore(path=tmp_path / "applied.jsonl")


class TestTheNewValueIsDerived:
    def test_the_floor_clears_the_largest_rejected_movement_and_no_more(self):
        """Nobody types the number.

        A threshold somebody picked to make a complaint go away is how a
        materiality floor becomes the place inconvenient findings are buried.
        """
        assert proposed_threshold(15_000, [10_000, 26_963, 4_000]) == pytest.approx(
            26_963 * 1.01
        )

    def test_the_raise_is_capped(self):
        """Materiality decides what a reader is shown at all, so an unbounded
        raise is the one change here that could quietly switch detection off."""
        assert proposed_threshold(15_000, [900_000]) == 15_000 * MAX_RAISE_MULTIPLE

    def test_no_recorded_movements_is_a_refusal_not_a_guess(self):
        with pytest.raises(ApplyRefused, match="chosen rather than derived"):
            proposed_threshold(15_000, [])

    def test_a_floor_that_already_excludes_them_is_not_moved(self):
        with pytest.raises(ApplyRefused, match="nothing to apply"):
            proposed_threshold(50_000, [26_963])


class TestTheRefusals:
    def test_an_unnamed_applier_is_refused(self, store):
        with pytest.raises(ApplyRefused, match="name the person"):
            apply_proposal(a_proposal(), kpi_id="net_revenue", current_value=15_000,
                           movements=[26_963], applied_by="   ", store=store)

    def test_a_contested_proposal_is_refused(self, store):
        with pytest.raises(ApplyRefused, match="contested"):
            apply_proposal(a_proposal(contested=True), kpi_id="net_revenue",
                           current_value=15_000, movements=[26_963],
                           applied_by="m.rao", store=store)

    def test_one_submitter_is_an_opinion(self, store):
        with pytest.raises(ApplyRefused, match="one person is an opinion"):
            apply_proposal(a_proposal(supporting=1), kpi_id="net_revenue",
                           current_value=15_000, movements=[26_963],
                           applied_by="m.rao", store=store)

    @pytest.mark.parametrize("target", [
        "candidate_ranking", "candidate_source", "driver_mapping", "retrieval_filter",
    ])
    def test_a_target_with_no_consumer_refuses_by_name(self, store, target):
        """A refusal a caller can read beats a queue nobody drains."""
        with pytest.raises(ApplyRefused, match="cannot be applied automatically"):
            apply_proposal(a_proposal(target=target), kpi_id="net_revenue",
                           current_value=15_000, movements=[26_963],
                           applied_by="m.rao", store=store)

    def test_nothing_is_written_when_an_application_is_refused(self, store):
        for bad in (a_proposal(contested=True), a_proposal(supporting=1)):
            with pytest.raises(ApplyRefused):
                apply_proposal(bad, kpi_id="net_revenue", current_value=15_000,
                               movements=[26_963], applied_by="m.rao", store=store)
        assert store.all() == []


class TestTheLoopActuallyCloses:
    def test_an_applied_change_reaches_the_contract(self, store):
        """The whole point. Two analysts, a named human, a different engine."""
        apply_proposal(a_proposal(), kpi_id="net_revenue", current_value=15_000,
                       movements=[26_963], applied_by="m.rao", store=store)

        authored = load_contract(CONTRACT)
        overlaid = load_contract(CONTRACT, store.overlay()["net_revenue"])
        assert authored.materiality.min_abs_delta_inr == 15_000
        assert overlaid.materiality.min_abs_delta_inr == pytest.approx(26_963 * 1.01)

    def test_the_record_carries_its_own_evidence(self, store):
        """"Why is this threshold what it is" must be answerable from the file."""
        change = apply_proposal(
            a_proposal(), kpi_id="net_revenue", current_value=15_000,
            movements=[26_963], applied_by="m.rao (finance director)", store=store,
        )
        assert change.applied_by == "m.rao (finance director)"
        assert change.submitters == ("a.sharma", "r.iyer")
        assert change.runs == ("run-1", "run-2")
        assert change.from_value == 15_000 and change.to_value > 15_000
        assert "26,963" in change.basis
        assert change.field_path == CONSUMABLE["materiality_threshold"]

    def test_the_store_rereads_when_the_file_changes(self, store):
        """Caching this outright serves the old threshold for the life of the
        process, and lifting a change by editing the file does nothing."""
        apply_proposal(a_proposal(), kpi_id="net_revenue", current_value=15_000,
                       movements=[26_963], applied_by="m.rao", store=store)
        assert store.overlay()["net_revenue"]
        store.path.unlink()
        assert store.overlay() == {}

    @pytest.mark.invariant
    def test_an_overlay_cannot_produce_a_contract_a_person_could_not_write(self):
        """Composed before validation, so every authored rule still applies."""
        from whychain.contracts.registry import ContractError

        with pytest.raises(ContractError):
            load_contract(CONTRACT, {"materiality.min_abs_delta_inr": -1.0})

    def test_an_overlay_cannot_invent_a_field(self):
        """A typo is a change that does nothing, not a new key."""
        c = load_contract(CONTRACT, {"materiality.made_up": 1.0, "nope.at.all": 2.0})
        assert c.materiality.min_abs_delta_inr == 15_000

    def test_feedback_carries_the_magnitude_a_threshold_is_derived_from(self):
        entries = [
            new_feedback(run_id=f"run-{i}", kpi_id="net_revenue", persona="analyst",
                         judgement="not_material", submitted_by=who,
                         movement_inr=26_963.0)
            for i, who in enumerate(("a.sharma", "r.iyer"))
        ]
        found = next(
            p for p in proposals(entries) if p.target == "materiality_threshold"
        )
        assert found.applicable and found.movements == (26_963.0, 26_963.0)
