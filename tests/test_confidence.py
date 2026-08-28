"""Confidence and abstention: the score is arithmetic, and it can refuse."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from whychain.confidence import Band, abstain, score
from whychain.confidence.score import ABSTAIN_BELOW, MIN_COVERAGE
from whychain.evidence import ClaimState, Freshness


@dataclass
class FakeCandidate:
    candidate_id: str
    exposed_regions: tuple[str, ...] = ("West",)
    description: str = "a cause"
    channel: str | None = None
    device: str | None = None
    category: str | None = None


@dataclass
class FakeTest:
    name: str
    statistic: float | None


@dataclass
class FakeVerification:
    candidate: FakeCandidate
    state: ClaimState
    effect_pct: float | None
    reason: str = "tested"
    results: tuple = ()


def verified(effect=-0.30, placebo=0.08, regions=("West",), name="c1"):
    return FakeVerification(
        FakeCandidate(name, regions), ClaimState.VERIFIED, effect,
        results=(FakeTest("placebo", placebo),),
    )


def fresh(met: bool = True) -> dict[str, Freshness]:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    return {
        "pos_txn": Freshness(
            source_id="pos_txn",
            as_of=now - (timedelta(hours=3) if met else timedelta(hours=30)),
            observed_at=now, sla=timedelta(hours=6),
        )
    }


class TestComponents:
    def test_coverage_is_the_share_explained(self):
        c = score([verified()], explained=-800.0, total_movement=-1000.0,
                  supporting_documents=3, sources=fresh())
        assert c.explain()["coverage"] == pytest.approx(0.8)

    def test_corroboration_saturates(self):
        """The second document matters. The twelfth does not."""
        few = score([verified()], explained=-900.0, total_movement=-1000.0,
                    supporting_documents=3, sources=fresh())
        many = score([verified()], explained=-900.0, total_movement=-1000.0,
                     supporting_documents=40, sources=fresh())
        assert few.explain()["corroboration"] == many.explain()["corroboration"] == 1.0

    def test_no_corroboration_scores_zero_not_neutral(self):
        c = score([verified()], explained=-900.0, total_movement=-1000.0,
                  supporting_documents=0, sources=fresh())
        assert c.explain()["corroboration"] == 0.0

    def test_a_stale_source_reduces_the_score(self):
        good = score([verified()], explained=-900.0, total_movement=-1000.0,
                     supporting_documents=3, sources=fresh(met=True))
        stale = score([verified()], explained=-900.0, total_movement=-1000.0,
                      supporting_documents=3, sources=fresh(met=False))
        assert stale.score < good.score


@pytest.mark.invariant
class TestAbstention:
    """UNKNOWN is an output, not a failure to produce one."""

    def test_nothing_verified_means_unknown(self):
        rejected = FakeVerification(FakeCandidate("c1"), ClaimState.REJECTED, -0.2)
        c = score([rejected], explained=0.0, total_movement=-1000.0,
                  supporting_documents=0, sources=fresh())
        assert c.band is Band.UNKNOWN
        assert "no candidate survived testing" in c.reasons

    def test_low_coverage_forces_abstention_however_good_the_rest(self):
        """Explaining a fifth of a movement very well is still not an explanation."""
        c = score([verified()], explained=-100.0, total_movement=-1000.0,
                  supporting_documents=40, sources=fresh())
        assert c.band is Band.UNKNOWN
        assert any("only" in r for r in c.reasons)

    def test_a_stale_critical_source_forces_abstention(self):
        c = score([verified()], explained=-950.0, total_movement=-1000.0,
                  supporting_documents=5, sources=fresh(met=False))
        assert c.band is Band.UNKNOWN
        assert any("stale" in r for r in c.reasons)

    def test_contradicting_verified_causes_force_abstention(self):
        """Two causes moving the same region in opposite directions cannot both hold."""
        up = verified(effect=+0.30, name="up")
        down = verified(effect=-0.30, name="down")
        c = score([up, down], explained=-900.0, total_movement=-1000.0,
                  supporting_documents=5, sources=fresh())
        assert c.band is Band.UNKNOWN
        assert any("opposite directions" in r for r in c.reasons)

    def test_one_concern_is_enough(self):
        """Confidence is not a vote: a single blocking reason abstains."""
        c = score([verified()], explained=-950.0, total_movement=-1000.0,
                  supporting_documents=10, sources=fresh(met=False))
        assert len(c.reasons) >= 1 and c.band is Band.UNKNOWN

    def test_a_clean_case_does_not_abstain(self):
        c = score([verified()], explained=-950.0, total_movement=-1000.0,
                  supporting_documents=5, sources=fresh())
        assert c.band is Band.HIGH and not c.reasons


class TestAbstentionOutput:
    """An abstention that says only "unknown" wastes the reader's time."""

    def test_carries_what_was_ruled_out_and_why(self):
        rejected = FakeVerification(
            FakeCandidate("promo"), ClaimState.REJECTED, -0.05,
            reason="failed exposure consistency",
        )
        untestable = FakeVerification(
            FakeCandidate("everywhere", ("North", "South", "East", "West")),
            ClaimState.CANNOT_VERIFY, -0.2, reason="could not run difference in differences",
        )
        c = score([rejected, untestable], explained=0.0, total_movement=-1000.0,
                  supporting_documents=0, sources=fresh())
        a = abstain([rejected, untestable], c)

        assert len(a.ruled_out) == 2
        assert {r["candidate"] for r in a.ruled_out} == {"promo", "everywhere"}
        assert all(r["reason"] for r in a.ruled_out), "every rejection states its reason"
        assert a.next_check, "an abstention must name something to do next"

    def test_asks_about_the_untestable_candidate_first(self):
        untestable = FakeVerification(
            FakeCandidate("everywhere", ("North", "South", "East", "West")),
            ClaimState.CANNOT_VERIFY, -0.2, reason="no comparison group",
        )
        c = score([untestable], explained=0.0, total_movement=-1000.0,
                  supporting_documents=0, sources=fresh())
        a = abstain([untestable], c)
        assert a.question and "everywhere" in a.question

    def test_thresholds_are_stated_not_hidden(self):
        assert 0.0 < ABSTAIN_BELOW < 1.0
        assert 0.0 < MIN_COVERAGE < 1.0
