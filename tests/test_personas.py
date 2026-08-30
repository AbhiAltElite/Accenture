"""Persona projection and entitlement.

The invariant these protect is the one that makes personas worth having: the
evidence is the same for everybody and only the projection differs. A persona
that changed a cause, a number or a confidence would be a different diagnosis
wearing a label, which is the failure the feature exists to avoid.
"""

from __future__ import annotations

import copy

import pytest

from whychain.personas import Persona, project

pytestmark = pytest.mark.invariant


def _result() -> dict:
    """An analyst-shaped diagnosis with one controllable and one uncontrollable
    cause, in two different regions."""
    return {
        "kpi_id": "net_revenue",
        "run_id": "run-test",
        "region": "West",
        "verdict": "explained",
        "window": {"from": "2026-08-13", "to": "2026-08-16"},
        "movement": {"total_change": -35323.22, "explained": -35323.22},
        "confidence": {
            "score": 0.86, "band": "high",
            "components": [{"name": "coverage", "value": 1.0, "detail": "all of it"}],
            "reasons": [],
        },
        "verified": [
            {
                "candidate_id": "rel-4.05", "description": "Release broke checkout",
                "contribution": -26186.97, "exposed_regions": ["West"],
                "scope": {"channel": "app"},
                "tests": [{"name": "placebo", "outcome": "pass", "detail": "..."}],
            },
            {
                "candidate_id": "wx-mumbai", "description": "Heavy rainfall",
                "contribution": -15943.19, "exposed_regions": ["West"],
                "scope": {},
                "tests": [{"name": "placebo", "outcome": "pass", "detail": "..."}],
            },
        ],
        "decisions": [
            {
                "candidate_id": "rel-4.05", "cause": "Release broke checkout",
                "driver": "release_quality", "lever": "release_rollback",
                "owner": "ecommerce_lead", "controllable": True,
                "action": "Apply release rollback for channel app",
                "measured_loss_inr_per_day": 26186.97,
                "expected_recovery_inr_per_day": 23568.27,
                "recovery_basis": "90% of measured", "confidence_band": "high",
                "monitoring": {"watch": "w", "threshold": "t", "window": "d",
                               "route_to": "ecommerce_lead"},
                "approval": {"assigned_to": "ecommerce_lead", "status": "awaiting_approval"},
                "caveats": [],
            },
            {
                "candidate_id": "wx-mumbai", "cause": "Heavy rainfall",
                "driver": "severe_weather", "lever": None, "owner": None,
                "controllable": False, "action": "No action: no lever.",
                "measured_loss_inr_per_day": 15943.19,
                "expected_recovery_inr_per_day": None,
                "recovery_basis": "not computed", "confidence_band": "high",
                "monitoring": {"watch": "imd", "threshold": "amber", "window": "7d",
                               "route_to": "finance_director"},
                "approval": None, "caveats": ["observable, not controllable"],
            },
        ],
        "telemetry": {"totals": {"model_calls": 0}},
    }


def test_projection_never_mutates_the_evidence():
    """A projection selects. It must not touch what it was given."""
    result = _result()
    before = copy.deepcopy(result)
    for persona in Persona:
        project(result, persona)
    assert result == before


def test_every_persona_reports_the_same_movement_and_confidence():
    """The numbers are identical; only what is rendered differs.

    A CFO and an analyst disagreeing about the size of the movement, or about how
    confident the engine is, would mean the persona had changed the finding.
    """
    result = _result()
    views = {p: project(result, p) for p in Persona}

    movements = {p: v["movement"]["total_change"] for p, v in views.items()}
    assert len(set(movements.values())) == 1, movements

    bands = {
        Persona.CFO: views[Persona.CFO]["headline"]["confidence"],
        Persona.OPS: views[Persona.OPS]["confidence"],
        Persona.ANALYST: views[Persona.ANALYST]["confidence"]["band"],
    }
    assert len(set(bands.values())) == 1, bands


def test_personas_differ_structurally_not_only_in_wording():
    """Different fields present, not the same fields reworded."""
    result = _result()
    cfo = project(result, Persona.CFO)
    ops = project(result, Persona.OPS)

    assert "decision" in cfo and "my_actions" not in cfo
    assert "my_actions" in ops and "decision" not in ops
    # The CFO is asked to back one call, not to choose from a list.
    assert isinstance(cfo["decision"], dict)


def test_withholding_is_declared_rather_than_silent():
    result = _result()
    cfo = project(result, Persona.CFO)
    assert "rejected candidates" in cfo["withheld"]
    assert "causal test detail" in cfo["withheld"]
    # An analyst is withheld nothing, and says so as an empty list rather than
    # by omitting the key.
    assert project(result, Persona.ANALYST)["withheld"] == []


def test_ops_sees_only_levers_it_can_pull_but_still_learns_of_the_rest():
    """Filtering to owned levers must not hide that something else moved."""
    ops = project(_result(), Persona.OPS)
    assert [a["lever"] for a in ops["my_actions"]] == ["release_rollback"]
    assert len(ops["watch_only"]) == 1
    assert ops["watch_only"][0]["monitoring"]["watch"] == "imd"


def test_entitlement_removes_out_of_scope_causes():
    """Rows outside scope are gone from the projection, not merely unrendered."""
    ops = project(_result(), Persona.OPS, entitled_regions=("East",))
    assert ops["causes"] == []
    assert ops["my_actions"] == []


def test_entitlement_announces_what_it_withheld_and_where_to_escalate():
    """Silently dropping the dominant cause would leave the reader with a
    diagnosis that excluded the thing responsible, and no way to know.

    This test previously asserted the *size* was named -- "including one
    accounting for 26,187 rupees per day" -- on the reasoning that a reader must
    be able to tell a material omission from an immaterial one. The reasoning
    holds; the implementation of it did not. That figure is the contribution of a
    slice the reader is not entitled to see, which is the exact quantity the
    entitlement exists to protect, and because the notice is produced on demand a
    reader entitled to one region could recover every other region's contribution
    by asking about each in turn.

    Existence and materiality are what the reader needs in order not to act on a
    partial picture, and neither of them requires the number.
    """
    ops = project(_result(), Persona.OPS, entitled_regions=("East",))
    notice = ops["entitlement"]["notice"]
    assert "outside your entitlement scope" in notice
    assert "material" in notice                     # that it matters, not by how much
    assert "26,187" not in notice and "26187" not in notice
    assert "Release broke checkout" not in notice
    assert ops["entitlement"]["withheld_count"] >= 1
    assert ops["entitlement"]["escalate_to"] == "finance_director"


def test_no_entitlement_declared_means_unrestricted():
    ops = project(_result(), Persona.OPS)
    assert len(ops["causes"]) == 2
    assert "notice" not in ops["entitlement"]


def test_cfo_outlook_separates_recoverable_from_merely_observable():
    cfo = project(_result(), Persona.CFO)
    outlook = cfo["recovery_outlook"]
    assert outlook["recoverable_inr_per_day"] == pytest.approx(23568.27)
    # The weather loss is real and is not recoverable; it must not be quietly
    # folded into the number a CFO reads as "what we get back".
    assert outlook["not_actionable_inr_per_day"] == pytest.approx(15943.19)
