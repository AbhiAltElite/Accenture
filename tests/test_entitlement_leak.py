"""Row-level entitlement, tested at the surface a reader actually receives.

These exist because the entitlement scenario passed every check it had while
leaking. `scripts/audit.py` asserted that entitlement filters in SQL before any
projection, and it does -- on `kpi_series`, which the diagnosis path does not
use. The projection was therefore the only guard on that path, and it had a hole
in it for the default persona.

The rule these encode: **no surface reaching the reader may name a cause outside
their entitlement.** Not the structured causes, not the ranking table, not the
set-aside list, and not the narrative -- which is prose written before the
projection runs and which every persona receives.
"""

import pytest

from whychain.personas import Persona, project

WEST_CAUSE = {
    "candidate_id": "rel-4.05",
    "description": "rel-4.05: West-only release regression",
    "contribution": -26239.0,
    "exposed_regions": ["West"],
    "scope": {},
}
SOUTH_CAUSE = {
    "candidate_id": "south-thing",
    "description": "south-thing: a South cause",
    "contribution": -100.0,
    "exposed_regions": ["South"],
    "scope": {},
}


@pytest.fixture
def result():
    return {
        "kpi_id": "net_revenue", "run_id": "r1", "region": "West",
        "verdict": "explained",
        "movement": {"total_change": -28306.0, "explained": -28306.0},
        "confidence": {"band": "high", "score": 0.7},
        "verified": [WEST_CAUSE, SOUTH_CAUSE],
        "decisions": [
            {
                "candidate_id": "rel-4.05", "action": "roll back release 4.05",
                "lever": "release_rollback", "owner": "ecommerce_lead",
                "controllable": True, "expected_recovery_inr_per_day": 18000.0,
                "measured_loss_inr_per_day": -26239.0,
                "cause": "West-only release regression",
                "monitoring": "watch checkout conversion", "approval": {},
            },
            {
                "candidate_id": "south-thing", "action": "reroute South stock",
                "lever": "assortment", "owner": "ops_lead",
                "controllable": True, "expected_recovery_inr_per_day": 40.0,
                "measured_loss_inr_per_day": -100.0,
                "cause": "a South cause",
                "monitoring": "watch South fill rate", "approval": {},
            },
        ],
        "ranking": {"track_a": [
            {"dimension": "region", "slice": "West", "contribution": -26239.0},
            {"dimension": "region", "slice": "South", "contribution": -100.0},
        ]},
        "set_aside": [{"candidate_id": "secret-west", "exposed_regions": ["West"]}],
        "narrative": {
            "sentences": [
                {"text": "Net revenue in West moved -28,307 per day."},
                {"text": "rel-4.05: West-only release regression, -26,239 per day."},
                {"text": "south-thing: a South cause, -100 per day."},
            ],
            "text": "...", "note": "template",
        },
    }


def _rendered(out: dict) -> str:
    """Everything the reader can read, as one string."""
    import json
    return json.dumps(out)


@pytest.mark.invariant
@pytest.mark.parametrize("persona", ["analyst", "cfo", "ops"])
class TestNoPersonaEscapesEntitlement:
    """Persona depth and row entitlement are different things.

    An analyst may see more *detail* than a CFO. Neither may see a region they
    are not entitled to, and the analyst branch used to merge the raw result back
    over the filtered one, restoring every withheld row beneath a notice that
    said they had been withheld.
    """

    def test_a_withheld_cause_is_absent_from_every_surface(self, result, persona):
        out = project(result, Persona(persona), entitled_regions=("South",))
        rendered = _rendered(out)
        assert "rel-4.05" not in rendered
        assert "West-only release regression" not in rendered
        assert "26239" not in rendered.replace(",", "")

    def test_the_entitled_cause_still_arrives(self, result, persona):
        out = project(result, Persona(persona), entitled_regions=("South",))
        assert "south-thing" in _rendered(out)

    def test_the_reader_is_told_something_was_withheld(self, result, persona):
        out = project(result, Persona(persona), entitled_regions=("South",))
        entitlement = out.get("entitlement") or {}
        assert entitlement.get("notice")
        assert entitlement.get("escalate_to")
        assert entitlement.get("withheld_count") == 1

    def test_the_notice_does_not_quote_the_withheld_figure(self, result, persona):
        """A redaction that discloses the redacted value is not a redaction.

        It was also repeatable: a reader entitled to one region could enumerate
        every other region's contribution by asking about each in turn.
        """
        out = project(result, Persona(persona), entitled_regions=("South",))
        notice = (out.get("entitlement") or {}).get("notice", "")
        assert "26239" not in notice.replace(",", "")
        assert "material" in notice

    def test_no_entitlement_declared_withholds_nothing(self, result, persona):
        out = project(result, Persona(persona), entitled_regions=None)
        assert "south-thing" in _rendered(out)
        assert (out.get("entitlement") or {}).get("notice") is None


@pytest.mark.invariant
class TestTheNarrativeIsRedactedToo:
    """Prose written before the projection is still prose the reader receives.

    Filtering the structured causes while shipping a sentence that names them is
    not a redaction; it is a redaction notice printed next to the data.
    """

    def test_the_sentence_naming_a_withheld_cause_is_dropped(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        narrative = out["narrative"]
        assert narrative["redacted_sentences"] == 1
        assert "West-only" not in narrative["text"]
        assert "entitlement" in narrative["note"]

    def test_sentences_in_scope_survive(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        assert "a South cause" in out["narrative"]["text"]

    def test_an_unrestricted_reader_keeps_the_whole_narrative(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=None)
        assert "redacted_sentences" not in out["narrative"]


@pytest.mark.invariant
class TestTheRankingTableIsFiltered:
    """Track A is a contribution table carrying the exact rupee figures the
    entitlement exists to withhold.

    Filtering it by region was the first attempt and it leaked: the table spans
    several dimensions and only one of them is region, so a row labelled
    "channel · store" carried the withheld regional cause's rupees under a
    different label. It is now withheld whole rather than trimmed, which is
    asserted in `TestTheRankingGoesRatherThanBeingTrimmed`.
    """

    def test_the_set_aside_list_is_filtered(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        assert out["set_aside"] == []


@pytest.mark.invariant
class TestEmptyIsNotUnrestricted:
    """`entitled=` is a claim about scope, not the absence of one."""

    def test_an_empty_scope_grants_nothing(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=())
        rendered = _rendered(out)
        assert "rel-4.05" not in rendered
        assert "south-thing" not in rendered

    def test_the_parameter_distinguishes_unset_from_empty(self):
        from api.main import _entitlement_scope
        assert _entitlement_scope(None) is None      # unset: unrestricted
        assert _entitlement_scope("") == ()          # present but empty: nothing
        assert _entitlement_scope("  ") == ()
        assert _entitlement_scope("South") == ("South",)


@pytest.mark.invariant
class TestTheValidationBlockIsRedactedToo:
    """`validation.accepted` is the same sentences again, kept so a reader can
    see which checks passed. Redacting one copy and shipping the other is not a
    redaction -- and this was the copy that survived a live request while
    `redacted_sentences` reported 3."""

    def test_the_second_copy_of_the_sentences_is_redacted(self, result):
        result["narrative"]["validation"] = {
            "accepted": list(result["narrative"]["sentences"]),
            "rejected": [], "checks_run": 4, "clean": True,
        }
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        accepted = out["narrative"]["validation"]["accepted"]
        assert not any("West-only" in s["text"] for s in accepted)
        assert any("a South cause" in s["text"] for s in accepted)


@pytest.mark.invariant
class TestTheRankingGoesRatherThanBeingTrimmed:
    """Track A spans several dimensions and only one is region. A row labelled
    "channel · store" carries the same rupees as the withheld regional cause
    wearing a different label, so trimming by region leaked."""

    def test_the_whole_table_is_withheld_when_anything_is(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        assert out["ranking"]["withheld"] is True
        assert "reason" in out["ranking"]

    def test_an_unrestricted_reader_gets_the_table(self, result):
        out = project(result, Persona.ANALYST, entitled_regions=None)
        assert out["ranking"]["track_a"]


@pytest.mark.invariant
class TestPerCauseAndScenariosAreRedacted:
    """`movement.per_cause` maps candidate id to exact rupee contribution: the
    most machine-readable form of the thing entitlement protects."""

    def test_the_per_cause_map_drops_withheld_causes(self, result):
        result["movement"]["per_cause"] = {"rel-4.05": -26239.0, "south-thing": -100.0}
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        per_cause = out["movement"]["per_cause"]
        assert "rel-4.05" not in per_cause
        assert per_cause["south-thing"] == -100.0
        assert out["movement"]["per_cause_withheld"] == 1

    def test_a_scenario_built_on_a_withheld_cause_is_dropped(self, result):
        result["scenarios"] = [
            {"scenario_id": "rollback", "candidate_id": "rel-4.05",
             "question": "What happens if we roll the release back now?",
             "effect_inr_per_day": 23615.5},
            {"scenario_id": "south", "candidate_id": "south-thing",
             "question": "What if South stock is rerouted?",
             "effect_inr_per_day": 40.0},
        ]
        out = project(result, Persona.ANALYST, entitled_regions=("South",))
        ids = [s["candidate_id"] for s in out["scenarios"]]
        assert ids == ["south-thing"]
