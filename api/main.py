"""HTTP service for the diagnosis console.

Thin by design: it resolves a contract, reads the series through the warehouse,
runs detection, and returns the result. No analysis happens here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import warnings
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from api.middleware import METRICS, EnterpriseMiddleware
from whychain import verticals
from whychain.actions import decision_cards, simulate
from whychain.audit import AuditLog, evidence_fingerprint
from whychain.confidence import abstain, explained_movement, score
from whychain.confidence.calibrate import Calibration
from whychain.contracts import ContractError, ContractRegistry
from whychain.corroborate import corroborate, scan
from whychain.corroborate.model_extract import ModelExtractor
from whychain.corroborate.quarantine import redact
from whychain.corroborate.query import ModelQueryWriter
from whychain.decompose import compute_bridge, contribution_by
from whychain.decompose.bridge import BridgeError
from whychain.decompose.waterfall import cause_waterfall
from whychain.detect import (
    decompose_for,
    festival_factor,
    find_anomalies,
    holidays_for,
    market_for,
    material,
)
from whychain.env import load_env
from whychain.evidence import MethodClass, Unit
from whychain.feedback import FeedbackStore, Judgement, new_feedback, proposals
from whychain.feedback.apply import (
    CONSUMABLE,
    WHY_NOT,
    AppliedStore,
    ApplyRefused,
    apply_proposal,
)
from whychain.identity import DEMO_USERS, Identity, effective_entitlement
from whychain.identity import mode as identity_mode
from whychain.ingest import IngestError, Warehouse
from whychain.ingest import rows as query_rows
from whychain.intent import interpret
from whychain.llm import (
    UNSET,
    Task,
    catalogue,
    default_model,
    describe,
    model_for,
    routing,
)
from whychain.narrate import narrate
from whychain.narrate.nextcheck import propose as propose_next_check
from whychain.narrate.writer import ModelWriter
from whychain.personas import Persona, project
from whychain.rank import rank
from whychain.reconcile import reconcile
from whychain.signalgap import PRECEDENT_LOOKBACK_DAYS, find_gap
from whychain.signalgap.gap import read_signals
from whychain.telemetry import Telemetry
from whychain.text import action_text, label, plain, plural, role, sentence_case
from whychain.verify import (
    filter_relevant,
    from_operations,
    from_promotions,
    touches_scope,
    verify,
)
from whychain.verify.candidates import remediations
from whychain.verify.fishbone import bone_for, bones
from whychain.verify.tests import PLACEBO_WINDOWS
from whychain.verticals import RETAIL_PLAN_COLUMNS, PlanColumns, Vertical

# Before anything reads the environment. `.env.example` documents settings a
# reader reasonably expects a copied `.env` to supply, and nothing loaded it:
# a key written there was silently ignored while the console reported no
# reachable backend. A real environment variable still wins over the file.
load_env()

# statsmodels warns about period length on short slices; the guard is in decompose().
warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")

app = FastAPI(title="WhyChain", docs_url="/api/docs")
# Identity, entitlement from identity, request ids, metrics and security
# headers, for every request. See api/middleware.py.
app.add_middleware(EnterpriseMiddleware)

# One JSON line per request, to stderr, where a container platform collects it.
# `WHYCHAIN_ACCESS_LOG=off` silences it for local work.
if os.environ.get("WHYCHAIN_ACCESS_LOG", "on").lower() != "off":
    _access = logging.getLogger("whychain.access")
    if not _access.handlers:
        _handler = logging.StreamHandler()
        _handler.setFormatter(logging.Formatter("%(message)s"))
        _access.addHandler(_handler)
        _access.setLevel(logging.INFO)
        _access.propagate = False
UI = Path("ui")

_retriever: object | None = None
_retriever_rows: int = 0
_feedback = FeedbackStore()
_applied = AppliedStore()
# Where a demo reset moves the records to. A module setting so a test can point
# it, and the stores, somewhere that is not the presenter's real demo data.
_ARCHIVE = Path("data/archive")
# Keyed on the file's mtime rather than loaded once at import. `make bench`
# refits the curve while the service is running, and a calibration that only
# takes effect after a restart is one that silently disagrees with the report
# sitting next to it.
_calibration_cache: tuple[float | None, Calibration | None] = (None, None)


def calibration() -> Calibration | None:
    """The fitted curve, reloaded when it changes. None is a valid state."""
    global _calibration_cache
    path = Path("data/calibration.json")
    stamp = path.stat().st_mtime if path.exists() else None
    if stamp != _calibration_cache[0]:
        _calibration_cache = (stamp, Calibration.load(path))
    return _calibration_cache[1]


def ticket_retriever(documents: pd.DataFrame):
    """One indexed retriever, reused across requests.

    Fitting TF-IDF over every ticket takes over a second and produces the same
    index every time, because the corpus does not change between requests. It is
    the single slowest thing in a diagnosis and none of it is analysis.
    """
    global _retriever, _retriever_rows
    import hashlib
    from datetime import UTC

    from whychain.corroborate.documents import Document
    from whychain.corroborate.retriever import NumpyRetriever

    tickets = documents[documents["doc_type"] == "support_ticket"]

    # Keyed on the content, not the row count. A count collides whenever one
    # document replaces another, and it carries no entitlement context at all:
    # were this index ever built over a filtered corpus, a later request under a
    # different entitlement would be served the first caller's documents.
    # BUGS.md T-06 calls that a P0, and a row count is exactly the key it warns
    # against.
    digest = hashlib.sha256(
        pd.util.hash_pandas_object(
            tickets[["doc_id", "text"]], index=False
        ).values.tobytes()
    ).hexdigest()
    key = (digest, len(tickets))
    if _retriever is not None and _retriever_rows == key:
        return _retriever

    retriever = NumpyRetriever()
    retriever.index([
        Document(doc_id=str(r["doc_id"]), source_id="voice_ops", text=str(r["text"]),
                 ts=pd.Timestamp(r["ts"]).to_pydatetime().replace(tzinfo=UTC))
        for _, r in tickets.iterrows()
    ])
    _retriever, _retriever_rows = retriever, key
    return retriever


_series_cache: dict[tuple, tuple[tuple, object]] = {}
_registries: dict[str, tuple[tuple, ContractRegistry]] = {}


def _snapshot(vertical: Vertical) -> tuple:
    """What the cached answers are answers about.

    T-06 requires a cache key to carry the data snapshot, the contract version
    and the entitlement context. The first two are here; entitlement is folded in
    by callers that have one, and until a caller does, nothing entitlement-scoped
    may be cached through this. A key that omits any of the three can serve one
    reader another reader's rows, which the same trap calls a P0.
    """
    try:
        stamp = vertical.warehouse.stat().st_mtime_ns
    except OSError:
        stamp = 0
    # Contract *content*, not just id and version. A threshold edited without a
    # version bump is exactly the change a developer makes while iterating, and
    # keying on the version alone meant the console kept serving figures from
    # before the edit with nothing to indicate it.
    # The industry id leads the key. Two verticals have their own warehouse and
    # their own contracts, so a key that omitted it would let a cached
    # `("kpi_series", "net_revenue")` answer a petroleum request -- one metric id
    # standing for two different metrics over two different warehouses. T-06
    # calls a cache key missing its context a P0, and an industry is context in
    # exactly the way an entitlement is.
    return (vertical.id, stamp, _contract_stamp(vertical))


def _cached(vertical: Vertical, key: tuple, build):
    """Memoise against the current snapshot.

    The warehouse is read-only and only `make gen` changes it, so recomputing a
    three-year series on every request re-derives an answer that cannot have
    moved. Entries for a previous snapshot are dropped rather than served.
    """
    snapshot = _snapshot(vertical)
    key = (vertical.id, *key)
    hit = _series_cache.get(key)
    if hit is not None and hit[0] == snapshot:
        return hit[1]
    value = build()
    _series_cache[key] = (snapshot, value)
    return value


def _external_for(ext, candidate, event_end: date) -> list[dict]:
    """Published warnings covering the slice this candidate touched.

    The corroboration section beside this one asks what the *company* wrote
    down, and for a retailer that is usually the whole story: the cause was
    something it did to itself and its own record describes it. For a fuel
    marketer or a generator it is not. Those businesses move because of refinery
    turnarounds, port closures, tariff orders and grid constraints, and the
    record that describes those is external and public: an IMD cyclone warning
    with a named publisher and a measurable lead time, which is already in the
    warehouse and already read by the signal-gap stage.

    Without this the card said "Nothing in the record describes this" for exactly
    the causes the two externally-driven verticals exist to demonstrate, while a
    warning covering that window sat one table away.

    Run-level foreseeability is a different question and is answered separately:
    that asks whether the *planning process* consumed the signal. This asks only
    what was published over this slice, which is context a reader needs to judge
    the cause in front of them.
    """
    if ext is None or getattr(ext, "empty", True):
        return []
    regions = candidate.exposed_regions or ()
    out: list[dict] = []
    seen: set[str] = set()
    for region in (regions or (None,)):
        for signal in read_signals(
            ext, window=(candidate.start, event_end), region=region
        ):
            if signal.signal_id in seen:
                continue
            seen.add(signal.signal_id)
            out.append(
                {
                    "signal_id": signal.signal_id,
                    "signal_type": signal.signal_type,
                    "city": signal.city,
                    "region": signal.region,
                    "severity": signal.severity,
                    "issued_at": signal.issued_at.isoformat(),
                    "valid_from": signal.valid_from.isoformat(),
                    "valid_to": signal.valid_to.isoformat(),
                    "lead_time_hours": round(signal.lead_time_hours, 1),
                    "is_public": bool(signal.is_public),
                    "publisher": signal.publisher,
                    "source_url": signal.source_url,
                }
            )
    # Longest warning first: the one that gave the most notice is the one a
    # reader asks about.
    out.sort(key=lambda r: r["lead_time_hours"], reverse=True)
    return out[:4]


def _entitlement_scope(entitled: str | None) -> tuple[str, ...] | None:
    """The regions a caller may see, distinguishing "unset" from "none at all".

    `None` means no entitlement was declared, which this deployment reads as
    unrestricted -- it has no identity provider, and inventing one would be
    pretending to an authentication story it does not have.

    An empty *string* is different and used to collapse into the same thing:
    `"" or None` is falsy, so a client sending `entitled=` was granted
    everything. That is the wrong way round. A parameter that is present is a
    claim about scope, and a present-but-empty claim is "entitled to nothing",
    which the projection already handles correctly as an empty tuple. Reading it
    as "unrestricted" turned the one input a caller fully controls into a way of
    switching the restriction off.
    """
    if entitled is None:
        return None
    return tuple(r.strip() for r in entitled.split(",") if r.strip())


def _refuse_outside_scope(
    region: str | None, scope: tuple[str, ...] | None, escalate_to: str
) -> None:
    """Refuse a question about a region the reader may not see, before computing.

    One guard for every endpoint that returns a region's figures. It used to be
    written out in `diagnose` and `candidates` only, and the console drew the
    same region's chart from `series` and its bridge from `decomposition`, which
    took no entitlement at all -- so the page announced that nothing had been
    computed for a region while showing its fall, its expected band and its
    price/volume/mix legs underneath the announcement. A restriction enforced on
    one endpoint and not on its neighbour is not enforced.
    """
    if scope is None:
        return
    if region is None and scope:
        return
    if region is not None and region in scope:
        return
    asked = region or "all regions"
    raise HTTPException(
        403,
        {
            "error": "outside your entitlement",
            "requested_region": region,
            "entitled_regions": list(scope),
            "escalate_to": escalate_to,
            "detail": (
                f"You are entitled to "
                f"{', '.join(scope) if scope else 'no regions'} and asked "
                f"about {asked}. Nothing was computed. Escalate to "
                f"{role(escalate_to)} for access."
            ),
        },
    )


def _within_scope(frame: pd.DataFrame, scope: tuple[str, ...] | None) -> pd.DataFrame:
    """Only the rows a reader may see, when no single region was asked for.

    An all-regions total is a disclosure of every region in it, so a scoped
    reader's total is the sum of their own regions and nothing else.
    """
    if scope is None or "region" not in frame.columns:
        return frame
    return frame[frame["region"].isin(scope)]


def _vertical(industry: str | None) -> Vertical:
    """Resolve the industry for this request, defaulting to retail.

    Refuses an unknown id rather than falling back. Serving retail's numbers
    under a petroleum heading because of a typo is the same class of failure as
    a cache key that omits its context: the answer looks right and is about
    something else.
    """
    try:
        return verticals.get(industry)
    except verticals.UnknownVertical as exc:
        raise HTTPException(404, str(exc)) from exc


def registry(industry: str | None = None) -> ContractRegistry:
    """This industry's contracts, reloaded when any of them changes on disk."""
    vertical = _vertical(industry) if not isinstance(industry, Vertical) else industry
    stamp = _contract_stamp(vertical)
    cached = _registries.get(vertical.id)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        loaded = ContractRegistry.from_directory(
            vertical.contracts_dir, overlay=_applied.overlay()
        )
    except ContractError as exc:
        raise HTTPException(500, f"contracts failed to load: {exc}") from exc
    _registries[vertical.id] = (stamp, loaded)
    return loaded


def _contract_stamp(vertical: Vertical) -> tuple:
    # The applied-feedback log is part of what a contract set *is* once an
    # overlay exists, so it belongs in the stamp. Without it an applied proposal
    # would sit in the file and change nothing until the process restarted,
    # which is the same as not having applied it.
    applied = _applied.path
    return (
        tuple(sorted(
            (p.name, p.stat().st_mtime) for p in vertical.contracts_dir.glob("*.yml")
        )),
        applied.stat().st_mtime if applied.exists() else 0,
    )


def warehouse(vertical: Vertical) -> Warehouse:
    """This industry's warehouse, with a readable error when it is not built."""
    try:
        return Warehouse(vertical.warehouse)
    except IngestError as exc:
        raise HTTPException(
            503,
            f"{vertical.label} has no warehouse at {vertical.warehouse}: {exc}. "
            f"Run `make gen-all` to build every industry.",
        ) from exc


@app.get("/api/models")
def models() -> dict:
    """Which model backends exist, which are reachable, and what each implies.

    Exposed so the console can make model choice a visible, switchable thing.
    An engine whose model is set by an environment variable nobody can see is
    one where a governance decision has been made invisibly.
    """
    rows = catalogue()
    active = default_model()
    return {
        "backends": rows,
        "active": describe(active),
        "active_id": active.backend if active else "none",
        "routing": routing(),
        "note": (
            "The engine depends on a protocol, not a vendor. Every backend "
            "produces text that the same deterministic validator then checks, "
            "so switching one changes what is read and written, never what is "
            "computed."
        ),
    }


@app.get("/api/contrast")
def contrast() -> dict:
    """The same case run with the model and without, if it has been captured.

    Exists because the honest default state of this repository is "no model
    backend configured", and a reader in that state has no way to see what the
    model stages do. Absence is reported rather than filled in.
    """
    path = Path("data/demo/contrast.json")
    if not path.exists():
        return {
            "captured": False,
            "note": (
                "No contrast has been captured. Run `make capture-ai` with a "
                "model backend reachable. Nothing is shown in the meantime, "
                "because an artefact describing what a model produced without "
                "running one would be a fabrication."
            ),
        }
    return {"captured": True, **json.loads(path.read_text(encoding="utf-8"))}


@app.get("/api/health")
def health(industry: str | None = Query(None)) -> dict:
    try:
        vertical = _vertical(industry)
        with warehouse(vertical) as wh:
            rows = len(wh.table("pos_txn", limit=1))
        return {
            "status": "ok",
            "industry": vertical.id,
            "warehouse": "connected",
            "contracts": len(registry(vertical)),
            "rows": rows,
        }
    except IngestError as exc:
        return {"status": "degraded", "detail": str(exc)}


@app.get("/api/industries")
def industries() -> dict:
    """Which industries this deployment can be pointed at, and what moves each.

    The switcher reads this. `generated` says whether that industry's warehouse
    has been built, so the console can grey out one that has not rather than
    offering a link that returns a 503.

    The contrast is the point of having more than one. Retail's metrics move
    mostly because of things the business did to itself -- a release, a price
    change, a stockout. The other two move because of things done to them, and
    the same engine has to answer the same eight questions in both cases.
    """
    return {
        "default": verticals.DEFAULT_VERTICAL.id,
        "industries": [
            {
                "id": v.id,
                "label": v.label,
                "tagline": v.tagline,
                "driven_by": v.driven_by,
                "graph_summary": v.graph_summary,
                "headline_kpi": v.headline_kpi,
                "dimensions": v.dimensions,
                "generated": v.is_generated(),
            }
            for v in verticals.VERTICALS
        ],
    }


@app.get("/api/ask")
def ask(
    q: str = Query(..., description="a question in plain language"),
    industry: str | None = Query(None),
    entitled: str | None = Query(None, description="comma-separated regions"),
    backend: str | None = Query(None),
) -> dict:
    """Read a question into a query this engine can run. It does not answer it.

    The model proposes and the registry decides. The enums in the schema are
    built from *this* deployment's contracts and the regions the caller is
    entitled to, so a metric the business does not have, or a region this reader
    may not see, is not something the model can return -- it is unrepresentable
    rather than filtered out afterwards. What comes back is checked again anyway.

    The response is a query and a plain-sentence reading of the question, which
    the console shows the reader *before* running anything. A misreading is then
    visible as a misreading rather than as a confident answer to a question
    nobody asked.
    """
    vertical = _vertical(industry)
    kpi_ids = [c.kpi_id for c in registry(vertical)]

    scope = _entitlement_scope(entitled)
    try:
        with warehouse(vertical) as wh:
            contract = registry(vertical).get(vertical.headline_kpi)
            # Entitlement is applied in SQL here exactly as it is everywhere
            # else, so the regions the model is offered are the regions this
            # reader may actually see. Narrowing the question is the same rule
            # as narrowing the answer, applied one step earlier.
            span = wh.kpi_series(contract, entitled_regions=scope)
    except (IngestError, ContractError) as exc:
        raise HTTPException(503, str(exc)) from exc

    regions = (
        sorted(span["region"].dropna().unique().tolist())
        if "region" in span.columns else []
    )
    days = pd.to_datetime(span["d"]).dt.date if "d" in span.columns else None
    coverage = (min(days), max(days)) if days is not None and len(days) else None
    # Anchored on the data rather than the wall clock. This warehouse ends in
    # August 2026, so "last week" resolved against the real today would ask for
    # a window the warehouse does not hold and every question would return
    # nothing. The last day with data is what "now" means to this deployment.
    today = coverage[1] if coverage else datetime.now(tz=UTC).date()

    intent = interpret(
        q, kpi_ids=kpi_ids, regions=regions, today=today, coverage=coverage,
        backend=model_for(Task.INTENT, backend) if backend else UNSET,
    )
    out = intent.as_dict()
    out["industry"] = vertical.id
    out["available_metrics"] = kpi_ids
    out["available_regions"] = regions
    return out


@app.get("/api/kpis")
def kpis(industry: str | None = Query(None)) -> list[dict]:
    return [
        {
            "kpi_id": c.kpi_id,
            "owner_role": c.owner_role,
            "definition": c.definition.strip(),
            "grain": f"{c.grain.time} by {'/'.join(c.grain.dims)}",
            "parents": list(c.parents),
            "children": list(c.children),
            "dimensions": list(c.dimensions),
            "materiality": {
                "min_abs_robust_z": c.materiality.min_abs_robust_z,
                "min_abs_delta_inr": c.materiality.min_abs_delta_inr,
            },
        }
        for c in registry(_vertical(industry))
    ]


@app.get("/api/overview")
def overview(
    region: str | None = None,
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    days: int = Query(90, ge=30, le=730),
    industry: str | None = Query(None, description="which industry to read"),
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    """Every KPI at once, with its current state and how the graph connects them.

    A dropdown asks the reader to already know which metric moved. The point of a
    KPI graph is that they usually do not, and that a break in one shows up in
    its children.
    """
    vertical = _vertical(industry)
    reg = registry(vertical)
    scope = _entitlement_scope(entitled)
    _refuse_outside_scope(
        region, scope, _contract(vertical.headline_kpi, vertical).owner_role
    )
    # Validated once against the headline contract, then applied per metric.
    # Metrics whose grain lacks a dimension are skipped rather than refused:
    # `on_time_delivery` has no channel, and a channel filter should narrow the
    # metrics it can narrow rather than empty the whole page.
    asked = {d: v for d, v in (("channel", channel), ("device", device),
                               ("category", category)) if v}
    sliced_key = tuple(sorted(asked.items()))
    try:
        with warehouse(vertical) as wh:
            rows = []
            for contract in reg:
                try:
                    raw = _cached(
                        vertical,
                        ("kpi_series", contract.kpi_id),
                        lambda c=contract: wh.kpi_series(c),
                    )
                except IngestError:
                    continue
                raw = _within_scope(raw, scope)
                if region and "region" in raw.columns:
                    raw = raw[raw["region"] == region]
                raw = _narrow(raw, {d: v for d, v in asked.items()
                                    if d in contract.grain.dims})
                if raw.empty:
                    continue

                frame = _roll_up(raw, contract)
                try:
                    # MSTL over three years is the other half of the cost, and it
                    # is a pure function of the frame it is given. How much
                    # history it needs depends on the grain, so the check lives
                    # in decompose and arrives here as a ValueError rather than
                    # as a row count this caller would have to know how to read.
                    d = _cached(
                        vertical,
                        # The scope is part of what was decomposed: an all-regions
                        # total for a reader entitled to South is South's series,
                        # and sharing a key with the unrestricted total would serve
                        # one reader the other's figures.
                        # The slice belongs in the key for the same reason the
                        # scope does: a channel series and a national one are
                        # different answers, and sharing a key serves one under
                        # the other's heading. T-06.
                        ("decompose", contract.kpi_id, region, scope, sliced_key),
                        lambda f=frame, c=contract: decompose_for(f, c),
                    )
                except ValueError:
                    continue
                anomalies = material(
                    find_anomalies(d, contract.materiality.min_abs_robust_z), contract
                )

                tail = min(days, len(frame))
                recent = frame.tail(tail)
                observed = d.observed[-tail:]
                expected = d.expected[-tail:]
                # Counted over the window the reader chose, not over the whole
                # history. These figures sit directly beside a control labelled
                # "Last 90 days"; counting three years under it made the number
                # a reader is most likely to quote the one least likely to be
                # true, and made the control look broken because nothing moved
                # when they changed it.
                since = frame["d"].iloc[-tail] if tail else None
                if since is not None:
                    floor = pd.Timestamp(since).date()
                    anomalies = [a for a in anomalies if a.day >= floor]
                drops = [a for a in anomalies if a.direction == "drop"]
                worst = min(drops, key=lambda a: a.delta) if drops else None

                # A compact shape for a sparkline: enough points to read, few
                # enough to send for five metrics at once.
                step = max(len(observed) // 60, 1)
                rows.append({
                    "kpi_id": contract.kpi_id,
                    "owner_role": contract.owner_role,
                    "grain": f"{contract.grain.time} by {'/'.join(contract.grain.dims)}",
                    # Which of the reader's filters this metric could not take.
                    # `checkout_conversion` is measured by region and device and
                    # has no channel, so a channel filter leaves its count
                    # unchanged. Without saying so the row looks like a control
                    # that does nothing, which is the complaint one level down.
                    "not_narrowed": [d for d in asked if d not in contract.grain.dims],
                    "parents": list(contract.parents),
                    "children": list(contract.children),
                    "unit": contract.unit.value,
                    "latest": round(float(observed[-1]), 2),
                    "expected": round(float(expected[-1]), 2),
                    "period_change": round(
                        float(recent["value"].tail(7).mean()
                              / recent["value"].head(7).mean() - 1), 4
                    ) if recent["value"].head(7).mean() else None,
                    "material_movements": len(anomalies),
                    "material_drops": len(drops),
                    "worst": None if worst is None else {
                        "day": worst.day.isoformat(),
                        "pct": round(worst.observed / worst.expected - 1, 4),
                        "delta": round(worst.delta, 2),
                    },
                    "spark": [round(float(v), 2) for v in observed[::step]],
                    "spark_expected": [round(float(v), 2) for v in expected[::step]],
                })
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    return {"region": region, "days": days, "kpis": rows,
            "roots": reg.roots(),
            # The values each scope control may offer, read from this
            # deployment's own warehouse. The console previously wrote
            # ["North","South","East","West"] into the region select, which is
            # retail's answer given to every industry: T-20, and visibly wrong
            # the moment a second vertical is selected.
            "dimension_values": _dimension_values(
                vertical, _contract(vertical.headline_kpi, vertical), scope)}


@app.get("/api/triage")
def triage(
    limit: int = Query(12, ge=1, le=50),
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    region: str | None = Query(None, description="a single region, or every one"),
    days: int | None = Query(None, ge=30, le=3650,
                             description="how far back to queue findings from"),
    entitled: str | None = Query(None, description="comma-separated regions"),
    industry: str | None = Query(None, description="which industry to read"),
    kpi: str | None = Query(None, description="one metric, or every one"),
    direction: str = Query("drop", pattern="^(drop|spike|both)$",
                           description="falls, rises or both"),
) -> dict:
    """What to look at first, across every KPI and every region at once.

    The console could show what moved once a reader had already chosen a metric
    and a region. That asks them to know the answer to the question they came
    with. Objective 1 of the brief is detection *and prioritisation*, and
    prioritisation is the half that was nowhere on the page.

    Two things make this a ranking rather than a list.

    **Findings are compared in rupees, not in their own units.** A four-point
    fall in checkout conversion and a two-lakh fall in revenue are not otherwise
    comparable, and a queue that sorts within each metric separately is five
    queues. Each contract already declares `value_per_unit_inr` for exactly this
    conversion, because materiality needs it, so the same declaration does the
    ranking. No new assumption is introduced.

    **Consecutive flagged days are one finding.** A five-day regression is one
    thing to look at, and listing it five times would push a larger single-day
    movement off the top of the queue by sheer repetition.

    This is detection, not diagnosis. It says what is worth a question, and the
    diagnosis answers it, which is why every row carries a link rather than a
    cause. Running twenty-five diagnoses to build a landing page would spend a
    reader's first ten seconds on questions they have not asked yet.
    """
    vertical = _vertical(industry)
    reg = registry(vertical)
    scope = _entitlement_scope(entitled)
    # Read from the warehouse rather than written down: "North, South, East,
    # West" is retail's answer, and this queue serves three verticals. T-20.
    regions = list(scope) if scope else _dimension_values(
        vertical, _contract(vertical.headline_kpi, vertical), scope
    ).get("region", [])
    asked = {d: v for d, v in (("channel", channel), ("device", device),
                               ("category", category)) if v}
    sliced_key = tuple(sorted(asked.items()))
    # A region the reader picked narrows the queue; entitlement still bounds it,
    # so asking for a region outside the grant returns nothing rather than
    # widening the scope back out.
    # The choices a filter may offer: bounded by entitlement, never by the
    # filter itself, so picking one region does not remove the others.
    offer = {"regions": list(regions), "metrics": [c.kpi_id for c in reg]}
    if region:
        regions = [r for r in regions if r == region]
    findings: list[dict] = []
    try:
        with warehouse(vertical) as wh:
            for contract in reg:
                if kpi and contract.kpi_id != kpi:
                    continue
                try:
                    raw = _cached(
                        vertical,
                        ("kpi_series", contract.kpi_id),
                        lambda c=contract: wh.kpi_series(c),
                    )
                except IngestError:
                    continue
                if raw.empty:
                    continue

                narrowed = _narrow(raw, {d: v for d, v in asked.items()
                                         if d in contract.grain.dims})
                for region_id in regions:
                    scoped = (
                        narrowed[narrowed["region"] == region_id]
                        if "region" in narrowed.columns else narrowed
                    )
                    if scoped.empty:
                        continue
                    frame = _roll_up(scoped, contract)
                    try:
                        d = _cached(
                            vertical,
                            # T-06 again: the slice is part of what was
                            # decomposed, so it is part of the key.
                            ("decompose", contract.kpi_id, region_id, sliced_key),
                            lambda f=frame, c=contract: decompose_for(f, c),
                        )
                    except ValueError:
                        continue

                    flagged = material(
                        find_anomalies(d, contract.materiality.min_abs_robust_z),
                        contract,
                    )
                    # Falls by default: they are what a reader is asked to
                    # explain. A rise is a movement too, and variance practice
                    # asks why a favourable one happened and whether it lasts.
                    for way in (("drop", "spike") if direction == "both" else (direction,)):
                        moves = sorted((a for a in flagged if a.direction == way), key=lambda a: a.day)
                        findings.extend(_episodes(moves, contract, region_id))
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    # The window the rail is showing. Without it the queue answered over the
    # whole three years while the figures beside it answered over ninety days,
    # and the two disagreed on screen about how much was wrong with the
    # business. "Now" is the last day the warehouse actually holds rather than
    # the wall clock, because the wall clock is not where this data lives and a
    # window measured against it would be empty.
    #
    # Read across every contract, before any filter. It used to be the newest
    # *finding* after the metric and region filters, so "last 90 days" began on
    # 1 Jun for the whole queue and on 18 May for on-time delivery alone: the
    # filter moved the window it was meant to narrow within (B-059).
    if days and findings:
        latest = _latest_day(vertical, reg).isoformat()
        since = (date.fromisoformat(latest) - timedelta(days=days)).isoformat()
        findings = [f for f in findings if f["end"] >= since]

    findings.sort(key=lambda f: f["impact_inr_per_day"], reverse=True)
    findings, folded = _fold_the_graph(findings, reg)
    return {
        "findings": findings[:limit],
        "total": len(findings),
        "folded": folded,
        "region": region,
        "days": days,
        "kpi": kpi,
        "direction": direction,
        "offer": offer,
        "scope": list(scope) if scope else None,
        "basis": (
            "Ranked by rupee impact per day, converted through each contract's "
            "declared value_per_unit_inr so metrics in different units are "
            "comparable. Consecutive flagged days are grouped into one finding, "
            "and a child metric moving in the same region and window as its "
            "parent is folded into the parent rather than queued again. "
            "This is detection and prioritisation; the cause is a diagnosis away."
        ),
    }


def _latest_day(vertical, reg) -> date:
    """The last day this warehouse holds any metric for, whatever is filtered."""
    days: list[date] = []
    with warehouse(vertical) as wh:
        for contract in reg:
            try:
                raw = _cached(vertical, ("kpi_series", contract.kpi_id),
                              lambda c=contract: wh.kpi_series(c))
            except IngestError:
                continue
            column = "h" if "h" in raw.columns else "d"
            if not raw.empty and column in raw.columns:
                days.append(pd.to_datetime(raw[column]).max().date())
    return max(days)


def _overlaps(a: dict, b: dict) -> bool:
    """Whether two findings cover any of the same days."""
    return a["start"] <= b["end"] and b["start"] <= a["end"]


def _ancestry(reg) -> dict[str, set[str]]:
    """Every KPI mapped to all of its ancestors, transitively."""
    out: dict[str, set[str]] = {}

    def walk(kpi_id: str, seen: frozenset[str] = frozenset()) -> set[str]:
        if kpi_id in out:
            return out[kpi_id]
        if kpi_id in seen:                       # the registry rejects cycles;
            return set()                         # this is belt and braces
        parents = set(getattr(reg.get(kpi_id), "parents", ()) or ())
        found = set(parents)
        for parent in parents:
            found |= walk(parent, seen | {kpi_id})
        out[kpi_id] = found
        return found

    for contract in reg:
        walk(contract.kpi_id)
    return out


def _fold_the_graph(findings: list[dict], reg) -> tuple[list[dict], int]:
    """One event, one row, however many metrics it showed up in.

    Revenue is orders times average order value, so a fall in orders and the
    fall in revenue it produces are the same rupees counted twice -- and
    literally twice, because both are priced through their contract's own
    `value_per_unit_inr` back into the same currency. Queued separately they
    took the top two places between them, and the child ranked *above* the
    parent while being the one with no price/volume/mix identity to decompose:
    the first thing a reader saw was a duplicate they could not act on.

    A queue is a claim about what to look at first. Two rows for one event is
    that claim being wrong twice over -- it wastes the top of the list, and it
    inflates the total, which is the number a reader uses to judge how much is
    wrong with the business.

    Which row survives is decided by the graph, never by size. Folding into
    whichever happened to rank higher is how the child won in the first place:
    it is priced through its own `value_per_unit_inr` and can out-total its
    parent, so sorting first and folding second just re-elects the duplicate.
    The parent is the metric the movement is *about*, so the parent keeps the
    row and names the children that corroborate it.

    Nothing is discarded. A child that moved when its parent did not, or in a
    window its parent's movement does not cover, is unrelated to that parent and
    queues on its own -- which is exactly the case where the child is the
    finding.
    """
    ancestry = _ancestry(reg)
    groups: list[list[dict]] = []

    for finding in findings:
        kin = ancestry.get(finding["kpi_id"], set())
        for group in groups:
            # One metric contributes at most one row to an event. Without this,
            # a chain of overlaps absorbs a *second* episode of the same metric
            # through a shared child and folds it into the first -- two separate
            # events reported as one, which is the opposite failure to the one
            # this function exists to fix.
            if finding["kpi_id"] in {m["kpi_id"] for m in group}:
                continue
            if any(
                member["region"] == finding["region"]
                and _overlaps(member, finding)
                and (
                    member["kpi_id"] in kin
                    or finding["kpi_id"] in ancestry.get(member["kpi_id"], set())
                )
                for member in group
            ):
                group.append(finding)
                break
        else:
            groups.append([finding])

    kept: list[dict] = []
    folded = 0
    for group in groups:
        # Closest to a root wins, and rupees break a tie between siblings.
        head = min(
            group,
            key=lambda f: (len(ancestry.get(f["kpi_id"], ())), -f["impact_inr_per_day"]),
        )
        others = [f["kpi_id"] for f in group if f is not head]
        if others:
            head["also_moved"] = sorted(set(others))
            folded += len(others)
        kept.append(head)

    kept.sort(key=lambda f: f["impact_inr_per_day"], reverse=True)
    return kept, folded


# Two flagged days further apart than this are separate events rather than one
# that happens to have a quiet day in the middle.
EPISODE_GAP_DAYS = 2


def _episodes(drops, contract, region: str) -> list[dict]:
    """Group consecutive flagged days into findings, worst day first."""
    out: list[dict] = []
    run: list = []

    def close(run):
        if not run:
            return
        # The largest move in the run's own direction: lowest for a fall,
        # highest for a rise.
        rising = run[0].direction == "spike"
        worst = max(run, key=lambda a: a.delta) if rising else min(run, key=lambda a: a.delta)
        total = sum(abs(a.delta) for a in run)
        out.append({
            "kpi_id": contract.kpi_id,
            "unit": contract.unit.value,
            "owner_role": contract.owner_role,
            "direction": "rise" if rising else "fall",
            "favourable": contract.favourable,
            "region": region,
            "start": run[0].day.isoformat(),
            "end": run[-1].day.isoformat(),
            "days": len(run),
            "worst_day": worst.day.isoformat(),
            "delta": round(float(worst.delta), 4),
            # Derived here rather than carried on the anomaly: the proportional
            # fall against what the day was expected to be, which is the figure
            # a reader compares across metrics of different sizes.
            "pct": (
                round(float(worst.delta) / float(worst.expected), 4)
                if worst.expected else None
            ),
            "robust_z": round(float(worst.robust_z), 2),
            # The number the queue is sorted on, and the only one that is
            # comparable across metrics.
            "impact_inr_per_day": round(
                contract.materiality.business_impact(total / len(run)), 2
            ),
            "diagnosable": contract.decomposition.method == "pvm",
        })

    for anomaly in drops:
        if run and (anomaly.day - run[-1].day).days > EPISODE_GAP_DAYS:
            close(run)
            run = []
        run.append(anomaly)
    close(run)
    return out


@app.get("/api/document/{doc_id}")
def document(
    doc_id: str,
    industry: str | None = Query(None),
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    """The full source record behind a citation.

    A quotation with a character range is only checkable if the reader can open
    the document and see the range in place.
    """
    vertical = _vertical(industry)
    scope = _entitlement_scope(entitled)
    try:
        with warehouse(vertical) as wh:
            docs = wh.table("voice_ops")
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    match = docs[docs["doc_id"] == doc_id]
    if match.empty:
        raise HTTPException(404, f"no document {doc_id}")
    row = match.iloc[0]
    # A record filed against a region is that region's record. Documents filed
    # against every region ("All") are readable by anyone entitled to any.
    doc_region = str(row["region"])
    headline = _contract(vertical.headline_kpi, vertical)
    if doc_region not in ("All", "None", ""):
        _refuse_outside_scope(doc_region, scope, headline.owner_role)
    raw = str(row["text"])
    # Masked for the person reading exactly as it was for the model: the same
    # declared classes, the same patterns. It used to be returned raw, so a
    # phone number the prompt never saw appeared in the evidence drawer, and a
    # citation span measured on the masked text was highlighted on the raw one.
    domains = headline.access_policy.domain_restriction
    text, masked = redact(raw, domains)
    return {
        "doc_id": doc_id,
        "doc_type": str(row["doc_type"]),
        "source_id": "voice_ops",
        "ts": pd.Timestamp(row["ts"]).isoformat(),
        "region": str(row["region"]),
        "text": text,
        "length": len(text),
        # What was scanned for and what was found, so "nothing masked" reads as
        # a result rather than as a check that never ran.
        "personal_data": {"scanned_for": list(domains), "masked": list(masked)},
        # Stated rather than assumed: the reader is being shown untrusted text.
        # Scanned on the original, so a payload next to personal data keeps its flag.
        "injection_flags": list(scan(raw)),
    }


@app.get("/api/series")
def series(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    industry: str | None = Query(None, description="which industry to read"),
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)
    scope = _entitlement_scope(entitled)
    _refuse_outside_scope(region, scope, contract.owner_role)

    try:
        with warehouse(vertical) as wh:
            # Freshness is a clock reading, not a derived series: never cached.
            freshness = wh.freshness(contract)
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc
    frame = _series_frame(vertical, contract, scope, region,
                          _slice_of(contract, channel=channel, device=device, category=category))

    try:
        decomposition = decompose_for(frame, contract)
    except ValueError as exc:
        # A short series is not a bad request. It is the sparse-history case the
        # brief asks for, and a 422 tells the reader they did something wrong
        # rather than telling them what can and cannot be said about a metric
        # that has not existed long enough to have a seasonal shape.
        #
        # What can still be said is said: the level, the direction, and how much
        # history would be needed. What must not be said is anything that
        # depends on a fitted seasonality, so there are no anomalies, no bands
        # and no expected line -- refusing to fit is the finding.
        return _sparse_series(frame, contract, str(exc), region, frm, to)

    anomalies = material(
        find_anomalies(decomposition, contract.materiality.min_abs_robust_z), contract
    )

    days = pd.to_datetime(frame["d"]).dt.date
    window = None
    if frm or to:
        lo = frm or days.min()
        hi = to or days.max()
        keep = (days >= lo) & (days <= hi)
        window = (lo, hi)
    else:
        keep = pd.Series(True, index=days.index)

    idx = keep.to_numpy()
    # Two decimals is right for rupees and destroys a rate: 4.3% conversion and
    # 4.4% both render as 0.04, so the chart becomes a staircase of seven levels
    # and the lower band sits at zero. The precision comes off the unit for the
    # same reason the seasonal period comes off the grain (B-018).
    places = 5 if contract.unit is Unit.RATIO else 2

    def at_precision(values) -> list[float]:
        return [round(float(v), places) for v in values]

    return {
        "kpi_id": contract.kpi_id,
        "slice": {k: v for k, v in
                  (("region", region), ("channel", channel), ("device", device)) if v},
        "unit": contract.unit.value,
        "favourable": contract.favourable,
        # What one point is. Checkout conversion is hourly, so a reader told it
        # is looking at "1,729 days" of it is being told something false about
        # three years of history that does not exist.
        "grain": contract.grain.time,
        "days": [d.isoformat() for d in days[idx]],
        "observed": at_precision(decomposition.observed[idx]),
        "expected": at_precision(decomposition.expected[idx]),
        "band_low": at_precision(decomposition.band_low[idx]),
        "band_high": at_precision(decomposition.band_high[idx]),
        "festival": [round(float(v), 3) for v in decomposition.festival[idx]],
        "robust_z": [round(float(v), 2) for v in decomposition.robust_z[idx]],
        "anomalies": [
            {
                "day": a.day.isoformat(),
                "observed": round(a.observed, places),
                "expected": round(a.expected, places),
                "delta": round(a.delta, places),
                "pct": round(a.observed / a.expected - 1, 4) if a.expected else None,
                "robust_z": round(a.robust_z, 2),
                "direction": a.direction,
            }
            for a in anomalies
            if window is None or window[0] <= a.day <= window[1]
        ],
        "freshness": [
            {
                "source_id": f.source_id,
                "as_of": f.as_of.isoformat(),
                "lag_hours": round(f.lag.total_seconds() / 3600, 1),
                "sla_hours": round(f.sla.total_seconds() / 3600, 1),
                "sla_met": f.sla_met,
            }
            for f in freshness.values()
        ],
        "materiality": {
            "min_abs_robust_z": contract.materiality.min_abs_robust_z,
            "min_abs_delta_inr": contract.materiality.min_abs_delta_inr,
        },
    }


def _sparse_series(
    frame: pd.DataFrame,
    contract,
    reason: str,
    region: str | None,
    frm: date | None,
    to: date | None,
) -> dict:
    """What is honestly available for a metric with too little history.

    Three years of history gives three observations per day-of-year; seventeen
    days gives none at all, and a seasonal component fitted to it is a shape
    invented from noise. So nothing seasonal is reported -- and because
    materiality here is a robust z against a fitted residual, nothing is flagged
    either. A new product with a fortnight of data has no anomalies, and saying
    so is more useful than a confident band drawn around too few points.
    """
    days = pd.to_datetime(frame["d"]).dt.date
    values = frame["value"].astype(float)
    first, last = (float(values.iloc[0]), float(values.iloc[-1])) if len(values) else (0.0, 0.0)
    change = (last / first - 1.0) if first else None
    return {
        "kpi_id": contract.kpi_id,
        "slice": {"region": region},
        "unit": contract.unit.value,
        "grain": contract.grain.time,
        "verdict": "sparse_history",
        "days": [d.isoformat() for d in days],
        "observed": [round(v, 4) for v in values],
        # Deliberately absent: expected, bands, robust z, anomalies. Each would
        # require the seasonality this series cannot support.
        "expected": None,
        "anomalies": [],
        "sparse": {
            "observations": len(frame),
            "reason": reason,
            "first": round(first, 2),
            "last": round(last, 2),
            "change_pct": round(change, 4) if change is not None else None,
            "what_can_be_said": (
                "the level and its direction over the window observed"
            ),
            "what_cannot": (
                "whether any movement is anomalous, because separating a "
                "seasonal shape from noise needs history this metric does not "
                "have yet. No band is drawn and nothing is flagged."
            ),
            "next_check": (
                "compare against a peer slice with established history, or wait "
                "until the series is long enough to fit"
            ),
        },
        "window": {"from": frm.isoformat() if frm else None,
                   "to": to.isoformat() if to else None},
    }


def _series_frame(vertical: Vertical, contract, scope, region: str | None,
                  sliced: dict[str, str]) -> pd.DataFrame:
    """The metric at its grain for one scope: the rows every figure is drawn from.

    One path, shared by the chart and by the query-and-rows view, so the rows a
    reader inspects are the rows the page's figures came from, not a second
    reading that happens to agree.
    """
    try:
        with warehouse(vertical) as wh:
            raw = _cached(vertical, ("kpi_series", contract.kpi_id), lambda: wh.kpi_series(contract))
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc
    raw = _within_scope(raw, scope)
    if region and "region" in raw.columns:
        raw = raw[raw["region"] == region]
    raw = _narrow(raw, sliced)
    if raw.empty:
        raise HTTPException(404, "no data for that slice")
    return _roll_up(raw, contract)


def _roll_up(raw: pd.DataFrame, contract) -> pd.DataFrame:
    """Collapse a sliced series to one value per period, as the contract says.

    Summing a rate produces a number that looks like data and means nothing.
    Averaging one is subtler and worse: it reads as the overall rate while
    weighting every slice equally regardless of size, so a quiet device drags
    the number as hard as the busy one. A ratio is rolled up by re-dividing its
    summed parts, which the contract names.
    """
    time_col = raw.columns[0]
    aggregation = contract.grain.aggregation.value

    if aggregation == "ratio_of_sums":
        num, den = contract.grain.numerator, contract.grain.denominator
        missing = [c for c in (num, den) if c not in raw.columns]
        if missing:
            raise HTTPException(
                500,
                f"{contract.kpi_id} declares ratio_of_sums but its query does not "
                f"emit {missing}; the rate cannot be rolled up without its parts",
            )
        parts = raw.groupby(time_col, as_index=False)[[num, den]].sum()
        parts["value"] = parts[num] / parts[den].replace(0, pd.NA)
        # The denominator travels with the rate. How firm a four per cent is
        # depends entirely on whether it came off fifty sessions or nine
        # hundred, and dropping the count here is what left the detector
        # judging a quiet hour by a busy hour's spread (see B-018).
        frame = parts[[time_col, "value", den]].rename(columns={den: "n"})
    else:
        grouped = raw.groupby(time_col, as_index=False)["value"]
        frame = grouped.mean() if aggregation == "mean" else grouped.sum()

    return frame.rename(columns={time_col: "d"}).sort_values("d").reset_index(drop=True)


def _contract(kpi: str, vertical: Vertical):
    try:
        return registry(vertical).get(kpi)
    except ContractError as exc:
        raise HTTPException(404, str(exc)) from exc


def _already_actioned(card: dict, verifications, documents: pd.DataFrame) -> dict:
    """Mark a card whose lever the record shows was already pulled.

    The West regression's card said "apply release rollback" while the release
    log, dated after the window, says the rollback was applied (B-057). A
    decision a reader is asked to back must not be one that was already taken:
    what is left to decide is whether it worked, so that is what the card says.
    """
    found = next((v.candidate for v in verifications
                  if v.candidate.candidate_id == card.get("candidate_id")), None)
    if found is None or not card.get("controllable"):
        return card
    done = remediations(documents, found.candidate_id, after=found.start)
    return {**card, "already_actioned": done[0] if done else None}


def _skus(panel: pd.DataFrame) -> tuple[str, ...]:
    """The products a note may name: the ones this warehouse actually holds."""
    return tuple(panel["sku"].dropna().unique()) if "sku" in panel.columns else ()


def _lookback(event_start: date, baseline_days: int) -> date:
    """The earliest day a diagnosis of this window actually reads.

    The bridge needs the baseline. Verification reaches further back: each of
    the placebo windows sits a fortnight behind the last, and each carries its
    own baseline. Reading from here covers all of it with a month to spare,
    instead of scanning the whole history to answer a question about a fortnight.
    """
    return event_start - timedelta(
        days=baseline_days * 2 + PLACEBO_WINDOWS * 14 + 30
    )


def _last_recorded(frame: pd.DataFrame | None, column: str) -> date | None:
    """The most recent day a table carries, or None when it carries none."""
    if frame is None or getattr(frame, "empty", True) or column not in frame.columns:
        return None
    stamps = pd.to_datetime(frame[column], errors="coerce", utc=True).dropna()
    return stamps.max().date() if len(stamps) else None


SEVERITY_ORDER = ("green", "yellow", "amber", "orange", "red")


def _severity_rank(severity: str | None) -> int:
    """How serious a warning claims to be. An unrecognised label sorts lowest."""
    try:
        return SEVERITY_ORDER.index(str(severity).strip().lower())
    except ValueError:
        return -1


def _signal_days(signals) -> list[dict]:
    """One marker per day and type, not one per warning.

    A quiet quarter carries 178 separate weather warnings over 90 days, and a
    strip drawn from those is a smear rather than a reading. Folding them to the
    day keeps what a reader is actually asking, which is whether a warning
    existed on that day and how much notice it gave, and moves the individual
    cities into the detail where they belong.

    The **longest** lead time survives the fold, not the average. The question
    behind this strip is whether the movement could have been anticipated, and
    the earliest warning is the one that answers it.
    """
    folded: dict[tuple, dict] = {}
    for signal in signals:
        day = signal.valid_from.date()
        key = (day, signal.signal_type)
        event = folded.setdefault(key, {
            "day": day.isoformat(),
            "kind": "signal",
            "label": signal.signal_type.replace("_", " "),
            "detail": "",
            "count": 0,
            "severity": signal.severity,
            "lead_time_hours": 0.0,
            "publisher": signal.publisher,
            "source_url": signal.source_url,
            "_cities": set(),
            "_regions": set(),
        })
        event["count"] += 1
        event["_cities"].add(str(signal.city))
        event["_regions"].add(str(signal.region))
        if signal.lead_time_hours > event["lead_time_hours"]:
            event["lead_time_hours"] = signal.lead_time_hours
        if _severity_rank(signal.severity) > _severity_rank(event["severity"]):
            event["severity"] = signal.severity

    out = []
    for event in folded.values():
        cities = sorted(event.pop("_cities"))
        regions = sorted(event.pop("_regions"))
        event["regions"] = regions
        event["lead_time_hours"] = round(event["lead_time_hours"], 1)
        shown = ", ".join(cities[:4]) + (f" and {len(cities) - 4} more" if len(cities) > 4 else "")
        event["detail"] = (
            f"{shown}. {event['publisher']} issued the earliest of these "
            f"{event['lead_time_hours']} hours before it took effect."
        )
        out.append(event)
    return out


def _promotions(plan, lo: date, hi: date, category: str | None) -> list[dict]:
    """Weeks the plan has a promotion running, between two days."""
    if plan is None or getattr(plan, "empty", True) or "promo_active" not in plan:
        return []
    weeks = plan.copy()
    weeks["week"] = pd.to_datetime(weeks["week"]).dt.date
    weeks = weeks[weeks["promo_active"].fillna(False).astype(bool)]
    weeks = weeks[(weeks["week"] > lo) & (weeks["week"] <= hi)]
    if category and "category" in weeks.columns:
        weeks = weeks[weeks["category"] == category]
    out: dict[tuple, dict] = {}
    for row in weeks.itertuples():
        # One promotion runs across a region's categories as several rows. The
        # reader wants the promotion, so they are folded back into one event and
        # the spend is summed rather than shown five times.
        key = (row.week, getattr(row, "promo_id", None))
        event = out.setdefault(key, {
            "day": row.week.isoformat(),
            "kind": "promotion",
            # "promo-monsoon-sale" reads as "Monsoon sale promotion".
            "label": (str(getattr(row, "promo_id", "") or "").removeprefix("promo-")
                      .replace("-", " ").strip().capitalize() + " promotion").strip(),
            "detail": "",
            "spend": 0.0,
            "regions": set(),
            "categories": set(),
        })
        event["spend"] += float(getattr(row, "marketing_spend", 0.0) or 0.0)
        if getattr(row, "region", None):
            event["regions"].add(str(row.region))
        if getattr(row, "category", None):
            event["categories"].add(str(row.category))
    events = []
    for event in out.values():
        regions = sorted(event.pop("regions"))
        categories = sorted(event.pop("categories"))
        event["detail"] = (
            f"Planned, across {', '.join(c.replace('_', ' ') for c in categories) or 'all categories'}"
            f"{' in ' + ', '.join(regions) if regions else ''}."
        )
        event["spend"] = round(event["spend"], 2)
        events.append(event)
    return events


def _calendar_events(market: str, lo: date, hi: date) -> list[dict]:
    """Public holidays between two days, with the uplift the detector applies.

    The uplift is read from `festival_factor`, the same function that divides
    the calendar out before anything is estimated, so the figure shown is the
    figure used rather than a second opinion about it. A holiday the weights do
    not name comes back at 1.0, and it is reported as unmodelled rather than
    hidden: a reader judging whether a movement was foreseeable needs to know
    which dates the expected line already accounts for and which it does not.
    """
    if hi < lo:
        return []
    cal = holidays_for(market, tuple(range(lo.year, hi.year + 1)))
    days = sorted(d for d in cal if lo <= d <= hi)
    if not days:
        return []
    factors = festival_factor(pd.Series(pd.to_datetime(days)))
    events = []
    for day, factor in zip(days, factors, strict=True):
        uplift = round(float(factor) - 1.0, 4)
        events.append({
            "day": day.isoformat(),
            "kind": "calendar",
            "label": str(cal[day]),
            "detail": (
                f"The expected line already carries {uplift:+.0%} for this day."
                if uplift else "On the calendar. No uplift is modelled for it."
            ),
            "uplift": uplift,
            "modelled": bool(uplift),
        })
    return events


# The fortnight before a finding is its baseline, so the rows show it too: a
# reader checking "short of expected" needs the days it is short of.
ROWS_BASELINE_DAYS = 14
ROWS_SAMPLE_LINES = 20


@app.get("/api/rows")
def rows(
    kpi: str = Query("net_revenue"),
    start: date = Query(...),
    end: date = Query(...),
    region: str | None = None,
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    industry: str | None = None,
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    """The aggregated rows behind a finding's figures, and the query that makes them.

    Aggregates only, on purpose. At warehouse scale nobody reads raw lines in a
    browser: the aggregation runs where the data lives and only the rows a
    figure is made of come back, which is what holds at a billion lines. There
    is no free-text SQL either. A console that runs what a reader types is a
    way round entitlement and masking; the enterprise path is to copy the
    statement into the warehouse's own editor, where its permissions apply.

    The rows come from the same path as the chart. The statement shown is run
    as well, and the response says whether it returned exactly those rows.
    """
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)
    scope = _entitlement_scope(entitled)
    _refuse_outside_scope(region, scope, contract.owner_role)
    sliced = _slice_of(contract, channel=channel, device=device, category=category)
    if end < start:
        raise HTTPException(422, "end is before start")
    lo = start - timedelta(days=ROWS_BASELINE_DAYS)

    frame = _series_frame(vertical, contract, scope, region, sliced)
    stamps = pd.to_datetime(frame["d"])
    engine = frame[(stamps >= pd.Timestamp(lo)) & (stamps < pd.Timestamp(end + timedelta(days=1)))]
    engine = engine.reset_index(drop=True)
    ratio = contract.grain.aggregation.value == "ratio_of_sums"
    hourly = contract.grain.time == "hour"

    try:
        with warehouse(vertical) as wh:
            raw = _cached(vertical, ("kpi_series", contract.kpi_id), lambda: wh.kpi_series(contract))
            rep = query_rows.reproduce(contract, raw.columns[0], lo=lo, hi=end, scope=scope,
                                       region=region, slice_=sliced)
            ran = wh.select(rep.sql, rep.params)
            served_from = ("materialised at ingest" if wh._prepared(contract).startswith("_prepared_")
                           else "computed at read")
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    match = len(ran) == len(engine) and all(
        pd.Timestamp(a) == pd.Timestamp(b) for a, b in zip(ran["d"], engine["d"], strict=True))
    diff = 0.0
    if match and len(ran):
        diff = float((ran["value"].astype(float) - engine["value"].astype(float)).abs().max())
        tolerance = 1e-9 if ratio else 1e-6
        match = diff <= tolerance * max(1.0, float(engine["value"].abs().max()))
        if ratio:
            match = match and bool((ran["n"].astype(float) == engine["n"].astype(float)).all())

    def stamp(value) -> str:
        t = pd.Timestamp(value)
        return t.isoformat(timespec="minutes") if hourly else t.date().isoformat()

    return {
        "kpi_id": contract.kpi_id,
        "version": contract.version,
        "owner_role": contract.owner_role,
        "unit": contract.unit.value,
        "grain": contract.grain.time,
        "aggregation": contract.grain.aggregation.value,
        "definition": " ".join(contract.definition.split()),
        "window": {"from": start.isoformat(), "to": end.isoformat(), "baseline_from": lo.isoformat()},
        "entitlement": list(scope) if scope is not None else None,
        "declared_sql": contract.calculation.canonical_sql.strip(),
        "lineage": [{"name": n, "sql": q} for n, q in rep.lineage],
        "served_from": served_from,
        "row_filter": contract.access_policy.row_filter or "region IN :entitled_regions",
        "dialect_targets": list(contract.calculation.dialect_targets),
        "sql": rep.literal(),
        "sql_sha256": hashlib.sha256(rep.sql.encode("utf-8")).hexdigest(),
        "rows": [
            {"d": stamp(r["d"]), "value": round(float(r["value"]), 6 if ratio else 2),
             **({"n": float(r["n"])} if ratio else {}),
             "in_window": pd.Timestamp(r["d"]) >= pd.Timestamp(start)}
            for _, r in engine.iterrows()
        ],
        "reproduced": {"match": bool(match), "rows": len(ran), "max_abs_diff": diff},
    }


@app.post("/api/rows/export")
def export_rows(payload: dict, request: Request) -> PlainTextResponse:
    """The rows as CSV, with the export on the audit trail.

    Anyone may export what they may see; the record is what makes it
    governed. It names who, which rows and a hash of the statement that
    produced them, so a figure in someone's spreadsheet can be traced back.
    """
    who = _who(request)
    try:
        start = date.fromisoformat(str(payload["start"]))
        end = date.fromisoformat(str(payload["end"]))
    except (KeyError, ValueError):
        raise HTTPException(422, "start and end are required, as YYYY-MM-DD") from None
    body = rows(
        kpi=str(payload.get("kpi") or "net_revenue"), start=start, end=end,
        region=payload.get("region") or None, channel=payload.get("channel") or None,
        device=payload.get("device") or None, category=payload.get("category") or None,
        industry=payload.get("industry") or None,
        entitled=effective_entitlement(who, payload.get("entitled")),
    )
    ratio = body["aggregation"] == "ratio_of_sums"
    head = "period,value,n,in_window" if ratio else "period,value,in_window"
    lines = [head] + [
        ",".join(str(x) for x in ((r["d"], r["value"], r["n"]) if ratio else (r["d"], r["value"]))
                 ) + f",{'yes' if r['in_window'] else 'no'}"
        for r in body["rows"]
    ]
    entry = _audit.append(
        "rows_exported", who.as_dict(),
        {"industry": payload.get("industry") or "retail", "kpi_id": body["kpi_id"],
         "region": payload.get("region") or None,
         "slice": {k: payload.get(k) for k in ("channel", "device", "category") if payload.get(k)},
         "window": {"from": start.isoformat(), "to": end.isoformat()}},
        {"rows": len(body["rows"]), "format": "csv", "sql_sha256": body["sql_sha256"],
         "reproduced": body["reproduced"]["match"],
         "statement": "Rows exported as CSV, with the statement that produced them."},
    )
    name = f"whychain-{body['kpi_id']}-{payload.get('region') or 'all'}-{start}-to-{end}.csv"
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-WhyChain-Audit-Seq": str(entry["seq"]),
    })


@app.get("/api/catalog")
def catalog(industry: str | None = None) -> dict:
    """Every governed metric: what it means, who owns it, where it comes from.

    The semantic layer, readable. A definition that lives only in YAML is one
    an analyst has to take on trust, and "how exactly do you define revenue" is
    the first question a finance reader asks of any number. Everything here is
    read from the contracts and the warehouse; nothing is typed for the page.
    """
    vertical = _vertical(industry)
    reg = registry(vertical)
    out = []
    try:
        with warehouse(vertical) as wh:
            for kpi_id in sorted(reg._contracts):
                c = reg.get(kpi_id)
                steps, _ = query_rows.lineage_ctes(c)
                fresh = wh.freshness(c)
                policy = wh.unenforceable_policy(c)
                out.append({
                    "kpi_id": c.kpi_id,
                    "version": c.version,
                    "owner_role": c.owner_role,
                    "unit": c.unit.value,
                    "definition": " ".join(c.definition.split()),
                    "grain": c.grain.time,
                    "dims": list(c.grain.dims),
                    "aggregation": c.grain.aggregation.value,
                    "ratio_of": [c.grain.numerator, c.grain.denominator]
                    if c.grain.aggregation.value == "ratio_of_sums" else None,
                    "parents": list(c.parents),
                    "children": list(c.children),
                    "diagnosable": c.decomposition.method == "pvm",
                    "sources": list(c.lineage.upstream),
                    "lineage": [{"name": n, "sql": q} for n, q in steps],
                    "served_from": ("materialised at ingest"
                                    if wh._prepared(c).startswith("_prepared_") else "computed at read"),
                    "favourable": c.favourable,
                    "sql": c.calculation.canonical_sql.strip(),
                    "dialect_targets": list(c.calculation.dialect_targets),
                    "row_filter": c.access_policy.row_filter or "region IN :entitled_regions",
                    "column_masks": list(c.access_policy.column_masks),
                    "masks_absent_from_source": policy["column_masks_absent_from_source"],
                    "personal_data": list(c.access_policy.domain_restriction),
                    "freshness": [{"source": f.source_id, "sla_hours": round(f.sla.total_seconds() / 3600, 1),
                                   "lag_hours": round(f.lag.total_seconds() / 3600, 1), "met": f.sla_met}
                                  for f in fresh.values()],
                    "materiality": {"min_abs_robust_z": c.materiality.min_abs_robust_z,
                                    "min_abs_delta_inr": c.materiality.min_abs_delta_inr},
                })
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"industry": vertical.id, "metrics": out}


@app.get("/api/calendar")
def calendar_band(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    category: str | None = None,
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    ahead: int = Query(120, ge=0, le=400, description="days to look forward"),
    industry: str | None = Query(None, description="which industry to read"),
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    """Dated events either side of the window: what was known, and what is coming.

    Two halves, and they are not symmetrical, which is the whole design.

    **Behind** the window are things that were *published before the movement
    happened*: warnings with a named publisher, a source URL and a measurable
    lead time, promotions the plan says were running, and the calendar the
    expectation is fitted to. This is the foreseeability answer made visible.
    The signal-gap stage already computes it; here a reader can see the warning
    sitting two days before the day it is looking at.

    **Ahead** of the window are only things that are *already committed or
    already dated*: the public calendar, which is computable for any year, and
    promotions the plan carries forward. **No warning signal is ever reported
    ahead.** There is no forecast here and none is implied: a warning that
    appears in the warehouse after the window end is hindsight, and showing it
    as something upcoming would be the engine claiming knowledge it did not have
    at the time. The response says so in `note` rather than leaving a reader to
    assume otherwise.

    Read-only, and nothing here feeds detection or ranking.
    """
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)
    scope = _entitlement_scope(entitled)
    _refuse_outside_scope(region, scope, contract.owner_role)

    try:
        with warehouse(vertical) as wh:
            ext = wh.table("ext_signals")
            plan = wh.table("plan_ops")
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    ext = _within_scope(ext, scope)
    plan = _within_scope(plan, scope)
    if region and ext is not None and "region" in getattr(ext, "columns", ()):
        ext = ext[ext["region"] == region]
    if region and plan is not None and "region" in getattr(plan, "columns", ()):
        plan = plan[plan["region"] == region]

    # The reader's "now" is the end of the window under review, not the clock.
    # Anchoring on today would put a demo warehouse's whole history behind an
    # empty forward half.
    end = (
        to
        or _last_recorded(plan, "week")
        or _last_recorded(ext, "valid_from")
        or datetime.now(tz=UTC).date()
    )
    start = frm or end - timedelta(days=90)
    horizon = end + timedelta(days=ahead)

    market = market_for(contract.calendar)

    behind: list[dict] = _signal_days(
        read_signals(ext, window=(start, end), region=region)
    )
    behind += _promotions(plan, start - timedelta(days=1), end, category)
    behind += _calendar_events(market, start, end)
    behind.sort(key=lambda e: e["day"])

    forward: list[dict] = _promotions(plan, end, horizon, category)
    forward += _calendar_events(market, end + timedelta(days=1), horizon)
    forward.sort(key=lambda e: e["day"])

    return {
        "kpi_id": contract.kpi_id,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "horizon": horizon.isoformat(),
        # Both, because they can disagree. The contract declares a calendar and
        # the detector does not read it (B-033); this endpoint does, so a reader
        # can see which market the dates on screen belong to.
        "calendar": contract.calendar,
        "market": market,
        "behind": behind,
        "ahead": forward,
        "note": (
            "Ahead of the window this shows only what is already dated or "
            "already committed: the public calendar, and promotions the plan "
            "carries. No warning signal is reported ahead, because a warning "
            "recorded after the window is hindsight rather than notice."
        ),
    }


@app.get("/api/decomposition")
def decomposition(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    event_start: date = Query(..., alias="start"),
    event_end: date = Query(..., alias="end"),
    baseline_days: int = Query(14, ge=7, le=90),
    industry: str | None = Query(None, description="which industry to read"),
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    """Split a movement into price, volume and mix, and locate it by dimension.

    The baseline is the period immediately before the movement, normalised to a
    daily rate so a fortnight can be compared against a week.
    """
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)  # 404s on an unknown metric before touching the warehouse
    scope = _entitlement_scope(entitled)
    _refuse_outside_scope(region, scope, contract.owner_role)

    # A bridge on a rate would be a price effect on a percentage. Decline rather
    # than decomposing something else and labelling it with this metric.
    if contract.decomposition.method != "pvm":
        raise HTTPException(
            422,
            f"{kpi} is measured in {contract.unit.value} and is not a sum of "
            "priced units, so a price/volume/mix bridge does not apply to it. "
            "Dimensional contribution is available; the bridge is not.",
        )

    try:
        with warehouse(vertical) as wh:
            panel = wh.bridge_facts(
                contract,
                since=event_start - timedelta(days=baseline_days + 1),
                until=event_end,
            )
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    panel = _within_scope(panel, scope)
    if region:
        panel = panel[panel["region"] == region]
    # The bridge on this page sits beside the diagnosis on the same page. If one
    # is sliced to a channel and the other is not they disagree by construction,
    # and the page shows two totals for one movement.
    sliced = _slice_of(contract, channel=channel, device=device, category=category)
    for dimension, value in sliced.items():
        if dimension in panel.columns:
            panel = panel[panel[dimension] == value]
    if panel.empty:
        raise HTTPException(404, "no data for that slice")
    day = pd.to_datetime(panel["d"]).dt.date

    base_start = event_start - timedelta(days=baseline_days)
    base = panel[(day >= base_start) & (day < event_start)]
    current = panel[(day >= event_start) & (day <= event_end)]
    if base.empty or current.empty:
        raise HTTPException(404, "no data in the baseline or the event window")

    base_days = max((event_start - base_start).days, 1)
    event_days = max((event_end - event_start).days + 1, 1)
    base = base.assign(units=base["units"] / base_days, revenue=base["revenue"] / base_days)
    current = current.assign(
        units=current["units"] / event_days, revenue=current["revenue"] / event_days
    )

    try:
        bridge = compute_bridge(base, current)
    except BridgeError as exc:
        # An identity that does not hold must not be presented as one.
        raise HTTPException(422, str(exc)) from exc

    dimensions = [d for d in ("channel", "device", "category", "region") if d in panel.columns]
    contributions = []
    scoping = ({"region"} if region else set()) | set(sliced)
    for dim in dimensions:
        # A dimension the reader has pinned is the whole slice, so its
        # contribution is 100% and it displaces a real contributor.
        if dim in scoping:
            continue
        c = contribution_by(base, current, dim)
        contributions.append(
            {
                "dimension": dim,
                "total_change": round(c.total_change, 2),
                "concentration_top1": round(c.concentration(1), 4),
                "slices": [
                    {
                        "value": s.value,
                        "base": round(s.base, 2),
                        "current": round(s.current, 2),
                        "delta": round(s.delta, 2),
                        "share": round(c.share_of(s), 4),
                        "pct_change": round(s.pct_change, 4) if s.pct_change is not None else None,
                    }
                    for s in c.ranked()
                ],
            }
        )

    shares = bridge.shares()
    return {
        "kpi_id": kpi,
        "region": region,
        "baseline": {"from": base_start.isoformat(), "to": (event_start - timedelta(days=1)).isoformat()},
        "event": {"from": event_start.isoformat(), "to": event_end.isoformat()},
        "bridge": {
            "base_revenue": round(bridge.base_revenue, 2),
            "current_revenue": round(bridge.current_revenue, 2),
            "total_change": round(bridge.total_change, 2),
            "legs": [
                {"leg": "volume", "value": round(bridge.volume_effect, 2), "share": round(shares["volume"], 4)},
                {"leg": "mix", "value": round(bridge.mix_effect, 2), "share": round(shares["mix"], 4)},
                {"leg": "price", "value": round(bridge.price_effect, 2), "share": round(shares["price"], 4)},
            ],
            "residual": round(bridge.residual, 6),
            "reconciles": abs(bridge.residual) < 0.1,
            "base_units": round(bridge.base_units, 1),
            "current_units": round(bridge.current_units, 1),
        },
        "contributions": contributions,
    }


@app.get("/api/candidates")
def candidates(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    event_start: date = Query(..., alias="start"),
    event_end: date = Query(..., alias="end"),
    industry: str | None = Query(None, description="which industry to read"),
    entitled: str | None = Query(None, description="comma-separated regions"),
) -> dict:
    """Every candidate cause in the record, and whether it survives testing.

    This endpoint took no entitlement at all, which made it a way round the one
    applied on `/api/diagnose`: the console never called it with a scope, so
    nothing broke, and a caller constructing the request by hand could read every
    candidate cause and its contribution for any region. A restriction enforced on
    one endpoint and not on its neighbour is not enforced.

    Candidates arrive from the operational data with nothing marking which are
    real. Ranking them by association would promote whatever happened to
    coincide; that is exactly what the tests exist to prevent.
    """
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)
    scope = _entitlement_scope(entitled)
    # Candidate testing runs difference-in-differences over a revenue panel, so
    # it needs the same facts the bridge does. Say so plainly: a metric with no
    # bridge is a 422 with a reason, not a 503, which would claim the service is
    # unavailable when it is answering correctly.
    if contract.decomposition.method != "pvm":
        raise HTTPException(
            422,
            f"{kpi} has no price/volume/mix panel to test candidates against, "
            "so causal verification is not available for it yet.",
        )
    try:
        with warehouse(vertical) as wh:
            panel = wh.bridge_facts(
                contract, since=_lookback(event_start, 14), until=event_end
            )
            documents = wh.table("voice_ops")
            plan = wh.table("plan_ops")
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    found = from_operations(
        documents, event_start, event_end, vocabulary=vertical.corpus.vocabulary,
        skus=_skus(panel),
    ) + from_promotions(plan, event_start, event_end, vertical.plan)
    all_regions = tuple(sorted(panel["region"].unique()))

    # `region` narrows which candidates are worth reporting, never the panel they
    # are tested against. Difference-in-differences needs the unexposed regions
    # to compare with, so filtering the data here would remove the control group
    # and quietly turn every verdict into CANNOT_VERIFY.
    if region:
        if region not in all_regions:
            raise HTTPException(404, f"no data for region {region!r}")
        # Asking about a region you are not entitled to is refused here, before
        # anything is computed, rather than computed and then scrubbed on the
        # way out. Redaction-after-computation cannot be made airtight on this
        # shape of answer: a contribution table sliced by channel, a scenario
        # estimate, a narrative sentence and a per-cause map all carry the same
        # figure in different clothes, and each one has to be found and removed
        # separately. Refusing the question removes the class.
        #
        # Note what is *not* being claimed: the panel still contains every
        # region, because difference-in-differences needs the unexposed ones as
        # a control and filtering them out would turn every verdict into
        # CANNOT_VERIFY. Using a region as a statistical control is not the same
        # act as disclosing its figures to a reader, and only the second is what
        # entitlement governs.
        _refuse_outside_scope(region, scope, contract.owner_role)
        found = [
            c for c in found
            if not c.exposed_regions or region in c.exposed_regions
        ]

    # The same narrowing one level finer, and for the same reason: an app-only
    # release regression is not a candidate for a movement in the store channel.
    # The panel is untouched, so difference-in-differences keeps its controls.
    sliced = _slice_of(contract, channel=channel, device=device, category=category)
    found = [c for c in found if touches_scope(c, sliced).relevant]

    verified, rejected, untestable = [], [], []
    for candidate in found:
        v = verify(candidate, panel, all_regions)
        corr = corroborate(candidate, documents, corpus=vertical.corpus,
                           retriever=ticket_retriever(documents), index=False)
        row = {
            "candidate_id": candidate.candidate_id,
            "kind": candidate.kind,
            "description": candidate.description,
            "exposed_regions": list(candidate.exposed_regions) or list(all_regions),
            "scope": candidate.scope(),
            "bone": bone_for(candidate.kind, candidate.description),
            "state": v.state.value,
            "reason": v.reason,
            "effect_pct": round(v.effect_pct, 4) if v.effect_pct is not None else None,
            "per_region": {k: round(x, 4) for k, x in v.per_region.items()
                           if x == x},  # drop NaN
            "tests": [
                {"name": t.name, "outcome": t.outcome.value, "detail": t.detail}
                for t in v.results
            ],
            "corroboration": {
                "searched": corr.searched,
                "supporting": corr.support_count,
                "summary": corr.summary,
                "flagged": len(corr.flagged),
                "citations": [
                    {
                        "doc_id": e.doc_id,
                        "issue": str(e.issue),
                        "span": list(e.span),
                        "quote": e.quote,
                        "flags": list(e.flags),
                    }
                    for e in corr.supporting[:4]
                ],
            },
        }
        {"verified": verified, "rejected": rejected}.get(row["state"], untestable).append(row)

    return {
        "kpi_id": kpi,
        "region": region,
        "window": {"from": event_start.isoformat(), "to": event_end.isoformat()},
        "counts": {
            "considered": len(found),
            "verified": len(verified),
            "rejected": len(rejected),
            "cannot_verify": len(untestable),
        },
        "verified": verified,
        "rejected": rejected,
        "cannot_verify": untestable,
    }



def _driver_series(
    panel: pd.DataFrame,
    plan: pd.DataFrame,
    region: str | None,
    event_start: date,
    baseline_days: int,
    plan_columns: PlanColumns = RETAIL_PLAN_COLUMNS,
) -> pd.DataFrame:
    """Daily series for each driver the contract names, on the metric's index.

    `plan_ops` lands weekly, so it is forward-filled onto days: a planner's
    stock and spend figures hold until the next planning cycle replaces them,
    which is what the source actually means. Interpolating between them would
    invent a mid-week decision nobody took.
    """
    days = panel.assign(d=pd.to_datetime(panel["d"]).dt.date)
    price = days.groupby("d").apply(
        lambda g: (g["revenue"].sum() / g["units"].sum()) if g["units"].sum() else float("nan"),
        include_groups=False,
    )
    frame = pd.DataFrame({"realised_price": price})

    if plan is not None and not plan.empty:
        p = plan.copy()
        if region:
            p = p[p["region"] == region]
        if not p.empty:
            p["week"] = pd.to_datetime(p["week"])
            # Levels are summed and the index is averaged. The mean of a week of
            # index readings is an index; their sum is nothing. Which columns
            # are which is a property of the industry's planning extract, so the
            # names come from the vertical rather than from here.
            levels = [c for c in plan_columns.levels if c in p.columns]
            index_col = plan_columns.index if plan_columns.index in p.columns else None
            wanted = levels + ([index_col] if index_col else [])
            if not wanted:
                return frame.dropna(axis=1, how="all")
            weekly = p.groupby("week")[wanted].sum(numeric_only=True)
            if index_col:
                weekly[index_col] = p.groupby("week")[index_col].mean()
            index = pd.to_datetime(pd.Series(sorted(frame.index)))
            daily = weekly.reindex(
                weekly.index.union(index)
            ).sort_index().ffill().reindex(index)
            daily.index = [d.date() for d in index]
            frame = frame.join(daily)

    return frame.dropna(axis=1, how="all")


# Dimensions a reader can narrow by, in the order a scope control should offer
# them: where, then how it was sold, then on what, then what. `sku` is excluded
# deliberately -- a select with hundreds of entries is a search box, not a
# filter, and nothing on this page is ranked by it.
FILTERABLE_DIMS = ("region", "channel", "category", "device")


def _dimension_values(vertical, contract, scope) -> dict[str, list[str]]:
    """What each scope control may offer, from the warehouse rather than a list.

    Entitlement applies: a reader who may see South is not offered West in a
    dropdown, because an unselectable option still discloses that the region
    exists and what it is called.
    """
    try:
        with warehouse(vertical) as wh:
            panel = _cached(
                vertical,
                ("dimension_values", contract.kpi_id),
                lambda: wh.kpi_series(contract),
            )
    except IngestError:
        return {}
    panel = _within_scope(panel, scope)
    return {
        dim: sorted(str(v) for v in panel[dim].dropna().unique())
        for dim in FILTERABLE_DIMS
        if dim in contract.grain.dims and dim in panel.columns
    }


def _narrow(frame, sliced: dict[str, str]):
    """Apply a slice to a frame, and refuse to pretend when a column is absent.

    Filtering only the columns that happen to exist is how a control ends up
    doing nothing: the rail offered Category, the frame had no category column
    on that path, the figures came back identical and the reader learned that
    none of the controls mean anything. So a dimension the contract declares but
    this frame does not carry is a fault, not a silent no-op.
    """
    for dimension, value in sliced.items():
        if dimension not in frame.columns:
            raise HTTPException(
                500,
                f"{dimension} is declared in the contract grain but is not in "
                f"this frame, so the filter could not be applied",
            )
        frame = frame[frame[dimension] == value]
    return frame


def _slice_of(contract, **dims: str | None) -> dict[str, str]:
    """The finer scope a reader asked for, checked against the contract's grain.

    A named dimension this metric is not measured at is refused rather than
    dropped. Silently ignoring `channel=app` on a metric with no channel column
    answers a different question than the one asked and looks identical on the
    page, which is the worst available behaviour.
    """
    asked = {d: v for d, v in dims.items() if v}
    unknown = [d for d in asked if d not in contract.grain.dims]
    if unknown:
        raise HTTPException(
            422,
            f"{contract.kpi_id} is not measured by {', '.join(sorted(unknown))}. "
            f"Its grain is {', '.join(contract.grain.dims)}.",
        )
    return asked


@app.get("/api/diagnose")
def diagnose(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    channel: str | None = Query(None, description="narrow the movement to one channel"),
    device: str | None = Query(None, description="narrow the movement to one device"),
    category: str | None = Query(None, description="narrow the movement to one category"),
    event_start: date = Query(..., alias="start"),
    event_end: date = Query(..., alias="end"),
    baseline_days: int = Query(14, ge=7, le=90),
    persona: str = Query("analyst"),
    entitled: str | None = Query(
        None, description="comma-separated regions this requester may see"
    ),
    price_delta: float = Query(-0.05, ge=-0.5, le=0.5),
    horizon_days: int = Query(14, ge=1, le=90),
    backend: str | None = Query(
        None, description="model backend for this run: ollama, openai, none"
    ),
    llm_model: str | None = Query(None, description="model id for this run"),
    industry: str | None = Query(None, description="which industry to read"),
) -> dict:
    """The whole pipeline for one movement: decompose, test, corroborate, score.

    Returns either a diagnosis or an abstention. Never both, and never a
    best guess dressed as the former.
    """
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)
    if contract.decomposition.method != "pvm":
        raise HTTPException(
            422,
            f"{kpi} is measured in {contract.unit.value} and cannot be "
            "decomposed by the price/volume/mix identity, so a full diagnosis "
            "is not yet available for it. Detection and freshness are.",
        )

    # Parsed here rather than at the projection, because entitlement now gates
    # the request as well as the rendering.
    scope = _entitlement_scope(entitled)

    run_id = f"run-{uuid4().hex[:10]}"
    tel = Telemetry(run_id=run_id)

    try:
        with tel.stage("read", MethodClass.DETERMINISTIC), warehouse(vertical) as wh:
            panel = wh.bridge_facts(
                contract,
                since=_lookback(event_start, baseline_days),
                until=event_end,
            )
            documents = wh.table("voice_ops")
            plan = wh.table("plan_ops")
            ext = wh.table("ext_signals")
            sources = wh.freshness(contract)
            # The second system's posting of the same quantity, if the contract
            # declares one. Read here with everything else so the reconciliation
            # costs one trip rather than its own.
            ledger = (
                wh.table(contract.reconciliation.source)
                if contract.reconciliation.declared else None
            )
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    # Refused before anything is computed, rather than computed and scrubbed on
    # the way out. See the note on the same guard in `candidates`: this shape of
    # answer carries the same figure in a contribution table, a scenario
    # estimate, a narrative sentence and a per-cause map, and each has to be
    # found and removed separately. Refusing the question removes the class.
    if region:
        _refuse_outside_scope(region, scope, contract.owner_role)

    sliced = _slice_of(contract, channel=channel, device=device, category=category)

    # Region first, because it is the one entitlement gates. The rest narrow the
    # same frame: a movement in the app on mobile in the West is a different
    # movement from the West's total, and the bridge below reconciles against
    # whichever one was asked for or raises rather than reporting.
    scoped = panel[panel["region"] == region] if region else panel
    for dimension, value in sliced.items():
        if dimension in scoped.columns:
            scoped = scoped[scoped[dimension] == value]
    if scoped.empty:
        raise HTTPException(404, "no data for that slice")

    day = pd.to_datetime(scoped["d"]).dt.date
    base_lo = event_start - timedelta(days=baseline_days)
    base = scoped[(day >= base_lo) & (day < event_start)]
    current = scoped[(day >= event_start) & (day <= event_end)]
    if base.empty or current.empty:
        raise HTTPException(404, "no data in the baseline or the event window")

    event_days = max((event_end - event_start).days + 1, 1)
    base = base.assign(units=base["units"] / baseline_days,
                       revenue=base["revenue"] / baseline_days)
    current = current.assign(units=current["units"] / event_days,
                             revenue=current["revenue"] / event_days)
    # Before anything is explained, not after. A movement two systems disagree
    # about is not a movement with lower confidence -- it may not have happened,
    # and every stage below this one will do its job correctly on it and arrive
    # at a confident, well-evidenced, completely false explanation. Detection
    # flags it because the series really does fall; ranking finds the slice
    # because that slice really is missing; the causal tests confirm the fall is
    # isolated because it is. Nothing downstream can catch this, which is why
    # the check sits above them rather than among them.
    with tel.stage("reconcile", MethodClass.DETERMINISTIC) as t:
        day_series = (
            scoped.assign(_d=pd.to_datetime(scoped["d"]).dt.date)
            .groupby("_d", as_index=False)["revenue"].sum()
            .rename(columns={"_d": "d", "revenue": "value"})
        )
        # Both sides of a reconciliation have to be the same slice of the same
        # business. The ledger posts at invoice level by region and carries no
        # channel or device, so a channel-sliced revenue series compared against
        # the whole ledger disagrees by construction: measured, an app-only
        # window read as a 68% contradiction and the run returned `contradicted`
        # with no cause proposed. That is a false refusal, which costs more here
        # than a false explanation would elsewhere, because refusal is the one
        # output this engine asks to be trusted on.
        #
        # So the ledger is narrowed by every dimension it actually has, and when
        # the reader has asked for one it does not, the comparison is declined
        # rather than made badly.
        comparable = ledger
        beyond = []
        if comparable is not None:
            if region and "region" in comparable:
                comparable = comparable[comparable["region"] == region]
            for dimension, value in sliced.items():
                if dimension in comparable:
                    comparable = comparable[comparable[dimension] == value]
                else:
                    beyond.append(dimension)
            if beyond:
                comparable = None
        agreement = reconcile(
            contract, day_series, comparable, window=(event_start, event_end),
        )
        if beyond:
            agreement = replace(
                agreement,
                reason=(
                    f"{contract.reconciliation.source} is not broken down by "
                    f"{', '.join(sorted(beyond))}, so this slice has no second "
                    f"posting to check against. The movement stands on one "
                    f"source alone."
                ),
            )
        t.note = (
            f"{agreement.state.value}"
            + (f" against the {label(agreement.source)}, worst {agreement.worst_residual:.1%}"
               if agreement.days else "")
        )

    try:
        with tel.stage("decompose", MethodClass.DETERMINISTIC):
            bridge = compute_bridge(base, current)
    except BridgeError as exc:
        raise HTTPException(422, str(exc)) from exc

    all_regions = tuple(sorted(panel["region"].unique()))
    found, set_aside = filter_relevant(
        from_operations(
            documents, event_start, event_end, vocabulary=vertical.corpus.vocabulary,
            skus=_skus(panel),
        )
        + from_promotions(plan, event_start, event_end, vertical.plan),
        event_start, event_end, region, sliced,
    )

    with tel.stage("rank", MethodClass.STATISTICAL) as t:
        # Every scoping dimension is excluded, not only region. With a region
        # selected the "region = West" slice *is* the total, so it tops the
        # ranking at a 100% share and says nothing; a row that is true, useless,
        # and displaces a real contributor out of the list. The same becomes
        # true of channel the moment a channel is selected.
        scoping = ({"region"} if region else set()) | set(sliced)
        contributions = [
            contribution_by(base, current, dim)
            for dim in contract.grain.dims
            if dim in base.columns and dim not in scoping
        ]
        # Track B needs a daily series per driver. They are built here rather
        # than inside the ranker because the shape of a driver series is a
        # property of this warehouse, not of the method: `plan_ops` is weekly
        # and regional, the price and volume series come off the panel, and a
        # ranker that knew that could not be pointed at a different warehouse.
        drivers = _driver_series(
            scoped, plan, region, event_start, baseline_days, vertical.plan_columns
        )
        metric = (
            scoped.assign(d=pd.to_datetime(scoped["d"]).dt.date)
            .groupby("d")["revenue"].sum()
        )
        ranking = rank(
            contributions, metric, drivers,
            rejected=frozenset(c.candidate_id for c, _ in set_aside),
            top_n=8,
        )
        t.note = (
            f"Track A: {plural(len(ranking.exact), 'exact contribution')}; "
            f"Track B: {len(ranking.associational)} associational, none stateable"
        )

    with tel.stage("verify", MethodClass.CAUSAL) as t:
        verifications = [verify(c, panel, all_regions) for c in found]
        t.note = f"{len(found)} candidates tested"
    _verified_ids = {
        v.candidate.candidate_id for v in verifications
        if v.state.value == "verified"
    }

    with tel.stage("corroborate", MethodClass.RETRIEVAL) as t:
        shared = ticket_retriever(documents)
        # One extractor across the whole run, so its token cost is counted once
        # and the receipt reports the reading it actually did.
        # The request may pin a backend, which is what makes the choice
        # demonstrable rather than merely configurable. With none pinned the
        # environment decides, and with nothing reachable `ModelExtractor`
        # falls through to the rule table on its own.
        # Extraction and narration are routed separately, because they are not
        # equally hard and should not cost the same.
        reader = ModelExtractor(
            backend=model_for(Task.EXTRACT, backend) if not llm_model
            else default_model(llm_model, backend),
            # Read this industry's tickets in this industry's vocabulary. Left
            # to its default the extractor offered retail's codes whatever was
            # being diagnosed, so a fuel dealer's "no stock, allocation cut to
            # half" had no code to land in and corroboration was empty for every
            # externally-caused event in petroleum and power.
            vocabulary=vertical.corpus.vocabulary,
        )
        # An operational note and the complaint it produces are written in
        # different registers, and bridging them is a language problem the
        # keyword table can only solve by having the synonyms written into it by
        # hand -- per industry, by a person. The model proposes them instead.
        # Retrieval underneath is unchanged and the proposal is filtered to
        # language before it is used, so a bad expansion retrieves less rather
        # than retrieving wrong.
        expander = ModelQueryWriter(
            backend=model_for(Task.EXPAND, backend) if not llm_model
            else default_model(llm_model, backend),
            vocabulary=vertical.corpus.vocabulary,
        )
        # Only what is actually read. Corroboration is consumed for verified
        # candidates alone -- it feeds their citation list and the confidence
        # component -- and it was being computed for every candidate that had
        # been tested and rejected as well. Deterministically that was wasted
        # milliseconds; with a model behind the extractor it is a wasted call
        # per rejected candidate, which on the flagship case was most of them.
        needed = [c for c in found if c.candidate_id in _verified_ids]
        corroborations = {
            c.candidate_id: corroborate(
                c, documents, corpus=vertical.corpus,
                retriever=shared, index=False, extractor=reader,
                query_writer=expander,
                # `domain_restriction` on the contract, finally read by
                # something. Ticket text is where personal data actually appears
                # in this system, and this is the last point before it becomes
                # prompt tokens.
                domain_restriction=contract.access_policy.domain_restriction,
            )
            for c in needed
        }
        t.model_calls = getattr(reader, "calls", 0) + expander.calls
        t.cache_hits = getattr(reader, "cache_hits", 0) + expander.cache_hits
        t.tokens_in = getattr(reader, "tokens_in", 0) + expander.tokens_in
        t.tokens_out = getattr(reader, "tokens_out", 0) + expander.tokens_out
        # Retrieval is deterministic either way. What varies is who reads the
        # tickets: a keyword table, or a model whose every citation is checked
        # back against the source text before it is allowed to ship.
        t.note = (
            f"tf-idf retrieval; {expander.note or 'deterministic query'}; "
            + (getattr(reader, "note", "") or "deterministic span extraction")
        )

    supporting = sum(
        corroborations[v.candidate.candidate_id].support_count
        for v in verifications
        if v.state.value == "verified"
    )
    with tel.stage("confidence", MethodClass.STATISTICAL):
        explained, per_cause, overlap = explained_movement(
            verifications, panel, event_start, event_end, baseline_days,
            total_movement=bridge.total_change,
        )
        confidence = score(
            verifications, explained=explained, total_movement=bridge.total_change,
            supporting_documents=supporting, sources=sources, overlap=overlap,
            calibration=calibration(),
        )

    with tel.stage("actions", MethodClass.DETERMINISTIC) as t:
        cards = decision_cards(
            verifications, per_cause, contract, confidence.band.value,
            drivers=vertical.drivers,
            recovery_model=vertical.recovery,
        )
        scenarios = simulate(
            verifications, per_cause, contract,
            base_revenue_per_day=bridge.current_revenue,
            price_delta=price_delta, horizon_days=horizon_days,
            recovery=vertical.recovery,
        )
        t.note = f"{plural(len(cards), 'decision card')}, every field derived"

    with tel.stage("signalgap", MethodClass.DETERMINISTIC) as t:
        verified_descriptions = [
            v.candidate.description for v in verifications
            if v.state.value == "verified" and v.candidate.description
        ]
        # The metric's own daily series over the precedent window, so "this has
        # happened before" can be reported as "and it cost us something" rather
        # than left as a count of weather.
        # A separate, longer read. The diagnosis panel only spans the baseline
        # and the event, so judging a precedent from two years ago against it
        # returns "cannot tell" for almost every episode, and a recurrence
        # figure where most rows are unknown is not worth showing.
        try:
            with warehouse(vertical) as wh:
                deep = wh.bridge_facts(
                    contract,
                    since=event_start - timedelta(days=PRECEDENT_LOOKBACK_DAYS),
                    until=event_start,
                )
            if region:
                deep = deep[deep["region"] == region]
            history = (
                deep.assign(_d=pd.to_datetime(deep["d"]).dt.date)
                .groupby("_d")["revenue"].sum()
            )
        except IngestError:
            history = None
        gap = find_gap(
            contract, ext,
            event_start=event_start, event_end=event_end,
            region=region, causes=verified_descriptions, history=history,
        )
        t.note = (
            f"Verdict {label(gap.verdict.value)}, {plural(gap.recurrence, 'prior episode')}, "
            f"{gap.recurrence_that_hurt or 'none'} of which moved the metric"
        )

    stale = tuple(f"{f.source_id} is stale by {f.lag}" for f in sources.values()
                  if not f.sla_met)
    result = {
        "kpi_id": kpi,
        "run_id": run_id,
        "region": region,
        # What the answer is about. Without it on the response a reader cannot
        # tell a national answer from a single-channel one.
        "slice": sliced,
        "decisions": [_already_actioned(c.as_dict(), verifications, documents)
                      for c in cards],
        "scenarios": [sc.as_dict() for sc in scenarios],
        "window": {"from": event_start.isoformat(), "to": event_end.isoformat()},
        "baseline": {"from": base_lo.isoformat(),
                     "to": (event_start - timedelta(days=1)).isoformat()},
        "movement": {
            "base_revenue": round(bridge.base_revenue, 2),
            "current_revenue": round(bridge.current_revenue, 2),
            "total_change": round(bridge.total_change, 2),
            "pct": round(bridge.current_revenue / bridge.base_revenue - 1, 4)
            if bridge.base_revenue else None,
            "explained": round(explained, 2),
            # How far the per-cause figures overlap. 1.0 means they are disjoint
            # and sum to `explained`; above that they sum to more than the
            # movement, and a reader adding the column up needs telling why it
            # does not reconcile.
            # Full precision: it is a divisor. Rounded to three places it moved a
            # scaled figure by four rupees between two views of one cause.
            "overlap": round(overlap, 6),
            "per_cause": {k: round(v2, 2) for k, v2 in per_cause.items()},
        },
        "confidence": {
            "score": confidence.score,
            "band": confidence.band.value,
            "caveats": list(confidence.caveats),
            "probability": confidence.probability,
            "calibrated_on": confidence.calibrated_on,
            "components": [
                {"name": c.name, "value": round(c.value, 3), "detail": c.detail}
                for c in confidence.components
            ],
            "reasons": list(confidence.reasons),
        },
        "ranking": ranking.as_dict(),
        "signal_gap": gap.as_dict(),
        "reconciliation": agreement.as_dict(),
        "set_aside": [
            # The description is for readers; the prompt builder reads only the
            # id and the reason, so adding it leaves every cached answer valid.
            {"candidate_id": c.candidate_id, "description": c.description, "reason": why,
             "bone": bone_for(c.kind, c.description)}
            for c, why in set_aside
        ],
        "verified": [
            {
                "candidate_id": v.candidate.candidate_id,
                "description": v.candidate.description,
                "effect_pct": round(v.effect_pct, 4) if v.effect_pct else None,
                "contribution": round(per_cause.get(v.candidate.candidate_id, 0.0), 2),
                "supporting_documents": corroborations[v.candidate.candidate_id].support_count,
                "external_signals": _external_for(ext, v.candidate, event_end),
                "issue": next(
                    (str(e.issue) for e in
                     corroborations[v.candidate.candidate_id].supporting), None
                ),
                "citations": [
                    {"doc_id": e.doc_id, "span": list(e.span), "quote": e.quote,
                     "issue": str(e.issue), "flags": list(e.flags)}
                    for e in corroborations[v.candidate.candidate_id].supporting[:6]
                ],
                "tests": [
                    {"name": t.name, "outcome": t.outcome.value, "detail": t.detail}
                    for t in v.results
                ],
                "exposed_regions": list(v.candidate.exposed_regions),
                "scope": v.candidate.scope(),
                "bone": bone_for(v.candidate.kind, v.candidate.description),
            }
            for v in verifications
            if v.state.value == "verified"
        ],
    }

    if agreement.blocks_diagnosis:
        # Its own verdict, not an abstention with a footnote. "We could not tell
        # what caused this" and "we cannot agree that this happened" are
        # different answers to the reader, and only the second one makes the
        # decisive next step a question for data engineering rather than for the
        # business. Collapsing them into `unknown` would send a finance director
        # looking for a commercial explanation of a broken extract.
        #
        # The causes are still carried, and still marked. A reader is entitled
        # to see what the engine would have said, provided it is not offered as
        # what the engine does say.
        result["verdict"] = "contradicted"
        result["abstention"] = {
            "coverage": 0.0,
            "ruled_out": [],
            "blocking": [agreement.reason],
            "next_check": (
                f"Reconcile {label(kpi)} against the {label(agreement.source)} for this window "
                f"before asking what moved it; the two systems disagree by "
                f"{agreement.worst_residual:.0%} and one of them is wrong"
            ),
            "question": (
                f"Is the {label(kpi)} extract complete for "
                f"{event_start.isoformat()} to {event_end.isoformat()}?"
            ),
        }
    elif confidence.abstained:
        a = abstain(verifications, confidence, blocking=stale)
        result["verdict"] = "unknown"
        result["abstention"] = {
            "coverage": round(a.coverage, 3),
            "ruled_out": list(a.ruled_out),
            "blocking": list(a.blocking),
            "next_check": a.next_check,
            "question": a.question,
        }
    else:
        result["verdict"] = "explained"

    # The most useful sentence in the product on the days there is no answer,
    # and it was three template branches. The model rewrites it from the shape
    # of this particular failure; a deterministic check rejects any sentence
    # that proposes a cause, names something the run does not contain, or
    # restates a figure, and the template stands when it does.
    if result.get("abstention"):
        with tel.stage("nextcheck", MethodClass.LLM) as t:
            known = {c.kpi_id for c in registry(vertical)} | set(all_regions) | {
                d.id for d in contract.drivers
            } | {d.owner_role for d in contract.drivers if d.owner_role} | {
                contract.owner_role, contract.kpi_id,
                contract.reconciliation.source or "",
            }
            proposal = propose_next_check(
                result,
                fallback=result["abstention"]["next_check"],
                backend=(
                    model_for(Task.NARRATE, backend) if not llm_model
                    else default_model(llm_model, backend)
                ),
                extra_terms=frozenset(k.lower() for k in known if k),
            )
            result["abstention"]["next_check"] = proposal.text
            result["abstention"]["next_check_by"] = proposal.as_dict()
            t.model_calls = proposal.model_calls
            t.cache_hits = proposal.cache_hits
            t.tokens_in, t.tokens_out = proposal.tokens_in, proposal.tokens_out
            t.note = (
                f"{proposal.writer}"
                + (f"; rejected: {proposal.rejected}" if proposal.rejected else "")
            )

    # The narrative is written from the finished result and nothing else, so it
    # can only describe what the pipeline concluded. It runs after abstention is
    # decided, because "we could not tell" is one of the things it has to say.
    with tel.stage("narrate", MethodClass.LLM) as t:
        known = set(all_regions) | {
            c.kpi_id for c in registry(vertical)
        } | {d.id for d in contract.drivers} | {
            d.owner_role for d in contract.drivers if d.owner_role
        } | {contract.owner_role, contract.kpi_id}
        story = narrate(
            result,
            writer=ModelWriter(
                backend=model_for(Task.NARRATE, backend) if not llm_model
                else default_model(llm_model, backend)
            ),
            known_entities=frozenset(k for k in known if k),
        )
        t.model_calls = story.model_calls
        t.cache_hits = story.cache_hits
        t.tokens_in, t.tokens_out = story.tokens_in, story.tokens_out
        t.note = (
            f"{sentence_case(story.writer)}; {plural(len(story.sentences), 'sentence')} accepted, "
            f"{len(story.validation.rejected)} rejected by the validator"
        )
    result["narrative"] = story.as_dict()
    # Routing on the receipt, so a reader can see which model did which job and
    # that the choice was made per task rather than once for everything.
    result["llm"] = {"routing": routing(), "active": describe(model_for(Task.NARRATE))}

    # Last, so the receipt covers every stage that actually ran.
    result["telemetry"] = tel.receipt()

    # The projection happens after everything is computed and never before: the
    # evidence set is identical for every reader, and only what is rendered from
    # it differs. Entitlement is applied here, at the projection layer.
    try:
        who = Persona(persona)
    except ValueError:
        raise HTTPException(
            422, f"unknown persona {persona!r}; expected one of "
            f"{[p.value for p in Persona]}"
        ) from None
    with tel.stage("project", MethodClass.DETERMINISTIC) as t:
        projected = project(result, who, entitled_regions=scope)
        t.note = f"persona {who.value}"
    # Of the full evidence, not the projection, so every reader of the same run
    # sees the same value, and a signature can be checked against it without
    # running the diagnosis a second time.
    projected["evidence_fingerprint"] = evidence_fingerprint(result)
    # From the full evidence, but withheld whole when the reader's entitlement
    # removed any cause: the net less the visible factors would otherwise
    # recover exactly what the withheld one was worth.
    projected["fair_target"] = fair_target(
        result, withheld=bool((projected.get("entitlement") or {}).get("notice")))
    # The fishbone's categories. Fixed labels and nothing about this run, so
    # safe after projection (T-32): they name no cause and size nothing.
    projected["bones"] = bones()
    # The variance bridge, from the projected movement so a withheld cause is
    # already absent. Labels only for causes this reader was given a figure for.
    shown = set((projected.get("movement") or {}).get("per_cause") or {})
    projected["waterfall"] = cause_waterfall(projected.get("movement"), {
        v.candidate.candidate_id: plain(v.candidate.description)
        for v in verifications if v.candidate.candidate_id in shown
    })
    return projected


def fair_target(result: dict, withheld: bool = False) -> dict | None:
    """How much of a movement the team should be judged on.

    The planning and operating split from management accounting, with the
    evidence doing the work opinion usually does. A verified cause the contract
    marks as having no lever is a condition beyond the team's control. Its size
    is its measured contribution, scaled back when causes overlap so the pieces
    sum to the real movement.

    Two refinements the research on the controllability principle asks for:
    a condition that was *warned in time* is flagged rather than excused, since
    a team can prepare for what it was told was coming; and a favourable
    condition raises the bar exactly as an adverse one lowers it, so good luck
    is not free. Nothing here changes a target; it is a proposal that only the
    metric's accountable owner can apply, through /api/adjustment.
    """
    if result.get("verdict") != "explained":
        return None
    movement = result.get("movement") or {}
    if withheld or movement.get("per_cause_withheld"):
        return {"withheld": True, "factors": [],
                "note": ("A cause here lies outside your entitlement, so the fair target is "
                         "shown only to a reader entitled to every region it touches.")}
    per_cause = movement.get("per_cause") or {}
    net = float(movement.get("total_change") or 0.0)
    gross = sum(abs(v) for v in per_cause.values())
    scale = min(1.0, abs(net) / gross) if gross else 1.0
    gap = result.get("signal_gap") or {}
    factors = []
    for card in result.get("decisions") or []:
        if card.get("controllable"):
            continue
        cid = card.get("candidate_id")
        amount = round(float(per_cause.get(cid, 0.0)) * scale, 2)
        warned = gap.get("verdict") == "gap_found" and card.get("driver") == gap.get("signal_type")
        factors.append({
            "candidate_id": cid,
            "cause": card.get("cause"),
            "amount_inr_per_day": amount,
            "direction": "headwind" if amount < 0 else "tailwind",
            "warned": warned,
            "lead_time_hours": gap.get("best_lead_time_hours") if warned else None,
            "excused_by_policy": not warned,
        })
    if not factors:
        return {"net_inr_per_day": round(net, 2), "factors": [], "policy_inr_per_day": round(net, 2),
                "all_excused_inr_per_day": round(net, 2),
                "note": "Every verified cause has a lever, so the whole movement is the team's."}
    excused = sum(f["amount_inr_per_day"] for f in factors if f["excused_by_policy"])
    every = sum(f["amount_inr_per_day"] for f in factors)
    return {
        "net_inr_per_day": round(net, 2),
        "factors": factors,
        # Removing an adverse (negative) factor lifts the team's figure toward
        # zero; removing a favourable one pushes it down. Same arithmetic.
        "policy_inr_per_day": round(net - excused, 2),
        "all_excused_inr_per_day": round(net - every, 2),
        "scaled_for_overlap": scale < 1.0,
        "note": ("Conditions warned in time are flagged, not excused: the team could "
                 "prepare. Only the accountable owner can excuse one, and it is recorded."),
    }


@app.post("/api/feedback")
def submit_feedback(payload: dict) -> dict:
    """Record one reader's judgement on one run.

    Recording is unconditional; *learning* from it is not. The response says
    which of the two happened, so a reader who submits a comment is not left
    believing they changed the engine.
    """
    required = ("run_id", "kpi_id", "judgement", "submitted_by")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise HTTPException(422, f"missing required field(s): {', '.join(missing)}")
    try:
        entry = new_feedback(
            run_id=str(payload["run_id"]),
            kpi_id=str(payload["kpi_id"]),
            persona=str(payload.get("persona", "analyst")),
            judgement=str(payload["judgement"]),
            submitted_by=str(payload["submitted_by"]),
            candidate_id=payload.get("candidate_id"),
            correction=payload.get("correction"),
            note=str(payload.get("note", "")),
            region=payload.get("region"),
            # "This was not worth flagging" is a judgement about a size, and
            # without the size an applied threshold could only move to a number
            # somebody typed. Sent by the console from the run it is judging.
            movement_inr=(
                float(payload["movement_inr"])
                if payload.get("movement_inr") not in (None, "") else None
            ),
        )
    except ValueError:
        raise HTTPException(
            422,
            f"unknown judgement; expected one of {[j.value for j in Judgement]}",
        ) from None

    _feedback.record(entry)
    return {
        "recorded": entry.as_dict(),
        "learned_from": entry.learnable,
        "note": (
            "this judgement can change a business input (candidate ranking, "
            "driver mapping, retrieval filter or a threshold) once it reaches "
            "quorum; it can never change a computed value"
            if entry.learnable
            else "recorded for audit only; this judgement class is not learned from"
        ),
        "summary": _feedback.summary(),
    }


@app.post("/api/feedback/apply")
def apply_feedback(payload: dict) -> dict:
    """Apply one proposal that has reached quorum, or refuse and say why.

    This is the step that turns a correction workflow into a loop that closes.
    Everything it changes is a business input; nothing it changes is a computed
    value; and what it writes is an audit record, not an edit to the contract.

    A person applies it. That is not decoration -- `applied_by` is required, is
    written into the record, and is shown beside the changed value for as long
    as it stands.
    """
    target = str(payload.get("target", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    applied_by = str(payload.get("applied_by", "")).strip()
    if not target or not subject:
        raise HTTPException(422, "target and subject are both required")
    if not applied_by:
        raise HTTPException(422, "applied_by is required; a change needs an author")

    found = next(
        (p for p in proposals(list(_feedback.all()))
         if p.target == target and p.subject == subject),
        None,
    )
    if found is None:
        raise HTTPException(404, f"no proposal for {target!r} on {subject!r}")

    reg = registry(_vertical(payload.get("industry")))
    try:
        contract = reg.get(found.subject)
    except KeyError:
        raise HTTPException(
            422,
            f"{found.subject!r} is not a metric in this industry's contract set, "
            f"so there is no threshold to move",
        ) from None

    try:
        change = apply_proposal(
            found,
            kpi_id=contract.kpi_id,
            current_value=contract.materiality.min_abs_delta_inr,
            movements=list(found.movements),
            applied_by=applied_by,
            store=_applied,
        )
    except ApplyRefused as exc:
        # 409 rather than 400: the request was well formed and the engine
        # declined it. The reason is the point, so it is the body.
        raise HTTPException(409, {"refused": str(exc), "target": target}) from None

    return {
        "applied": change.as_dict(),
        "effective": (
            "the next diagnosis reads the new floor; every past run is unchanged"
        ),
    }


@app.get("/api/feedback/applied")
def applied_feedback(kpi_id: str | None = None) -> dict:
    """What feedback has actually changed, and what it still cannot change."""
    return {
        "changes": [c.as_dict() for c in _applied.history(kpi_id)],
        "consumable": CONSUMABLE,
        "not_consumable": WHY_NOT,
    }


@app.get("/api/feedback")
def read_feedback(run_id: str | None = None) -> dict:
    """The loop's own state: what readers said, and what it would change."""
    if run_id:
        return {
            "run_id": run_id,
            "entries": [f.as_dict() for f in _feedback.for_run(run_id)],
        }
    return {
        **_feedback.summary(),
        "proposals": [
            # Whether the engine can consume this target travels with the
            # proposal. Without it the console offers "apply" on a proposal that
            # can only ever be refused, which reads as a broken button rather
            # than as a boundary.
            {**p.as_dict(), "consumable": p.target in CONSUMABLE,
             "why_not": WHY_NOT.get(p.target)}
            for p in proposals(list(_feedback.all()))
        ],
        "applied": [c.as_dict() for c in _applied.history()],
    }


# The console is one file with no build step and no hashed filename, so nothing
# tells a browser a new version exists. Heuristic caching then served a page from
# before a fix -- a refusal rendered by the old script on top of the new API --
# which is the worst moment to learn the fix is not what the reader sees.
# --- accountability: identity, sign-off, decisions, audit -------------------
#
# The engine drafts; a person decides. These endpoints record who decided what,
# on which evidence, into the hash-chained log in `whychain.audit`. Nothing here
# executes an action: accepting a decision card records the acceptance and
# nothing else, exactly as the card says.

_audit = AuditLog()


def _who(request: Request) -> Identity:
    who = request.scope.get("state", {}).get("identity")
    if who is None:  # only reachable if the middleware is removed
        raise HTTPException(401, "no identity on this request")
    return who


def _finding_run(body: dict, entitled: str | None) -> dict:
    """The deterministic run a signature or decision refers to, recomputed here.

    Recomputed rather than accepted from the browser, so what is recorded is
    what the engine finds now, not what a client says it found. Every parameter
    is passed, because FastAPI's defaults are objects when a handler is called
    as a function (B-040).
    """
    try:
        start = date.fromisoformat(str(body["start"]))
        end = date.fromisoformat(str(body["end"]))
    except (KeyError, ValueError):
        raise HTTPException(422, "start and end are required, as YYYY-MM-DD") from None
    return diagnose(
        kpi=str(body.get("kpi") or "net_revenue"), region=body.get("region") or None,
        channel=body.get("channel") or None, device=body.get("device") or None,
        category=body.get("category") or None, event_start=start, event_end=end,
        baseline_days=14, persona="analyst", entitled=entitled, price_delta=-0.05,
        horizon_days=14, backend="none", llm_model=None,
        industry=body.get("industry") or None,
    )


def _subject(run: dict, body: dict) -> dict:
    return {
        "industry": body.get("industry") or "retail",
        "kpi_id": run.get("kpi_id"),
        "region": run.get("region"),
        "slice": {k: body.get(k) for k in ("channel", "device", "category") if body.get(k)},
        "window": run.get("window"),
    }


@app.post("/api/demo/reset")
def demo_reset(request: Request) -> dict:
    """Start the demo clean: sign-offs, decisions and feedback moved aside.

    The same as `make demo-reset`, for a presenter with no terminal. Demo mode
    only: under single sign-on the audit trail is a record of real decisions and
    nothing in the product may reset it. Nothing is deleted. The files move to
    `data/archive/<time>/` with a note of who reset it, and the chain starts
    again from its genesis, which `verify` reads as intact.
    """
    if identity_mode() != "demo":
        raise HTTPException(403, "the audit trail cannot be reset under single sign-on")
    who = _who(request)
    stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")  # local, as make demo-reset names it
    dest = _ARCHIVE / stamp
    moved = []
    with _audit._lock:
        for path in (_audit.path, _feedback.path, _applied.path):
            if path.exists() and path.stat().st_size:
                dest.mkdir(parents=True, exist_ok=True)
                path.replace(dest / path.name)
                moved.append(path.name)
        if moved:
            (dest / "RESET.json").write_text(json.dumps(
                {"reset_by": who.as_dict(), "at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                 "moved": moved}, indent=2), encoding="utf-8")
    return {"archived_to": str(dest) if moved else None, "moved": moved}


@app.get("/api/me")
def me(request: Request) -> dict:
    """Who the console is acting as, how that was established, and who else it may be."""
    who = _who(request)
    return {
        "identity": who.as_dict(),
        "mode": identity_mode(),
        "demo_users": (
            [{"id": k, "name": n, "role": r} for k, (n, r) in DEMO_USERS.items()]
            if identity_mode() == "demo" else []
        ),
    }


@app.get("/api/trackrecord")
def trackrecord() -> dict:
    """How well the engine does what it does, from the last benchmark run.

    Read from the report `make bench` writes, never typed. The first thing an
    enterprise reader should be told is how often the tool is wrong.
    """
    path = Path("bench/report.json")
    if not path.exists():
        raise HTTPException(404, "no benchmark report; run make bench")
    report = json.loads(path.read_text(encoding="utf-8"))
    rates, counts = report.get("rates", {}), report.get("counts", {})
    fit = report.get("calibration_fit") or {}
    # Of the cases where the engine named a cause, how often the planted cause
    # was among those it verified. The planted cause is `<case_id>-cause`, by
    # the generator's own convention (datagen/bulk.py), and the report keeps the
    # verified list per case, so this is read, not re-scored. It is the figure a
    # reader who signs cares about: when it answers, is it right.
    cases = report.get("cases", [])
    named = [c for c in cases if c.get("verdict") == "explained"]
    truth = lambda c: f"{c['case_id']}-cause"  # noqa: E731
    exact = sum(1 for c in named if set(c.get("verified") or []) == {truth(c)})
    # The strict count, not the benchmark's per-case decoy rate: a decoy planted
    # for a neighbouring case in the same panel counts here too. The per-case
    # rate (87.5%) is correct as defined and reads as more than it is.
    decoy_through = sum(1 for c in named if any(v.endswith("-decoy") for v in c.get("verified") or []))
    noise = [c for c in cases if c.get("expected") == "no_anomaly"]
    return {
        "cases": counts.get("cases"),
        "noise_explained": rates.get("false_alarm_rate"),
        "decoys_rejected": rates.get("negative_control_rejection"),
        "true_cause_verified": rates.get("topk_accuracy"),
        "named_a_cause": len(named),
        "exactly_right": exact,
        "decoy_let_through": decoy_through,
        "noise_cases": len(noise),
        "noise_cases_explained": sum(1 for c in noise if c.get("verdict") == "explained"),
        "true_cause_first": rates.get("top1_accuracy"),
        "abstention_precision": rates.get("abstention_precision"),
        "abstention_recall": rates.get("abstention_recall"),
        "calibration_error": fit.get("ece_after"),
        "measured_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).date().isoformat(),
        "source": "bench/report.json, written by make bench",
    }


@app.post("/api/signoff")
def signoff(payload: dict, request: Request) -> dict:
    """Sign a finding. Only the metric's accountable owner may.

    Signing records the evidence fingerprint of a fresh deterministic run, so a
    later change to the data under the finding is detectable (see `GET`).
    """
    who = _who(request)
    vertical = _vertical(payload.get("industry"))
    contract = _contract(str(payload.get("kpi") or "net_revenue"), vertical)
    if who.role != contract.owner_role:
        raise HTTPException(403, {
            "refused": f"only {role(contract.owner_role)} signs a {label(contract.kpi_id)} finding",
            "accountable": contract.owner_role,
            "you": who.role,
        })
    run = _finding_run(payload, effective_entitlement(who, payload.get("entitled")))
    statement = {
        "explained": "The movement and its verified causes are accepted for reporting.",
        "unknown": "The movement is accepted as real and its cause as not yet established.",
        "contradicted": "The two systems disagree; the movement is not accepted as real.",
    }.get(str(run.get("verdict")), "Reviewed.")
    entry = _audit.append(
        "finding_signed", who.as_dict(), _subject(run, payload),
        {
            "verdict": run.get("verdict"),
            "statement": statement,
            "evidence": evidence_fingerprint(run),
            "run_id": run.get("run_id"),
            "note": str(payload.get("note") or "")[:500],
        },
    )
    return {"signed": entry, "chain": _audit.verify()}


@app.get("/api/signoff")
def signoff_status(
    request: Request,
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    start: date = Query(...),
    end: date = Query(...),
    channel: str | None = None,
    device: str | None = None,
    category: str | None = None,
    industry: str | None = None,
    entitled: str | None = None,
    evidence: str | None = Query(None, description="a diagnosis's evidence_fingerprint"),
    verify: bool = Query(False, description="re-run the diagnosis to check"),
) -> dict:
    """The latest signature on a finding, and whether its evidence still holds.

    Cheap by default: it reads the log. Pass `evidence` (the fingerprint a
    diagnosis response carries) and it says whether that matches what was
    signed; pass `verify=true` and it re-runs the diagnosis itself.
    """
    who = _who(request)
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)
    body = {"kpi": kpi, "region": region, "start": start.isoformat(), "end": end.isoformat(),
            "channel": channel, "device": device, "category": category, "industry": industry}
    # Entitlement still applies: a reader may not learn that a region they
    # cannot see was signed.
    _refuse_outside_scope(region, _entitlement_scope(effective_entitlement(who, entitled)),
                          contract.owner_role)
    subject = {
        "industry": industry or "retail", "kpi_id": contract.kpi_id, "region": region,
        "slice": {k: body[k] for k in ("channel", "device", "category") if body[k]},
        "window": {"from": body["start"], "to": body["end"]},
    }
    signed = [e for e in _audit.for_subject(**subject) if e["event"] == "finding_signed"]
    latest = signed[-1] if signed else None
    now = evidence
    if verify:
        now = evidence_fingerprint(_finding_run(body, effective_entitlement(who, entitled)))
    return {
        "signed": latest,
        "evidence_now": now,
        "unchanged": (latest["payload"]["evidence"] == now) if latest and now else None,
        "accountable": contract.owner_role,
    }


@app.post("/api/decision")
def decide(payload: dict, request: Request) -> dict:
    """Accept, modify or reject one decision card. Records; never executes.

    Only the role the card is assigned to may decide it. That is the decision
    right the contract already declares for the driver, enforced rather than
    printed.
    """
    who = _who(request)
    choice = str(payload.get("decision", "")).lower()
    if choice not in ("accept", "modify", "reject"):
        raise HTTPException(422, "decision must be accept, modify or reject")
    if choice == "modify" and not str(payload.get("note", "")).strip():
        raise HTTPException(422, "a modification needs a note saying what changes")
    run = _finding_run(payload, effective_entitlement(who, payload.get("entitled")))
    card = next((c for c in run.get("decisions", [])
                 if (c.get("approval") or {}).get("action_id") == payload.get("action_id")), None)
    if card is None:
        raise HTTPException(404, f"no decision card {payload.get('action_id')!r} on this finding")
    assigned = card["approval"]["assigned_to"]
    if who.role != assigned:
        raise HTTPException(403, {
            "refused": f"this decision belongs to {role(assigned)}",
            "assigned_to": assigned,
            "you": who.role,
        })
    entry = _audit.append(
        {"accept": "decision_accepted", "modify": "decision_modified",
         "reject": "decision_rejected"}[choice],
        who.as_dict(), _subject(run, payload),
        {
            "action_id": card["approval"]["action_id"],
            "action": card["action"],
            "expected_recovery_inr_per_day": card.get("expected_recovery_inr_per_day"),
            "note": str(payload.get("note") or "")[:500],
            "evidence": evidence_fingerprint(run),
            "executed": False,
        },
    )
    return {"recorded": entry}


@app.post("/api/adjustment")
def adjust_target(payload: dict, request: Request) -> dict:
    """Excuse conditions beyond the team's control from a finding's target.

    Only the metric's accountable owner may, only conditions the evidence marks
    as uncontrollable can be excused, and the adjustment is recorded with the
    evidence it rests on. Nothing about the finding itself changes.
    """
    who = _who(request)
    vertical = _vertical(payload.get("industry"))
    contract = _contract(str(payload.get("kpi") or "net_revenue"), vertical)
    if who.role != contract.owner_role:
        raise HTTPException(403, {
            "refused": f"only {role(contract.owner_role)} adjusts a {label(contract.kpi_id)} target",
            "accountable": contract.owner_role, "you": who.role,
        })
    run = _finding_run(payload, effective_entitlement(who, payload.get("entitled")))
    plan = fair_target(run)
    if plan and plan.get("withheld"):
        raise HTTPException(403, "a cause on this finding lies outside your entitlement")
    if not plan or not plan["factors"]:
        raise HTTPException(409, "nothing on this finding is beyond the team's control")
    wanted = set(payload.get("excuse") or [])
    allowed = {f["candidate_id"] for f in plan["factors"]}
    if not wanted or not wanted <= allowed:
        raise HTTPException(422, {"refused": "only conditions beyond the team's control can be excused",
                                  "excusable": sorted(allowed)})
    excused = [f for f in plan["factors"] if f["candidate_id"] in wanted]
    # A warned condition is excused only with a reason on the record: the
    # policy holds a team accountable for preparing for what it was told.
    if any(f["warned"] for f in excused) and not str(payload.get("note") or "").strip():
        raise HTTPException(422, "a condition the team was warned about needs a reason to be excused")
    amount = round(sum(f["amount_inr_per_day"] for f in excused), 2)
    entry = _audit.append(
        "target_adjusted", who.as_dict(), _subject(run, payload),
        {
            "excused": [{"candidate_id": f["candidate_id"], "amount_inr_per_day": f["amount_inr_per_day"],
                         "warned": f["warned"]} for f in excused],
            "net_inr_per_day": plan["net_inr_per_day"],
            "team_inr_per_day": round(plan["net_inr_per_day"] - amount, 2),
            "statement": "Conditions beyond the team's control excused from its target.",
            "evidence": evidence_fingerprint(run),
            "note": str(payload.get("note") or "")[:500],
        },
    )
    return {"recorded": entry}


@app.get("/api/audit")
def audit_log(
    kpi: str | None = None,
    region: str | None = None,
    industry: str | None = None,
) -> dict:
    """The accountability record, newest first, with the chain's integrity."""
    entries = _audit.entries()
    if kpi:
        entries = [e for e in entries if e["subject"].get("kpi_id") == kpi]
    if region:
        entries = [e for e in entries if e["subject"].get("region") == region]
    if industry:
        entries = [e for e in entries if e["subject"].get("industry") == industry]
    return {"entries": list(reversed(entries)), "chain": _audit.verify()}


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _card_span(start: str, end: str) -> str:
    """"13 to 15 Aug 2026", the way the decision view writes a window."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    tail = f"{b.day} {_MONTHS[b.month - 1]} {b.year}"
    if a == b:
        return tail
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day} to {tail}"
    return f"{a.day} {_MONTHS[a.month - 1]}{'' if a.year == b.year else f' {a.year}'} to {tail}"


_card_action = action_text


def _card_role(identifier: str) -> str:
    text = sentence_case(role(identifier).removeprefix("the "))
    return re.sub(r"^Ecommerce", "E-commerce", text)


def _adaptive_card(card: dict, run: dict, link: str, decided: dict | None = None) -> dict:
    """A Microsoft Teams Adaptive Card for one decision, in its current state.

    It said "awaiting approval" after the owner had accepted, so the manager
    reading it in Teams saw a decision still pending that was already taken.
    The state is read from the audit trail, the same record the page reads.
    """
    rec = card.get("expected_recovery_inr_per_day")
    verb = {"decision_accepted": "accepted", "decision_modified": "modified",
            "decision_rejected": "rejected"}.get((decided or {}).get("event", ""))
    heading = (f"Decision {verb} by {decided['actor']['name']}" if verb
               else "Decision awaiting approval")
    footer = ("Recorded in the WhyChain audit trail. Nothing was executed by WhyChain."
              if verb else "Drafted by WhyChain. Nothing executes until the owner approves.")
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "text": heading, "weight": "Bolder", "size": "Medium"},
            {"type": "TextBlock", "wrap": True, "text": _card_action(card["action"])},
            {"type": "FactSet", "facts": [
                {"title": "Verified cause", "value": sentence_case(card["cause"].split(": ", 1)[-1])},
                {"title": "Owner", "value": _card_role(card["approval"]["assigned_to"])},
                {"title": "Expected recovery",
                 "value": f"₹{_indian(rec)} a day" if rec is not None else "not computed"},
                {"title": "Finding", "value":
                    f"{sentence_case(label(run['kpi_id']))}, {run.get('region') or 'all regions'}, "
                    f"{_card_span(run['window']['from'], run['window']['to'])}"},
            ]},
            {"type": "TextBlock", "wrap": True, "isSubtle": True, "size": "Small", "text": footer},
        ],
        "actions": [{"type": "Action.OpenUrl", "title": "Review in WhyChain", "url": link}],
    }


def _indian(n: float) -> str:
    """24139 -> 24,139 and 1234567 -> 12,34,567: the page's grouping, not the West's."""
    whole = str(round(abs(n)))
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail]) if groups else tail


@app.post("/api/dispatch/teams")
def dispatch_teams(payload: dict, request: Request) -> dict:
    """Send a decision card to its owner in Microsoft Teams, or show what would be sent.

    Posts to the incoming webhook in `WHYCHAIN_TEAMS_WEBHOOK` when one is set.
    With none, returns the exact card and says it was not sent: the delivery is
    real code, and the page never claims a message left the building when it
    did not.
    """
    who = _who(request)
    run = _finding_run(payload, effective_entitlement(who, payload.get("entitled")))
    card = next((c for c in run.get("decisions", [])
                 if (c.get("approval") or {}).get("action_id") == payload.get("action_id")), None)
    if card is None:
        raise HTTPException(404, f"no decision card {payload.get('action_id')!r} on this finding")
    # The link is the address this request arrived on, or the public one the
    # deployment declares, so a card never points at a laptop's loopback.
    public = os.environ.get("WHYCHAIN_PUBLIC_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    window = run.get("window") or {}
    link = f"{public}/finding?" + urllib.parse.urlencode({k: v for k, v in {
        "kpi": run.get("kpi_id"), "region": run.get("region"), "start": window.get("from"),
        "end": window.get("to"), "industry": payload.get("industry")}.items() if v})
    decided = _decided(run, (card.get("approval") or {}).get("action_id"))
    content = _adaptive_card(card, run, link, decided)
    webhook = os.environ.get("WHYCHAIN_TEAMS_WEBHOOK", "").strip()
    sent, detail = False, "No Teams webhook is configured, so nothing was sent."
    if webhook:
        message = {"type": "message", "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive", "content": content}]}
        try:
            req = urllib.request.Request(
                webhook, data=json.dumps(message).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                sent, detail = 200 <= resp.status < 300, f"Teams answered HTTP {resp.status}."
        except Exception as exc:  # the reason is the answer
            detail = f"Teams could not be reached: {type(exc).__name__}."
        if sent:
            _audit.append("card_dispatched", who.as_dict(), _subject(run, payload),
                          {"action_id": card["approval"]["action_id"], "channel": "teams"})
    return {"sent": sent, "detail": detail, "card": content}


def _decided(run: dict, action_id: str | None) -> dict | None:
    """The latest decision recorded on this action for this finding, if any."""
    return next((e for e in reversed(_audit.entries())
                 if e["event"].startswith("decision_") and e["payload"].get("action_id") == action_id
                 and e["subject"].get("kpi_id") == run.get("kpi_id")
                 and e["subject"].get("region") == run.get("region")
                 and e["subject"].get("window") == run.get("window")), None)


def _change_request(card: dict, run: dict, link: str, decided: dict) -> dict:
    """The work item an accepted decision becomes in the owner's service desk.

    WhyChain decides nothing and executes nothing. Once the owner has accepted,
    the change itself is made where changes are made, under that system's own
    approvals, and the ticket carries back what the change desk needs: what to
    do, who owns it, why, what it is worth, how to tell it worked, and the
    audit entry and evidence it rests on, so the ticket can be checked against
    the finding rather than trusted.
    """
    rec = card.get("expected_recovery_inr_per_day")
    mon = card.get("monitoring") or {}
    verb = {"decision_accepted": "Accepted", "decision_modified": "Accepted with a change"}[decided["event"]]
    note = str(decided["payload"].get("note") or "").strip()
    return {
        "reference": f"WC-{decided['hash'][:8].upper()}",
        "type": "change_request",
        "title": _card_action(card["action"]),
        "assignee_role": _card_role(card["approval"]["assigned_to"]),
        "requested_by": decided["actor"]["name"],
        "decision": f"{verb} by {decided['actor']['name'].replace(' (demo)', '')} on "
                    f"{_card_span(decided['at'][:10], decided['at'][:10])}",
        "change_note": note or None,
        "reason": sentence_case(card["cause"].split(": ", 1)[-1]),
        "finding": (f"{sentence_case(label(run['kpi_id']))}, {run.get('region') or 'all regions'}, "
                    f"{_card_span(run['window']['from'], run['window']['to'])}"),
        "expected_recovery": f"₹{_indian(rec)} a day" if rec is not None else "not computed",
        "done_when": (f"No alert on {mon['threshold']}, watching {mon['watch']}"
                      if mon.get("threshold") and mon.get("watch") else None),
        "check_within": mon.get("window"),
        "evidence": {"audit_entry": decided["hash"],
                     "fingerprint": decided["payload"].get("evidence"), "link": link},
    }


@app.post("/api/dispatch/ticket")
def dispatch_ticket(payload: dict, request: Request) -> dict:
    """Raise the change request for a decision the owner has accepted.

    Posted as JSON to `WHYCHAIN_TICKET_WEBHOOK` (a service desk's inbound
    integration) when one is set; without one, the exact request is returned
    and the page says it was not raised. Only an accepted or modified decision
    becomes a ticket: a rejection is the end of it, and a pending one is still
    the owner's to make.
    """
    who = _who(request)
    run = _finding_run(payload, effective_entitlement(who, payload.get("entitled")))
    card = next((c for c in run.get("decisions", [])
                 if (c.get("approval") or {}).get("action_id") == payload.get("action_id")), None)
    if card is None:
        raise HTTPException(404, f"no decision card {payload.get('action_id')!r} on this finding")
    decided = _decided(run, card["approval"]["action_id"])
    if decided is None or decided["event"] == "decision_rejected":
        raise HTTPException(409, "only an accepted decision becomes a change request"
                            if decided else "the owner has not decided yet")
    public = os.environ.get("WHYCHAIN_PUBLIC_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    window = run.get("window") or {}
    link = f"{public}/finding?" + urllib.parse.urlencode({k: v for k, v in {
        "kpi": run.get("kpi_id"), "region": run.get("region"), "start": window.get("from"),
        "end": window.get("to"), "industry": payload.get("industry")}.items() if v})
    ticket = _change_request(card, run, link, decided)
    raised = next((e for e in reversed(_audit.entries()) if e["event"] == "ticket_raised"
                   and e["payload"].get("reference") == ticket["reference"]), None)
    if raised:
        return {"sent": True, "detail": f"Already raised by {raised['actor']['name']}.", "ticket": ticket}
    webhook = os.environ.get("WHYCHAIN_TICKET_WEBHOOK", "").strip()
    sent, detail = False, "No service desk is connected, so no ticket was raised."
    if webhook:
        try:
            req = urllib.request.Request(
                webhook, data=json.dumps(ticket).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                sent, detail = 200 <= resp.status < 300, f"The service desk answered HTTP {resp.status}."
        except Exception as exc:  # the reason is the answer
            detail = f"The service desk could not be reached: {type(exc).__name__}."
        if sent:
            _audit.append("ticket_raised", who.as_dict(), _subject(run, payload),
                          {"action_id": card["approval"]["action_id"], "reference": ticket["reference"]})
    return {"sent": sent, "detail": detail, "ticket": ticket}


@app.get("/api/metrics")
def metrics() -> PlainTextResponse:
    """Request counts and latency, in the format Prometheus scrapes."""
    return PlainTextResponse(METRICS.render())


_NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/")
@app.get("/finding")
def index() -> FileResponse:
    """The decision view: findings to act on, then one finding at a time."""
    return FileResponse(UI / "app.html", headers=_NO_CACHE)


@app.get("/login")
def login() -> FileResponse:
    """Sign-in: single sign-on in production, a choice of seat in the demo."""
    return FileResponse(UI / "login.html", headers=_NO_CACHE)


@app.get("/slide")
def slide() -> FileResponse:
    """One finding as a board-pack slide, laid out for print to PDF."""
    return FileResponse(UI / "slide.html", headers=_NO_CACHE)


@app.get("/uat")
def uat() -> FileResponse:
    """Acceptance checks that run in the browser against every scenario."""
    return FileResponse(UI / "uat.html", headers=_NO_CACHE)


@app.get("/workbench")
def workbench() -> FileResponse:
    """The analyst's workbench: every method section, the scenarios, the receipt."""
    return FileResponse(UI / "index.html", headers=_NO_CACHE)


@app.get("/kpi/{kpi_id}")
def kpi_page(kpi_id: str) -> FileResponse:
    """Serve the app for a deep link.

    A diagnosis someone can send to a colleague is worth more than one they have
    to describe how to reach, so the view has a real URL and the server hands
    back the app rather than a 404 for it.
    """
    return FileResponse(UI / "index.html", headers=_NO_CACHE)


if UI.exists():
    app.mount("/static", StaticFiles(directory=UI), name="static")
