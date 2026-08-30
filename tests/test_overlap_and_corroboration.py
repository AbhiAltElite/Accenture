"""Four defects found by reading the console output against its own arithmetic.

Each of these produced a plausible screen. That is what makes them worth a
regression test: nothing crashed, no test failed, and the number on the page was
simply wrong or the sentence beside it contradicted itself.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from whychain.confidence import Band, score
from whychain.confidence.coverage import explained_movement
from whychain.confidence.score import MIN_COVERAGE
from whychain.corroborate import RETAIL_CORPUS as RETAIL
from whychain.corroborate.pipeline import corroborate, quarantine
from whychain.evidence import ClaimState, Freshness
from whychain.narrate.validate import _NUMERAL
from whychain.verify.candidates import _identifier
from whychain.verify.tests import Candidate
from whychain.verticals.petroleum import CORPUS as PETROLEUM
from whychain.verticals.power import CORPUS as POWER


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


def verified(name="c1", effect=-0.30, placebo=0.08):
    return FakeVerification(
        FakeCandidate(name), ClaimState.VERIFIED, effect,
        results=(FakeTest("placebo", placebo),),
    )


def fresh() -> dict[str, Freshness]:
    now = datetime(2026, 8, 20, 12, tzinfo=UTC)
    return {"s": Freshness(source_id="s", as_of=now - timedelta(hours=1),
                           observed_at=now, sla=timedelta(hours=6))}


class TestOverExplanationIsNotPerfectCoverage:
    """Three causes summing to 188% of a fall was scoring full marks.

    The clamp was right and the silence was not: coverage is the largest single
    component of the score, and it was paying full credit in precisely the case
    where the split between the causes cannot be established.
    """

    def test_the_overlap_ratio_survives_the_clamp(self):
        panel = pd.DataFrame({
            "d": pd.to_datetime(["2026-08-01"] * 4),
            "region": ["West"] * 4,
            "channel": [None] * 4, "device": [None] * 4, "category": [None] * 4,
            "revenue": [1000.0] * 4,
        })
        total, per_cause, overlap = explained_movement(
            [], panel, date(2026, 8, 15), date(2026, 8, 18),
            total_movement=-1000.0,
        )
        assert overlap == 1.0, "no causes cannot overlap"
        assert per_cause == {}
        assert total == 0.0

    def test_coverage_is_discounted_by_the_overlap(self):
        clean = score([verified()], explained=-1000.0, total_movement=-1000.0,
                      supporting_documents=3, sources=fresh())
        overlapping = score([verified()], explained=-1000.0, total_movement=-1000.0,
                            supporting_documents=3, sources=fresh(), overlap=1.883)
        assert clean.explain()["coverage"] == pytest.approx(1.0)
        assert overlapping.explain()["coverage"] == pytest.approx(1 / 1.883, abs=1e-3)
        assert overlapping.score < clean.score

    def test_the_reader_is_told_rather_than_only_scored(self):
        c = score([verified()], explained=-1000.0, total_movement=-1000.0,
                  supporting_documents=3, sources=fresh(), overlap=1.883)
        assert any("overlap" in x for x in c.caveats)
        assert "188%" in c.components[0].detail

    def test_a_caveat_is_not_an_abstention(self):
        """A cause carrying most of a fall on its own is still worth naming."""
        c = score([verified()], explained=-1000.0, total_movement=-1000.0,
                  supporting_documents=3, sources=fresh(), overlap=1.2)
        assert c.band is not Band.UNKNOWN
        assert c.reasons == ()
        assert c.caveats

    def test_overlap_never_moves_the_abstention_boundary(self):
        """The discount is priced into the score and kept out of the gate.

        Letting it cross MIN_COVERAGE would change when the engine refuses
        without anyone choosing to change it. Measured, that cost 16 abstentions
        and took their precision from 85.7% to 51.4%.
        """
        severe = score([verified()], explained=-1000.0, total_movement=-1000.0,
                       supporting_documents=3, sources=fresh(), overlap=3.0)
        assert severe.explain()["coverage"] < MIN_COVERAGE
        assert severe.band is not Band.UNKNOWN, "overlap is not a refusal"
        assert not any("account for only" in r for r in severe.reasons)

    def test_genuinely_thin_coverage_still_abstains(self):
        """The gate reads undiscounted coverage, and still closes."""
        c = score([verified()], explained=-200.0, total_movement=-1000.0,
                  supporting_documents=3, sources=fresh())
        assert c.band is Band.UNKNOWN


class TestCorroborationCanActuallyBeFound:
    """`related_issues[residual] = ()` made corroboration structurally impossible.

    An empty expectation is not "nothing corroborates this". It discards every
    retrieved document before it is read, so the answer is the same whether the
    record is silent or full. Every externally-caused event in petroleum and
    power took that path, because an operational note and the complaint it
    produces are written in different registers.
    """

    @pytest.mark.parametrize("corpus", [RETAIL, PETROLEUM, POWER])
    def test_an_unrecognised_subject_expects_something(self, corpus):
        expected = corpus.expected_for("a subject no vocabulary declares")
        assert expected, "an empty expectation discards the whole retrieved set"
        assert corpus.vocabulary.residual_issue not in expected, (
            "a ticket the vocabulary cannot read is not support for anything"
        )

    @pytest.mark.parametrize("corpus", [RETAIL, PETROLEUM, POWER])
    def test_a_recognised_subject_still_narrows(self, corpus):
        """The fallback must not become a bypass: a known subject keeps its map."""
        for subject, related in corpus.related_issues.items():
            if related:
                assert corpus.expected_for(subject) == related

    def test_the_turnaround_note_classifies_as_a_shortage(self):
        """The operational register, which the complaint vocabulary did not cover."""
        extractor = PETROLEUM.extractor()
        note = ("TA-4411: Turnaround at the West refinery extended by nine days; "
                "downstream allocation reduced to 55 per cent of indent")
        got = extractor.extract([quarantine("c", note)])
        assert got and got[0].issue != PETROLEUM.vocabulary.residual_issue

    def test_dealer_complaints_corroborate_a_refinery_turnaround(self):
        """The tickets were always in the retrieved set; nothing read them."""
        documents = pd.DataFrame({
            "doc_id": ["TK1", "TK2", "TK3"],
            "doc_type": ["support_ticket"] * 3,
            "region": ["West"] * 3,
            "ts": pd.to_datetime(
                ["2026-08-14", "2026-08-15", "2026-08-16"]
            ).tz_localize(UTC),
            "text": [
                "no stock at the depot since Monday, allocation cut to half",
                "Supply delayed again, indent placed Tuesday and nothing yet.",
                "Third day with no delivery, tank empty and customers waiting.",
            ],
        })
        candidate = Candidate(
            candidate_id="TA-4411", kind="release_log",
            start=date(2026, 8, 13), end=date(2026, 8, 22),
            exposed_regions=("West",),
            description=("TA-4411: Turnaround at the West refinery extended by "
                         "nine days; downstream allocation reduced to 55 per "
                         "cent of indent"),
        )
        result = corroborate(candidate, documents, corpus=PETROLEUM)
        assert result.support_count > 0, "the record describes this at length"


class TestTheIdentifierIsTheReference:
    """`Operations circular OC-2026-14: ...` was read as the candidate `Operations`.

    Two costs, and the collision is the worse one: every circular in the corpus
    became the same candidate.
    """

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("TA-4411: Turnaround at the West refinery extended", "TA-4411"),
            ("Operations circular OC-2026-14: unit returned to service", "OC-2026-14"),
            ("Despatch circular DC-2026-31: South unit synchronised", "DC-2026-31"),
            ("rel-4.05: Release 4.05 broke card entry", "rel-4.05"),
            ("TO-2026-19: Commission tariff order takes effect", "TO-2026-19"),
        ],
    )
    def test_the_reference_is_taken_from_the_note(self, text, expected):
        assert _identifier(text, "D1") == expected

    def test_distinct_circulars_stay_distinct(self):
        a = _identifier("Operations circular OC-2026-14: allocation restored", "D1")
        b = _identifier("Operations circular OC-2026-22: allocation revised", "D2")
        assert a != b


class TestNumeralsSurviveTheirPunctuation:
    """A figure followed by a comma scanned as a numeral that cited no fact."""

    def test_a_trailing_comma_is_not_part_of_the_figure(self):
        assert _NUMERAL.findall("accounts for ₹35,323, which is all of it") == ["₹35,323"]

    def test_separators_inside_a_figure_are_kept(self):
        assert "1,234,567.89" in _NUMERAL.findall("1,234,567.89 total")[0]
