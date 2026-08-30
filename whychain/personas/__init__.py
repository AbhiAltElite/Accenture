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


def _names_any(row: object, withheld: list[dict]) -> bool:
    """Whether a rendered row mentions a withheld cause anywhere in its text.

    A coarse check on purpose. Scenario questions and monitoring plans are prose
    assembled from the cause's own description, and matching structured ids
    alone let the description through in a sentence.
    """
    import json as _json

    try:
        blob = _json.dumps(row)
    except (TypeError, ValueError):
        return False
    for cause in withheld:
        for field in ("candidate_id", "description"):
            value = cause.get(field)
            if isinstance(value, str) and value.strip():
                label = value.split(":", 1)[-1].strip().rstrip(".")
                if value.strip() in blob or (len(label) > 12 and label in blob):
                    return True
    return False


def _redact_movement(movement: object, withheld_ids: set) -> object:
    """Drop the per-cause split for causes outside scope, and say how many.

    The totals stay: the reader asked about this slice and is entitled to know
    it moved. What they are not entitled to is the attribution of that movement
    to a region they cannot see.
    """
    if not isinstance(movement, dict):
        return movement
    per_cause = movement.get("per_cause")
    if not isinstance(per_cause, dict):
        return movement
    kept = {k: v for k, v in per_cause.items() if k not in withheld_ids}
    if len(kept) == len(per_cause):
        return movement
    out = dict(movement)
    out["per_cause"] = kept
    out["per_cause_withheld"] = len(per_cause) - len(kept)
    return out


def _redact_narrative(narrative: object, withheld: list[dict]) -> object:
    """Drop sentences that describe a cause this reader may not see.

    Matched on the cause's own identifier and on its description, because the
    deterministic writer builds its sentences from exactly those strings. A
    sentence that mentions neither is about the movement itself or about a cause
    still in scope, and is kept.
    """
    if not isinstance(narrative, dict):
        return narrative
    markers: list[str] = []
    for cause in withheld:
        for field in ("candidate_id", "description"):
            value = cause.get(field)
            if isinstance(value, str) and value.strip():
                markers.append(value.strip().rstrip("."))
                # The writer strips the "id: " prefix when it renders a cause,
                # so the bare label has to be matched too.
                if field == "description" and ":" in value:
                    markers.append(value.split(":", 1)[1].strip().rstrip("."))

    def _keep(sentences: object) -> tuple[list, int]:
        kept, removed = [], 0
        for sentence in sentences or []:
            if not isinstance(sentence, dict):
                kept.append(sentence)
                continue
            text = str(sentence.get("text", ""))
            if any(marker and marker in text for marker in markers):
                removed += 1
                continue
            kept.append(sentence)
        return kept, removed

    kept, removed = _keep(narrative.get("sentences"))

    if not removed:
        return narrative

    out = dict(narrative)
    out["sentences"] = kept
    out["text"] = " ".join(str(s.get("text", "")) for s in kept)
    out["redacted_sentences"] = removed

    # `validation.accepted` is the same sentences again, kept so a reader can
    # see the checks that passed. Redacting one copy and shipping the other is
    # not a redaction, and this is the copy that survived: `redacted_sentences`
    # said 3 while the withheld cause sat in the validation block verbatim.
    validation = narrative.get("validation")
    if isinstance(validation, dict):
        accepted, _ = _keep(validation.get("accepted"))
        redacted_validation = dict(validation)
        redacted_validation["accepted"] = accepted
        out["validation"] = redacted_validation
    note = str(out.get("note") or "")
    out["note"] = (
        f"{note} · {removed} sentence(s) removed: they described a cause outside "
        f"this reader's entitlement"
    ).strip(" ·")
    return out


def _in_scope(regions: tuple[str, ...] | None, row: dict) -> bool:
    """Whether a row describing a slice may be shown to this reader.

    A row with no region named is national and is shown; a row naming regions is
    shown only if at least one of them is entitled. Same rule as `_entitled`,
    applied to the row shapes that carry a region list rather than one region.
    """
    if regions is None:
        return True
    exposed = tuple(row.get("exposed_regions") or ())
    if not exposed:
        return True
    return any(_entitled(regions, r) for r in exposed)


def _filter_ranking(ranking: object, regions: tuple[str, ...] | None) -> object:
    """Drop ranked rows naming a region outside scope.

    Track A is a contribution table sliced by dimension, and one of those
    dimensions is region: an unfiltered track A hands a South-only reader the
    exact rupee contribution of every West slice, which is the number the
    entitlement exists to withhold.
    """
    if regions is None or not isinstance(ranking, dict):
        return ranking
    out: dict = {}
    for track, rows in ranking.items():
        if not isinstance(rows, list):
            out[track] = rows
            continue
        out[track] = [
            row for row in rows
            if not isinstance(row, dict)
            or row.get("dimension") != "region"
            or _entitled(regions, row.get("slice") or row.get("value"))
        ]
    return out


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
        # Answer 2 and the narrative go to every reader. Neither is method
        # detail: "the warning existed, the process has no step for it, and
        # this is the third occurrence" is the finding a CFO is being asked to
        # act on, and withholding it from them while showing it to the analyst
        # would leave the decision-maker reading the incident and not the
        # control failure behind it.
        "signal_gap": result.get("signal_gap"),
        "narrative": result.get("narrative"),
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

    # The narrative is prose written from the *full* evidence set, before this
    # function runs, so it names the withheld causes and their figures in plain
    # language. Every persona receives it -- deliberately, it is the finding
    # rather than method detail -- which meant the one surface that reaches every
    # reader was also the one surface entitlement never touched. Filtering the
    # structured causes while shipping a sentence that names them is not a
    # redaction, it is a redaction notice next to the data.
    #
    # Sentences are dropped rather than rewritten. Rewriting would need the
    # writer, the brief and possibly a model call inside a projection that is
    # supposed to select and never recompute; dropping is deterministic, and the
    # notice already tells the reader that something was removed and who to ask.
    if withheld_causes and entitled_regions is not None:
        withheld_ids = {v.get("candidate_id") for v in withheld_causes}
        out["narrative"] = _redact_narrative(
            result.get("narrative"), withheld_causes
        )
        # `movement.per_cause` is a map from candidate id to its exact rupee
        # contribution. It went to every persona untouched, so the one field
        # that spells out precisely what each withheld cause was worth was also
        # the field entitlement never reached -- a strictly worse leak than the
        # structured causes, because it is already keyed and machine-readable.
        out["movement"] = _redact_movement(result.get("movement"), withheld_ids)
        # A scenario is "what if we reversed this cause", so a scenario built on
        # a withheld cause names it and quantifies its reversal. The estimate is
        # the withheld contribution with a recovery share applied to it.
        out["scenarios"] = [
            scenario for scenario in (result.get("scenarios") or [])
            if scenario.get("candidate_id") not in withheld_ids
            and not _names_any(scenario, withheld_causes)
        ]

    if withheld_causes:
        # Announced, never silently absent. The largest contributor being out of
        # scope is exactly the case a reader must not mistake for its absence.
        #
        # What the notice may say is bounded, though, and it used to quote the
        # withheld cause's exact contribution: "including one accounting for
        # 26,239 rupees per day". That is precisely the figure the entitlement
        # exists to withhold, handed over in the sentence explaining that it had
        # been withheld -- and repeatable, so a reader entitled to one region
        # could enumerate every other region's contribution by asking about each
        # in turn. A redaction that discloses the redacted value is not one.
        #
        # Existence and materiality are what the reader actually needs in order
        # not to act on a partial picture, and neither requires the number. The
        # band is the contract's own materiality floor, which the reader can
        # already see, so it discloses nothing new about the slice.
        largest = max(
            withheld_causes,
            key=lambda v: abs(v.get("contribution") or 0.0),
        )
        material = abs(largest.get("contribution") or 0.0) > 0
        out["entitlement"]["notice"] = (
            f"{len(withheld_causes)} verified cause(s) lie outside your "
            f"entitlement scope and are not shown"
            + (
                ", and at least one of them is material to this movement. "
                if material else ". "
            )
            + f"Escalate to {escalation_role} to see them, including their size."
        )
        out["entitlement"]["escalate_to"] = escalation_role
        out["entitlement"]["withheld_count"] = len(withheld_causes)

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
        # The full card for the one decision being backed, so the console can
        # show the lever, the owner and the monitoring rule rather than a
        # summary of them.
        out["decisions"] = decisions[:1]

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
        out["decisions"] = [d for d in decisions if d["controllable"]]

    else:  # analyst: the full working, but not more rows than they may see
        # `out = {**result, **out}` was the defect. `out` carries no "verified"
        # key of its own -- only the CFO and Ops branches set one -- so merging
        # the raw result over it restored the *unfiltered* causes, decisions,
        # ranking and set-aside list, while the entitlement notice assembled
        # above survived and went on claiming they were "not shown". A reader
        # entitled to South alone, asking about West, was handed all three West
        # causes with their rupee contributions beneath a notice saying they had
        # been withheld.
        #
        # Persona depth and row entitlement are different things. An analyst may
        # see more *detail* than a CFO; neither may see a region they are not
        # entitled to. Everything the analyst gets that carries rows is taken
        # from the filtered set, and the two remaining row-bearing keys are
        # filtered here rather than passed through.
        out = {**result, **out}
        out["verified"] = verified
        out["decisions"] = decisions
        out["withheld"] = []
        if entitled_regions is not None:
            allowed = {v["candidate_id"] for v in verified}
            out["set_aside"] = [
                v for v in (result.get("set_aside") or [])
                if _in_scope(entitled_regions, v)
            ]
            # Not filtered row by row. Track A is a contribution table over
            # several dimensions and only one of them is region: a row labelled
            # "channel · store" carries the same rupees as the withheld regional
            # cause, wearing a different label. Dropping the region rows and
            # keeping the rest was the version of this that leaked, so when
            # anything is withheld the table goes rather than being trimmed.
            out["ranking"] = {
                "withheld": True,
                "reason": (
                    "the contribution table is computed across every dimension "
                    "of a panel that includes slices outside your entitlement, "
                    "so it cannot be shown in part"
                ),
            }
            out["candidates"] = [
                c for c in (result.get("candidates") or [])
                if _in_scope(entitled_regions, c)
            ] if result.get("candidates") is not None else result.get("candidates")
            del allowed

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
