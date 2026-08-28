"""The report file must contain the run that produced it.

`make bench` prints its numbers and then writes them. When the write fails
after the print, the terminal shows one set of figures and `bench/report.json`
keeps the last set that succeeded. Every document written from the file then
disagrees with the run, and nothing in the output says so. That happened
(B-015), so the serialisation boundary has a test.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from bench.run import _jsonable


class TestTheReportSerialises:
    @pytest.mark.invariant
    @pytest.mark.parametrize(
        "value",
        [np.bool_(True), np.int64(3), np.float64(0.5), np.float32(0.25)],
        ids=["bool", "int", "float64", "float32"],
    )
    def test_numpy_scalars_survive_the_boundary(self, value):
        """Comparisons on pandas and numpy values do not return Python types."""
        assert json.dumps({"v": value}, default=_jsonable)

    def test_a_type_it_cannot_convert_raises_rather_than_silently_dropping(self):
        """A new unserialisable type must fail loudly, not vanish from the report."""
        with pytest.raises(TypeError, match="cannot serialise"):
            json.dumps({"v": object()}, default=_jsonable)

    def test_an_outcome_shaped_row_round_trips(self):
        """The shape the harness actually writes, with numpy where it arises."""
        row = {
            "case_id": "bench-00-west-0",
            "top1": np.bool_(True),
            "decoy_rejected": np.bool_(False),
            "confidence": np.float64(0.86),
            "verified": ["rel-4.05"],
            "error": None,
        }
        assert json.loads(json.dumps(row, default=_jsonable))["top1"] is True
