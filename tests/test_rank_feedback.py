"""The two-track ranking, and the bounded feedback loop.

Both stages exist to hold a line rather than to compute something hard, so the
tests are about the line: a correlation must never become a stated cause, and a
correction must never move a computed number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from whychain.decompose.contribution import Contribution, SliceContribution
from whychain.evidence import ClaimState, EvidenceKind
from whychain.feedback import (
    QUORUM,
    FeedbackStore,
    eval_cases,
    new_feedback,
    proposals,
)
from whychain.rank import Track, rank, rank_associational, rank_exact
from whychain.rank.tracks import as_evidence


def contribution(dimension: str, pairs: list[tuple[str, float, float]]) -> Contribution:
    slices = tuple(SliceContribution(dimension, v, b, c) for v, b, c in pairs)
    return Contribution(
        dimension=dimension,
        total_change=sum(s.delta for s in slices),
        slices=slices,
    )


CONTRIBUTIONS = [
    contribution("channel", [("app", 100_000, 77_000), ("store", 60_000, 55_000),
                             ("web", 40_000, 42_000)]),
]


class TestTrackA:
    def test_ranked_in_the_direction_the_total_moved(self):
        """A fall lists its biggest fallers first.

        Sorting by raw value puts the slices that moved *against* the total at
        the top of a list of reasons it fell, true of each row, and a lie about
        the list.
        """
        rows = rank_exact(CONTRIBUTIONS)
        assert [r.label for r in rows][:2] == ["channel · app", "channel · store"]
        assert rows[0].rank == 1

    def test_every_row_is_stateable(self):
        for row in rank_exact(CONTRIBUTIONS):
            assert row.track is Track.EXACT
            assert row.state is ClaimState.VERIFIED
            assert row.is_causal_claim

    def test_a_slice_that_moved_the_other_way_has_a_negative_share(self):
        web = next(r for r in rank_exact(CONTRIBUTIONS) if r.label.endswith("web"))
        assert web.value > 0 and web.share < 0


class TestTrackB:
    @pytest.fixture
    def series(self):
        rng = np.random.default_rng(11)
        days = pd.date_range("2026-06-01", periods=40).date
        price = rng.normal(100, 5, 40)
        spend = rng.normal(2000, 200, 40)
        metric = pd.Series(500_000 - price * 900 + rng.normal(0, 4000, 40), index=days)
        drivers = pd.DataFrame(
            {"realised_price": price, "marketing_spend": spend}, index=days
        )
        return metric, drivers

    @pytest.mark.invariant
    def test_no_row_may_be_stated_as_a_cause(self, series):
        """The line this whole stage exists to hold."""
        rows, _ = rank_associational(*series)
        assert rows
        for row in rows:
            assert row.track is Track.ASSOCIATIONAL
            assert row.state is ClaimState.HYPOTHESIS
            assert not row.is_causal_claim
            assert "correlational" in row.basis

    def test_a_rejected_candidate_cannot_re_enter_here(self, series):
        """BUGS.md T-12. Once rejected, rejected for the whole run."""
        metric, drivers = series
        rows, notes = rank_associational(
            metric, drivers, rejected=frozenset({"realised_price"})
        )
        assert not any(r.label == "realised price" for r in rows)
        assert any("already rejected" in n for n in notes)

    def test_too_few_observations_is_a_refusal_not_a_ranking(self):
        days = pd.date_range("2026-06-01", periods=6).date
        metric = pd.Series(range(6), index=days, dtype=float)
        drivers = pd.DataFrame({"x": range(6)}, index=days, dtype=float)
        rows, notes = rank_associational(metric, drivers)
        assert rows == ()
        assert any("not fitted" in n for n in notes)

    def test_a_driver_that_did_not_vary_is_named_not_dropped_silently(self):
        days = pd.date_range("2026-06-01", periods=30).date
        rng = np.random.default_rng(3)
        metric = pd.Series(rng.normal(100, 10, 30), index=days)
        drivers = pd.DataFrame(
            {"flat": [5.0] * 30, "moves": rng.normal(0, 1, 30)}, index=days
        )
        _, notes = rank_associational(metric, drivers)
        assert any("flat" in n for n in notes)


class TestTheTracksStayApart:
    @pytest.mark.invariant
    def test_the_two_tracks_are_never_merged(self):
        rng = np.random.default_rng(5)
        days = pd.date_range("2026-06-01", periods=30).date
        metric = pd.Series(rng.normal(100, 10, 30), index=days)
        drivers = pd.DataFrame({"price": rng.normal(50, 5, 30)}, index=days)
        ranking = rank(CONTRIBUTIONS, metric, drivers)
        assert ranking.exact and ranking.associational
        assert not ({r.label for r in ranking.exact}
                    & {r.label for r in ranking.associational})
        assert "candidate generator" in ranking.as_dict()["disclaimer"]

    def test_the_evidence_kinds_differ_so_the_two_cannot_be_confused(self):
        rng = np.random.default_rng(7)
        days = pd.date_range("2026-06-01", periods=30).date
        metric = pd.Series(rng.normal(100, 10, 30), index=days)
        drivers = pd.DataFrame({"price": rng.normal(50, 5, 30)}, index=days)
        ranking = rank(CONTRIBUTIONS, metric, drivers)
        records = as_evidence(ranking, "run-1", "pos_txn", "SELECT 1")
        kinds = {e.id: e.kind for e in records}
        assert EvidenceKind.CONTRIBUTION in kinds.values()
        assert EvidenceKind.ASSOCIATION in kinds.values()
        # A consumer filtering for stateable facts cannot pick up a correlation.
        stateable = [e for e in records if e.kind is EvidenceKind.CONTRIBUTION]
        assert all(e.state is ClaimState.VERIFIED for e in stateable)

    def test_no_driver_series_means_no_track_b_rather_than_a_faked_one(self):
        ranking = rank(CONTRIBUTIONS)
        assert ranking.associational == ()
        assert any("not run" in n for n in ranking.notes)


class TestFeedbackIsBounded:
    @pytest.fixture
    def store(self, tmp_path):
        return FeedbackStore(path=tmp_path / "feedback.jsonl")

    def entry(self, who="asha", judgement="wrong_owner", run="run-1", **kw):
        return new_feedback(
            run_id=run, kpi_id="net_revenue", persona="analyst",
            judgement=judgement, submitted_by=who,
            candidate_id=kw.pop("candidate_id", "rel-4.05"), **kw,
        )

    @pytest.mark.invariant
    def test_only_declared_judgements_are_learned_from(self):
        """The map is the enforcement. A comment is recorded and never acted on."""
        assert self.entry(judgement="wrong_owner").learnable
        assert not self.entry(judgement="comment").learnable
        assert not self.entry(judgement="confirmed").learnable

    def test_an_unknown_judgement_is_refused(self):
        with pytest.raises(ValueError):
            self.entry(judgement="retrain_the_model")

    def test_recording_is_append_only_and_counts_once(self, store):
        store.record(self.entry(who="asha"))
        store.record(self.entry(who="ravi"))
        assert store.summary()["total"] == 2
        assert len(store.path.read_text().strip().splitlines()) == 2

    def test_one_analyst_is_an_opinion_not_a_proposal(self, store):
        store.record(self.entry(who="asha"))
        proposal = store.summary()["proposals"][0]
        assert proposal["supporting"] == 1
        assert not proposal["applicable"]

    def test_quorum_makes_it_applicable(self, store):
        store.record(self.entry(who="asha", run="run-1"))
        store.record(self.entry(who="ravi", run="run-2"))
        proposal = store.summary()["proposals"][0]
        assert proposal["supporting"] == QUORUM
        assert proposal["applicable"]
        assert proposal["target"] == "driver_mapping"

    @pytest.mark.invariant
    def test_disagreement_produces_a_contested_proposal_not_an_average(self, store):
        """Two readers who disagree do not get silently averaged into one input."""
        for who in ("asha", "ravi"):
            store.record(self.entry(who=who))
        for who in ("meera", "vikram", "sunil"):
            store.record(self.entry(who=who, judgement="confirmed"))
        proposal = store.summary()["proposals"][0]
        assert proposal["contested"]
        assert not proposal["applicable"]

    def test_the_same_person_twice_is_still_one_voice(self, store):
        store.record(self.entry(who="asha", run="run-1"))
        store.record(self.entry(who="asha", run="run-2"))
        assert store.summary()["proposals"][0]["supporting"] == 1

    def test_a_named_miss_becomes_a_labelled_regression_case(self):
        entries = [
            self.entry(judgement="missed_cause", correction="warehouse power cut"),
            self.entry(judgement="comment"),
        ]
        cases = eval_cases(entries)
        assert len(cases) == 1
        assert cases[0]["expected_cause"] == "warehouse power cut"
        assert cases[0]["source"] == "analyst_correction"

    def test_a_miss_with_no_named_cause_is_not_a_case(self):
        assert eval_cases([self.entry(judgement="missed_cause")]) == ()

    def test_the_timestamp_is_not_taken_from_the_caller(self):
        """A client-supplied timestamp on an audit record is not an audit record."""
        entry = self.entry()
        assert entry.submitted_at.tzinfo is not None
        assert entry.feedback_id.startswith("fb-")

    def test_proposals_group_by_subject_not_by_run(self):
        """The same misrouted driver on six runs is one problem, not six."""
        entries = [self.entry(who=f"a{i}", run=f"run-{i}") for i in range(6)]
        assert len(proposals(entries)) == 1
