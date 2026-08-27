"""Core evidence types.

Every fact the engine computes becomes an Evidence record. The narrative layer
may only reference evidence by id, and the validator resolves those references
against the store. Nothing reaches a reader that does not exist here first.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator


class MethodClass(StrEnum):
    """How a fact was produced. Drives the LLM vs non-LLM breakdown."""

    DETERMINISTIC = "deterministic"
    STATISTICAL = "statistical"
    CAUSAL = "causal"
    RETRIEVAL = "retrieval"
    LLM = "llm"


class EvidenceKind(StrEnum):
    ANOMALY = "anomaly"
    DECOMPOSITION = "decomposition"
    CONTRIBUTION = "contribution"
    ASSOCIATION = "association"
    CAUSAL_TEST = "causal_test"
    CORROBORATION = "corroboration"
    EXTERNAL_EVENT = "external_event"
    SIGNAL_GAP = "signal_gap"
    FRESHNESS = "freshness"
    PRECEDENT = "precedent"


class ClaimState(StrEnum):
    """Terminal states for a candidate explanation.

    CANNOT_VERIFY and REJECTED are deliberately distinct: a test that could not
    run is not a test that failed. Collapsing them corrupts abstention metrics.
    See DECISIONS.md D-006.
    """

    VERIFIED = "verified"
    HYPOTHESIS = "hypothesis"
    CONTEXTUAL = "contextual"
    REJECTED = "rejected"
    CANNOT_VERIFY = "cannot_verify"


class Unit(StrEnum):
    INR = "INR"
    PCT = "pct"
    PCT_POINT = "pct_point"  # distinct from PCT — see BUGS.md T-02
    COUNT = "count"
    HOURS = "hours"
    RATIO = "ratio"
    NONE = "none"


# Method -> units that method can legitimately produce (BUGS.md T-03).
# A price/volume/mix bridge yields currency, never order counts.
METHOD_UNITS: dict[str, frozenset[Unit]] = {
    "pvm_bridge": frozenset({Unit.INR}),
    "dimensional_contribution": frozenset({Unit.INR, Unit.PCT}),
    "mstl_robust_z": frozenset({Unit.RATIO}),
    "materiality": frozenset({Unit.INR, Unit.RATIO}),
    "ridge": frozenset({Unit.RATIO}),
    "lasso": frozenset({Unit.RATIO}),
    "did": frozenset({Unit.INR, Unit.PCT_POINT}),
    "event_time_isolation": frozenset({Unit.NONE}),
    "placebo": frozenset({Unit.NONE}),
    "retrieval": frozenset({Unit.COUNT, Unit.NONE}),
    "signal_gap": frozenset({Unit.HOURS, Unit.COUNT, Unit.NONE}),
    "freshness": frozenset({Unit.HOURS}),
}


class Provenance(BaseModel):
    """Where a fact came from. This is what the click-through renders."""

    source_id: str
    query: str | None = None
    row_ids: list[str] | None = None
    row_count: int | None = None
    doc_id: str | None = None
    span: tuple[int, int] | None = None
    quote: str | None = None

    @model_validator(mode="after")
    def _require_a_trail(self) -> Provenance:
        if self.query is None and self.doc_id is None:
            raise ValueError(
                "provenance needs either a query (structured) or a doc_id (document); "
                "evidence without a trail cannot be verified by a reader"
            )
        if self.doc_id is not None and self.span is None:
            raise ValueError("document provenance requires a character span")
        return self


class Freshness(BaseModel):
    """When a source was last updated, and whether that breaches its SLA.

    Both timestamps must be timezone-aware. Staleness drives confidence and can
    trigger abstention, so a naive/aware mix here is not a style problem — it
    raises at runtime in the middle of a diagnosis. See BUGS.md T-15.
    """

    source_id: str
    as_of: datetime
    observed_at: datetime
    sla: timedelta

    @model_validator(mode="after")
    def _timestamps_are_aware(self) -> Freshness:
        for name, value in (("as_of", self.as_of), ("observed_at", self.observed_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(
                    f"{name} must be timezone-aware; naive timestamps make lag "
                    "arithmetic silently wrong across sources in different zones"
                )
        return self

    @computed_field
    @property
    def lag(self) -> timedelta:
        return self.observed_at - self.as_of

    @computed_field
    @property
    def sla_met(self) -> bool:
        return self.lag <= self.sla


class Evidence(BaseModel):
    """One computed fact, addressable and traceable.

    Immutable once created: the store is append-only so a diagnosis can be
    replayed exactly.
    """

    model_config = {"frozen": True}

    id: str
    kind: EvidenceKind
    claim: str
    value: float | dict[str, float] | None
    unit: Unit
    method: str
    method_class: MethodClass
    state: ClaimState | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    ci: tuple[float, float] | None = None
    provenance: Provenance
    freshness: Freshness | None = None
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    run_id: str
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unit_matches_method(self) -> Evidence:
        allowed = METHOD_UNITS.get(self.method)
        if allowed is not None and self.unit not in allowed:
            raise ValueError(
                f"method {self.method!r} cannot produce unit {self.unit!r}; "
                f"expected one of {sorted(u.value for u in allowed)}"
            )
        return self

    @model_validator(mode="after")
    def _ci_ordered(self) -> Evidence:
        if self.ci is not None and self.ci[0] > self.ci[1]:
            raise ValueError(f"confidence interval bounds are inverted: {self.ci}")
        return self
