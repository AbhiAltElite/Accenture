"""The validator is the load-bearing part of this stage, so it is what is tested.

A writer that produces good prose is pleasant. A validator that lets one
fabricated figure through destroys the product's only claim. Every test here
attacks the validator with output a model plausibly produces, and the
`TestTheGateActuallyCloses` class exists because a check that cannot fail is
not a check.
"""

from __future__ import annotations

import pytest

from whychain.evidence import Unit
from whychain.narrate import (
    Failure,
    Sentence,
    TemplateWriter,
    build_brief,
    format_value,
    narrate,
    validate,
)

RESULT = {
    "run_id": "run-test",
    "kpi_id": "net_revenue",
    "region": "West",
    "verdict": "explained",
    "window": {"from": "2026-08-13", "to": "2026-08-16"},
    "movement": {"total_change": -35323.0, "pct": -0.129, "explained": -35323.0},
    "confidence": {"score": 0.86, "band": "high"},
    "verified": [
        {
            "candidate_id": "rel-4.05",
            "description": "rel-4.05: Release 4.05 broke card entry on the Android checkout flow.",
            "contribution": -26187.0,
            "effect_pct": -0.288,
            "exposed_regions": ["West"],
            "scope": {"channel": "app", "device": "mobile"},
        }
    ],
    "set_aside": [
        {"candidate_id": "promo-xyz", "reason": "ran in three regions that did not move"}
    ],
    "decisions": [
        {
            "action": "Apply release rollback for channel app, device mobile",
            "owner": "ecommerce_lead",
            "expected_recovery_inr_per_day": 23568.0,
        }
    ],
    "signal_gap": {
        "verdict": "no_gap",
        "reason": "No external warning covering this window and slice was published.",
        "best_lead_time_hours": None,
        "recurrence": 0,
    },
}

KNOWN = frozenset({"West", "net_revenue", "ecommerce_lead", "app", "mobile"})


@pytest.fixture
def brief():
    return build_brief(RESULT)


class TestFormatting:
    @pytest.mark.invariant
    def test_percent_and_percentage_point_are_different_claims(self):
        """BUGS.md T-02. 10% to 15% is five percentage points, not five percent."""
        assert format_value(0.05, Unit.PCT) == "5.0%"
        assert format_value(5.0, Unit.PCT_POINT) == "+5.0 percentage points"
        assert format_value(0.05, Unit.PCT) != format_value(5.0, Unit.PCT_POINT)

    def test_a_loss_reads_as_a_loss(self):
        """The sign belongs outside the currency symbol."""
        assert format_value(-39486.0, Unit.INR) == "−₹39,486"
        assert format_value(39486.0, Unit.INR) == "₹39,486"

    def test_absence_is_stated_not_zeroed(self):
        assert format_value(None, Unit.INR) == "not available"


class TestTheBrief:
    def test_a_rejected_candidate_cannot_be_represented_as_a_cause(self, brief):
        """BUGS.md T-12, closed at the source rather than caught downstream."""
        ruled = [f for f in brief.facts if f.kind == "ruled_out"]
        assert ruled and all(f.state == "rejected" for f in ruled)
        assert not any(
            f.kind == "cause" and "promo-xyz" in f.claim for f in brief.facts
        )

    def test_the_addressing_prefix_is_not_prose(self, brief):
        cause = next(f for f in brief.facts if f.kind == "cause")
        assert cause.claim.startswith("verified cause: Release 4.05")

    def test_every_fact_carries_a_display_string(self, brief):
        assert all(f.display for f in brief.facts)


class TestTheGateActuallyCloses:
    """Each of these is output a model realistically produces."""

    def test_an_uncited_sentence_is_rejected(self, brief):
        out = validate([Sentence("Revenue fell sharply.", ())], brief)
        assert not out.accepted
        assert out.rejected[0].failure is Failure.UNBOUND

    def test_a_citation_to_nothing_is_rejected(self, brief):
        out = validate([Sentence("Revenue fell.", ("f-nope",))], brief)
        assert out.rejected[0].failure is Failure.UNBOUND

    @pytest.mark.invariant
    def test_an_invented_figure_is_rejected(self, brief):
        """The whole point. A plausible number nobody computed does not ship."""
        out = validate(
            [Sentence("Revenue fell ₹41,000 per day.", ("f-movement",))], brief
        )
        assert out.rejected[0].failure is Failure.INVENTED_NUMERAL

    @pytest.mark.invariant
    def test_a_figure_from_an_uncited_fact_is_rejected(self, brief):
        """Right number, wrong provenance. Still not bound, so still rejected."""
        out = validate(
            [Sentence("The cause cost −₹26,187 per day.", ("f-movement",))], brief
        )
        assert out.rejected[0].failure is Failure.INVENTED_NUMERAL

    def test_the_correct_figure_from_the_cited_fact_passes(self, brief):
        out = validate(
            [Sentence("The cause cost −₹26,187 per day.", ("f-cause-1",))], brief
        )
        assert out.clean

    def test_an_unknown_role_is_rejected(self, brief):
        out = validate(
            [Sentence("Owned by regional_director.", ("f-movement",))],
            brief, known_entities=KNOWN,
        )
        assert out.rejected[0].failure is Failure.UNKNOWN_ENTITY

    @pytest.mark.invariant
    def test_a_rejected_candidate_stated_as_a_cause_is_rejected(self, brief):
        out = validate(
            [Sentence("The promotion caused the fall.", ("f-ruled-out-1",))], brief
        )
        assert out.rejected[0].failure is Failure.REJECTED_AS_CAUSE

    def test_saying_it_was_ruled_out_is_allowed(self, brief):
        out = validate(
            [Sentence("One candidate was tested and ruled out.", ("f-ruled-out-1",))],
            brief,
        )
        assert out.clean


class TestNoFalsePositives:
    """A validator that cries wolf gets switched off, and protects nothing."""

    def test_dates_are_not_measurements(self, brief):
        out = validate(
            [Sentence("Between 2026-08-13 and 2026-08-16.", ("f-movement",))], brief
        )
        assert out.clean

    def test_a_figure_quoted_from_the_evidence_text_is_not_invented(self, brief):
        """"Release 4.05" carries a number inside the evidence itself."""
        out = validate(
            [Sentence("Release 4.05 broke card entry.", ("f-cause-1",))], brief
        )
        assert out.clean

    def test_a_counted_list_is_not_a_claim(self, brief):
        out = validate(
            [Sentence("1 candidate was ruled out.", ("f-ruled-out-1",))], brief
        )
        assert out.clean


class TestTheWholeStage:
    def test_the_template_writer_passes_its_own_validator(self):
        """Not a tautology, the template builds from `display` strings, which is
        exactly the property the validator asserts about the model's output."""
        story = narrate(RESULT, writer=TemplateWriter(), known_entities=KNOWN)
        assert story.validation.clean, [r.as_dict() for r in story.validation.rejected]
        assert story.sentences and story.model_calls == 0

    def test_a_failing_writer_falls_back_rather_than_failing_the_run(self):
        class Broken:
            def write(self, brief):
                raise RuntimeError("no api key")

        story = narrate(RESULT, writer=Broken(), known_entities=KNOWN)
        assert story.text and story.fell_back
        assert "template used" in story.note

    def test_a_writer_whose_every_sentence_fails_falls_back(self):
        class Fabricator:
            def write(self, brief):
                from whychain.narrate.writer import Written
                return Written(
                    sentences=(Sentence("Revenue fell ₹99,999.", ("f-movement",)),),
                    model_calls=1, tokens_in=10, tokens_out=5, writer="model",
                )

        story = narrate(RESULT, writer=Fabricator(), known_entities=KNOWN)
        assert story.fell_back
        assert story.text
        # The cost of the failed call is still reported. A run that spent money
        # and threw the output away has still spent the money.
        assert story.model_calls == 1

    def test_an_abstention_is_narrated_as_an_abstention(self):
        unknown = {**RESULT, "verdict": "unknown", "verified": [], "decisions": []}
        story = narrate(unknown, writer=TemplateWriter(), known_entities=KNOWN)
        assert "unknown rather than its best guess" in story.text
