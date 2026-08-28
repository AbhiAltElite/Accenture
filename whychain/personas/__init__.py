"""Who is asking, and what they should be shown.

A persona changes the projection and never the evidence. The same run produces
the same verified causes, the same effect sizes and the same confidence score for
everyone; what differs is which of those fields are rendered and which are
withheld. That is the whole invariant, and there is a test asserting the
underlying evidence is byte-identical across personas.

The distinction matters because the easy version of this feature is a tone
change: the same paragraph, warmer for the CFO. That fools nobody and it is not
what different readers need. A CFO needs the size, the decision and how much to
believe it. A regional manager needs the lever they personally control and who
signs it off. An analyst needs the method behind every number, including the
candidates that were rejected and why.

**Entitlement is enforced here, at the projection, not by asking a model
nicely.** Rows outside a requester's scope are removed before assembly, and when
the removal changes the answer the response says so and names the role to
escalate to. A quiet omission would leave a regional manager reading a diagnosis
that silently excluded the region actually responsible, with no way to tell.
"""

from __future__ import annotations

from enum import StrEnum


class Persona(StrEnum):
    CFO = "cfo"
    OPS = "ops"          # regional or channel manager: owns levers, not methods
    ANALYST = "analyst"  # the console: everything, including the working


# What each persona is shown. Absence is deliberate and is stated in the
# response rather than inferred from a missing key.
WITHHELD: dict[Persona, tuple[str, ...]] = {
    Persona.CFO: (
        "causal test detail", "rejected candidates", "confidence components",
        "evidence citations", "stage telemetry",
    ),
    Persona.OPS: (
        "cross-region comparison", "confidence components", "stage telemetry",
    ),
    Persona.ANALYST: (),
}


def _entitled(regions: tuple[str, ...] | None, region: str | None) -> bool:
    """Whether a slice is inside the requester's scope."""
    if regions is None:          # no entitlement declared: unrestricted
        return True
    if region is None:           # an unsliced figure is national
        return False
    return region in regions


def project(
    result: dict,
    persona: Persona,
    *,
    entitled_regions: tuple[str, ...] | None = None,
    escalation_role: str = "finance_director",
) -> dict:
    """Render one diagnosis for one reader.

    `result` is the full analyst-shaped response. Nothing is recomputed here:
    this selects, and where it removes something it records what and why.
    """
    persona = Persona(persona)
    out: dict = {
        "persona": persona.value,
        "kpi_id": result.get("kpi_id"),
        "run_id": result.get("run_id"),
        "region": result.get("region"),
        "window": result.get("window"),
        "verdict": result.get("verdict"),
        "movement": result.get("movement"),
        "withheld": list(WITHHELD[persona]),
        "entitlement": {"regions": list(entitled_regions) if entitled_regions else None},
        # Every reader gets the scenarios. "What happens if we act" is the CFO's
        # question and the ops manager's question more than it is the analyst's,
        # and each scenario already carries its own assumptions, so it needs no
        # method section to be read honestly.
        "scenarios": result.get("scenarios") or [],
    }

    confidence = result.get("confidence") or {}
    decisions = result.get("decisions") or []
    verified = result.get("verified") or []

    # --- entitlement, applied before anything is assembled -----------------
    withheld_causes = []
    if entitled_regions is not None:
        visible = []
        for v in verified:
            regions = tuple(v.get("exposed_regions") or ())
            if not regions or any(_entitled(entitled_regions, r) for r in regions):
                visible.append(v)
            else:
                withheld_causes.append(v)
        verified = visible
        allowed_ids = {v["candidate_id"] for v in verified}
        decisions = [d for d in decisions if d["candidate_id"] in allowed_ids]

    if withheld_causes:
        # Announced, never silently absent. The largest contributor being out of
        # scope is exactly the case a reader must not mistake for its absence.
        largest = max(
            withheld_causes,
            key=lambda v: abs(v.get("contribution") or 0.0),
        )
        out["entitlement"]["notice"] = (
            f"{len(withheld_causes)} verified cause(s) lie outside your "
            f"entitlement scope and are not shown, including one accounting for "
            f"{abs(largest.get('contribution') or 0):,.0f} rupees per day. "
            f"Escalate to {escalation_role} to see them."
        )
        out["entitlement"]["escalate_to"] = escalation_role

    # --- per-persona projection -------------------------------------------
    if persona is Persona.CFO:
        top = decisions[0] if decisions else None
        out["headline"] = {
            "change_inr_per_day": (result.get("movement") or {}).get("total_change"),
            "explained_inr_per_day": (result.get("movement") or {}).get("explained"),
            "confidence": confidence.get("band"),
        }
        out["causes"] = [
            {"cause": v.get("description"), "contribution": v.get("contribution")}
            for v in verified
        ]
        # One decision, not a list. A CFO is being asked to back a call.
        out["decision"] = None if top is None else {
            "action": top["action"],
            "owner": top["owner"],
            "expected_recovery_inr_per_day": top["expected_recovery_inr_per_day"],
            "controllable": top["controllable"],
            "awaiting_approval_from": (top.get("approval") or {}).get("assigned_to"),
        }
        out["recovery_outlook"] = _outlook(decisions)

    elif persona is Persona.OPS:
        out["causes"] = [
            {
                "cause": v.get("description"),
                "contribution": v.get("contribution"),
                "scope": v.get("scope"),
            }
            for v in verified
        ]
        # Only what this reader can actually do something about, plus the
        # monitoring rule for everything else.
        out["my_actions"] = [
            {
                "action": d["action"], "lever": d["lever"], "owner": d["owner"],
                "expected_recovery_inr_per_day": d["expected_recovery_inr_per_day"],
                "monitoring": d["monitoring"],
                "approval": d.get("approval"),
            }
            for d in decisions if d["controllable"]
        ]
        out["watch_only"] = [
            {"cause": d["cause"], "monitoring": d["monitoring"]}
            for d in decisions if not d["controllable"]
        ]
        out["confidence"] = confidence.get("band")

    else:  # analyst: the full record, nothing removed
        out = {**result, **out}
        out["withheld"] = []

    if result.get("verdict") == "unknown":
        out["abstention"] = result.get("abstention")
    return out


def _outlook(decisions: list[dict]) -> dict:
    """What is recoverable and what is not, in one line of arithmetic."""
    recoverable = sum(
        d["expected_recovery_inr_per_day"] or 0.0
        for d in decisions if d["controllable"]
    )
    unrecoverable = sum(
        d["measured_loss_inr_per_day"] for d in decisions if not d["controllable"]
    )
    return {
        "recoverable_inr_per_day": round(recoverable, 2),
        "not_actionable_inr_per_day": round(unrecoverable, 2),
        "note": (
            "recoverable is the sum of expected recoveries on causes with a "
            "lever; the remainder has no lever and can only be monitored"
        ),
    }


__all__ = ["WITHHELD", "Persona", "project"]
