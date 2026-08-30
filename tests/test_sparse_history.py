"""A metric with too little history is answered, not rejected.

`decompose` refuses under sixty observations, and correctly: three years of
history gives three observations per day-of-year, and seventeen days gives none
at all, so a seasonal component fitted to it is a shape invented from noise.

What was wrong was the shape of the refusal. It surfaced as HTTP 422 -- a bad
request -- which tells a reader they did something wrong rather than telling them
what can and cannot be said about a product that launched a fortnight ago. The
brief asks for a sparse-history *scenario*, and an exception is not one.
"""

import numpy as np
import pandas as pd
import pytest

from api.main import _sparse_series
from whychain.contracts import ContractRegistry
from whychain.detect import decompose_for


@pytest.fixture(scope="module")
def contract():
    return ContractRegistry.from_directory("contracts").get("net_revenue")


@pytest.fixture
def short_frame():
    """Seventeen days: a plausible new SKU, and far under the floor."""
    rng = np.random.default_rng(7)
    days = pd.date_range("2026-08-01", periods=17, freq="D")
    return pd.DataFrame({"d": days, "value": rng.normal(1000, 40, 17)})


class TestTheFloorStillHolds:
    def test_a_short_series_is_never_fitted(self, short_frame, contract):
        """The refusal is the point. A band drawn around seventeen points would
        be a confident statement about a shape that cannot be estimated."""
        with pytest.raises(ValueError, match="at least"):
            decompose_for(short_frame, contract)


class TestWhatIsSaidInstead:
    @pytest.fixture
    def sparse(self, short_frame, contract):
        return _sparse_series(
            short_frame, contract, "need at least 60 days, got 17",
            region="West", frm=None, to=None,
        )

    def test_it_is_a_verdict_rather_than_an_error(self, sparse):
        assert sparse["verdict"] == "sparse_history"

    def test_the_level_and_direction_survive(self, sparse):
        assert sparse["sparse"]["observations"] == 17
        assert sparse["sparse"]["first"] is not None
        assert sparse["sparse"]["change_pct"] is not None
        assert len(sparse["observed"]) == 17

    @pytest.mark.invariant
    def test_nothing_that_needs_a_seasonality_is_reported(self, sparse):
        """Every one of these would require the shape the series cannot support.

        This is the assertion that matters: a sparse verdict that still flagged
        anomalies would be the confident answer the floor exists to prevent,
        wearing a caveat.
        """
        assert sparse["expected"] is None
        assert sparse["anomalies"] == []
        assert "band_low" not in sparse
        assert "robust_z" not in sparse

    def test_the_reader_is_told_what_cannot_be_said_and_what_to_do(self, sparse):
        detail = sparse["sparse"]
        assert "seasonal" in detail["what_cannot"]
        assert "nothing is flagged" in detail["what_cannot"].lower()
        assert detail["next_check"]
        assert "peer" in detail["next_check"]

    def test_an_empty_series_does_not_divide_by_zero(self, contract):
        empty = pd.DataFrame({"d": pd.to_datetime([]), "value": []})
        out = _sparse_series(empty, contract, "no data", None, None, None)
        assert out["sparse"]["change_pct"] is None
        assert out["observed"] == []
