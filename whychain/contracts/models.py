"""KPI semantic contracts.

A contract is not documentation. One file drives four things: the SQL that
computes the metric, the filter that enforces entitlement, the threshold that
decides whether a movement is worth reporting, and the owner an action is
routed to. Change the file and all four change.

Validation here is deliberately strict. A contract error surfaces as a load
failure at startup, not as a wrong diagnosis in front of a reader.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Coverage(StrEnum):
    """How much of a process's signal consumption we could establish.

    UNKNOWN is not a failure state — it is the honest answer when no process
    document exists, and it stops Answer 2 asserting a gap from absence of
    evidence (see D-005).
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Grain(BaseModel):
    """The level of detail one row represents."""

    time: str  # hour | day | week
    dims: tuple[str, ...]


class Driver(BaseModel):
    """Something that can move the metric.

    `controllable_lever` is what separates a driver you can act on from one you
    can only observe. Weather moves revenue; nobody has a weather lever.
    """

    id: str
    source: str
    controllable_lever: str | None = None
    owner_role: str | None = None
    elasticity_prior: float | None = None

    @model_validator(mode="after")
    def _controllable_drivers_need_an_owner(self) -> Driver:
        # Action assembly routes a recommendation to an owner. A lever with
        # nobody accountable produces an action that cannot be actioned.
        if self.controllable_lever is not None and self.owner_role is None:
            raise ValueError(
                f"driver {self.id!r} has lever {self.controllable_lever!r} but no owner_role; "
                "an action nobody owns cannot be recommended"
            )
        return self


class Materiality(BaseModel):
    """Both tests must pass before a movement is worth an analyst's attention.

    Statistical significance alone surfaces clean but trivial movements; rupee
    impact alone surfaces noise that happens to be large.
    """

    min_abs_robust_z: float = Field(gt=0)
    min_abs_delta_inr: float = Field(gt=0)


class AccessPolicy(BaseModel):
    """Entitlement, enforced at projection — never by asking a model nicely.

    `row_filter` is a SQL fragment with named bindings resolved from the
    requester's entitlements. `domain_restriction` names classes of data that
    must never reach a prompt at all.
    """

    row_filter: str | None = None
    column_masks: tuple[str, ...] = ()
    domain_restriction: tuple[str, ...] = ()


class ExtractedSignal(BaseModel):
    """A signal a process consumes, with the span in the SOP that says so."""

    signal: str
    span: tuple[int, int]

    @model_validator(mode="after")
    def _span_is_ordered(self) -> ExtractedSignal:
        if self.span[0] >= self.span[1]:
            raise ValueError(f"span {self.span} is empty or inverted")
        return self


class SignalsConsumed(BaseModel):
    """Which signals this KPI's planning process actually ingests.

    Derived at contract registration by reading a real SOP, never hand-written —
    otherwise Answer 2 reduces to declaring the gap we then discover (D-005).
    Every entry keeps a span back into the source document so the finding can be
    shown rather than asserted.
    """

    derived_from: str | None = None
    extracted: tuple[ExtractedSignal, ...] = ()
    extracted_at: datetime | None = None
    coverage: Coverage = Coverage.UNKNOWN

    @model_validator(mode="after")
    def _claims_need_a_source(self) -> SignalsConsumed:
        if self.coverage is not Coverage.UNKNOWN and self.derived_from is None:
            raise ValueError(
                f"coverage is {self.coverage!r} but no source document is recorded; "
                "signal consumption must be evidenced, not asserted"
            )
        if self.extracted and self.derived_from is None:
            raise ValueError("extracted signals require the SOP they came from")
        return self

    @property
    def signal_ids(self) -> frozenset[str]:
        return frozenset(s.signal for s in self.extracted)


class Calculation(BaseModel):
    canonical_sql: str
    dialect_targets: tuple[str, ...] = ("duckdb",)

    @model_validator(mode="after")
    def _runnable_locally(self) -> Calculation:
        # The engine executes DuckDB. Other dialects are declared for portability
        # but are not compiled — see D-002 and the README's roadmap note.
        if "duckdb" not in self.dialect_targets:
            raise ValueError("dialect_targets must include 'duckdb', the execution engine")
        return self


class Lineage(BaseModel):
    upstream: tuple[str, ...]
    transforms: tuple[str, ...] = ()


class KPIContract(BaseModel):
    """One metric's complete governed definition."""

    model_config = {"frozen": True}

    kpi_id: str
    version: int = Field(ge=1)
    owner_role: str
    definition: str
    calculation: Calculation
    grain: Grain
    calendar: str = "gregorian"
    parents: tuple[str, ...] = ()
    children: tuple[str, ...] = ()
    dimensions: tuple[str, ...]
    drivers: tuple[Driver, ...]
    materiality: Materiality
    freshness_sla: dict[str, timedelta]
    access_policy: AccessPolicy = AccessPolicy()
    signals_consumed: SignalsConsumed = SignalsConsumed()
    lineage: Lineage

    @model_validator(mode="after")
    def _every_driver_source_has_an_sla(self) -> KPIContract:
        # Freshness gates confidence. A driver whose source has no SLA cannot be
        # assessed for staleness, so a stale input would pass silently.
        missing = sorted({d.source for d in self.drivers} - set(self.freshness_sla))
        if missing:
            raise ValueError(
                f"{self.kpi_id}: drivers reference sources with no freshness SLA: {missing}"
            )
        return self

    @model_validator(mode="after")
    def _grain_dims_are_declared(self) -> KPIContract:
        undeclared = sorted(set(self.grain.dims) - set(self.dimensions))
        if undeclared:
            raise ValueError(
                f"{self.kpi_id}: grain references undeclared dimensions: {undeclared}"
            )
        return self

    @model_validator(mode="after")
    def _driver_ids_are_unique(self) -> KPIContract:
        seen = [d.id for d in self.drivers]
        dupes = sorted({i for i in seen if seen.count(i) > 1})
        if dupes:
            raise ValueError(f"{self.kpi_id}: duplicate driver ids: {dupes}")
        return self

    def driver(self, driver_id: str) -> Driver:
        for d in self.drivers:
            if d.id == driver_id:
                return d
        raise KeyError(f"{self.kpi_id} has no driver {driver_id!r}")

    def controllable_drivers(self) -> tuple[Driver, ...]:
        return tuple(d for d in self.drivers if d.controllable_lever is not None)
