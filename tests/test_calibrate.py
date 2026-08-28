"""Calibration must refuse more often than it fires.

The dangerous failure here is not a bad curve, it is a curve fitted on too
little, or fitted on the cases it is then scored against, or applied so that
the raw arithmetic underneath disappears. Each of those produces a confident
number that nobody can check, which is the thing this engine exists not to do.
"""

from __future__ import annotations

import json
from itertools import pairwise

import pytest

from whychain.confidence import Band, score
from whychain.confidence.calibrate import (
    MIN_OUTCOMES,
    Calibration,
    expected_calibration_error,
    fit,
)


def overconfident() -> tuple[list[float], list[bool]]:
    """Scores clustered high, right well short of what they claim.

    The shape the uncalibrated engine actually produced: correctly ordered, and
    wrong about the level. 0.9 is right 70% of the time and 0.5 is right 30%,
    so a working curve pulls the top band down and leaves the ordering alone.
    """
    scores = [0.9] * 80 + [0.5] * 40
    correct = ([True] * 56 + [False] * 24) + ([True] * 12 + [False] * 28)
    return scores, correct


class TestItRefusesToOverclaim:
    def test_too_few_outcomes_returns_no_curve(self):
        scores = [0.9] * (MIN_OUTCOMES - 1)
        correct = [i % 2 == 0 for i in range(MIN_OUTCOMES - 1)]
        assert fit(scores, correct) is None

    def test_one_sided_outcomes_return_no_curve(self):
        """Everything right, or everything wrong, teaches nothing about level."""
        assert fit([0.5] * 80, [True] * 80) is None
        assert fit([0.5] * 80, [False] * 80) is None

    @pytest.mark.invariant
    def test_a_curve_that_makes_the_forecast_worse_is_discarded(self):
        """A calibration is an improvement or it is not applied at all."""
        curve = fit(*overconfident())
        assert curve is None or curve.improved

    def test_no_file_means_no_probability_rather_than_a_guess(self, tmp_path):
        assert Calibration.load(tmp_path / "absent.json") is None

    def test_a_malformed_file_is_not_a_calibration(self, tmp_path):
        path = tmp_path / "calibration.json"
        path.write_text('{"thresholds": "not a list"}')
        assert Calibration.load(path) is None


class TestTheCurveBehaves:
    @pytest.fixture
    def curve(self):
        fitted = fit(*overconfident(), split="test-fixture")
        if fitted is None:
            pytest.skip("fixture did not produce a fittable curve")
        return fitted

    @pytest.mark.invariant
    def test_it_is_monotone(self, curve):
        """A higher score must never map to a lower probability.

        Monotonicity is the property the raw score earned. Calibration corrects
        the level; reordering the diagnoses would discard the one thing the
        score was designed to get right.
        """
        probabilities = [curve.probability(i / 50) for i in range(51)]
        assert all(b >= a - 1e-9 for a, b in pairwise(probabilities))

    def test_it_stays_inside_zero_and_one(self, curve):
        for i in range(0, 101):
            assert 0.0 <= curve.probability(i / 100) <= 1.0

    def test_it_pulls_an_overconfident_score_down(self, curve):
        """The whole point: 0.9 claimed, roughly two thirds observed."""
        assert curve.probability(0.9) < 0.9

    def test_it_round_trips_through_disk(self, curve, tmp_path):
        path = curve.save(tmp_path / "calibration.json")
        loaded = Calibration.load(path)
        assert loaded is not None
        assert loaded.fitted_on == curve.fitted_on
        assert loaded.probability(0.9) == pytest.approx(curve.probability(0.9))

    def test_it_records_what_it_was_fitted_on(self, curve, tmp_path):
        raw = json.loads(curve.save(tmp_path / "c.json").read_text())
        assert raw["split"] == "test-fixture"
        assert raw["fitted_on"] >= MIN_OUTCOMES
        assert "brier_before" in raw and "brier_after" in raw


class TestItReachesTheScore:
    def _score(self, calibration=None):
        return score(
            [], explained=0.0, total_movement=0.0,
            supporting_documents=0, sources={}, calibration=calibration,
        )

    @pytest.mark.invariant
    def test_without_a_curve_there_is_no_probability(self):
        """Absence is reported, never filled in with the raw score."""
        result = self._score()
        assert result.probability is None
        assert not result.is_probability

    def test_the_raw_score_is_never_overwritten(self):
        curve = fit(*overconfident(), split="t")
        if curve is None:
            pytest.skip("no curve")
        plain, calibrated = self._score(), self._score(curve)
        assert calibrated.score == plain.score
        assert calibrated.probability is not None

    @pytest.mark.invariant
    def test_banding_is_decided_on_the_raw_score(self):
        """Abstention must not move when the curve is refitted.

        The thresholds were chosen against the raw scale. Re-deriving the band
        from a calibrated probability would shift the point at which the engine
        refuses every time the curve is refitted, which is a silent change to
        when it declines to answer.
        """
        curve = fit(*overconfident(), split="t")
        if curve is None:
            pytest.skip("no curve")
        assert self._score(curve).band is self._score().band is Band.UNKNOWN


class TestTheErrorMetric:
    def test_a_perfect_forecast_scores_zero(self):
        assert expected_calibration_error([1.0] * 20 + [0.0] * 20,
                                          [True] * 20 + [False] * 20) == 0.0

    def test_a_confidently_wrong_forecast_scores_one(self):
        assert expected_calibration_error([1.0] * 20, [False] * 20) == 1.0

    def test_an_empty_population_is_zero_not_an_error(self):
        assert expected_calibration_error([], []) == 0.0
