"""HTTP service for the diagnosis console.

Thin by design: it resolves a contract, reads the series through the warehouse,
runs detection, and returns the result. No analysis happens here.
"""

from __future__ import annotations

import json
import warnings
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from whychain import verticals
from whychain.actions import decision_cards, simulate
from whychain.confidence import abstain, explained_movement, score
from whychain.confidence.calibrate import Calibration
from whychain.contracts import ContractError, ContractRegistry
from whychain.corroborate import corroborate, scan
from whychain.corroborate.model_extract import ModelExtractor
from whychain.corroborate.query import ModelQueryWriter
from whychain.decompose import compute_bridge, contribution_by
from whychain.decompose.bridge import BridgeError
from whychain.detect import decompose_for, find_anomalies, material
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
from whychain.ingest import IngestError, Warehouse
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
from whychain.narrate.writer import ModelWriter
from whychain.personas import Persona, project
from whychain.rank import rank
from whychain.signalgap import PRECEDENT_LOOKBACK_DAYS, find_gap
from whychain.signalgap.gap import read_signals
from whychain.telemetry import Telemetry
from whychain.verify import filter_relevant, from_operations, from_promotions, verify
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
UI = Path("ui")

_retriever: object | None = None
_retriever_rows: int = 0
_feedback = FeedbackStore()
_applied = AppliedStore()
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
    record that describes those is external and public — an IMD cyclone warning
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
    days: int = Query(90, ge=30, le=730),
    industry: str | None = Query(None, description="which industry to read"),
) -> dict:
    """Every KPI at once, with its current state and how the graph connects them.

    A dropdown asks the reader to already know which metric moved. The point of a
    KPI graph is that they usually do not, and that a break in one shows up in
    its children.
    """
    vertical = _vertical(industry)
    reg = registry(vertical)
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
                if region and "region" in raw.columns:
                    raw = raw[raw["region"] == region]
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
                        ("decompose", contract.kpi_id, region),
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
            "roots": reg.roots()}


@app.get("/api/triage")
def triage(
    limit: int = Query(12, ge=1, le=50),
    region: str | None = Query(None, description="a single region, or every one"),
    days: int | None = Query(None, ge=30, le=3650,
                             description="how far back to queue findings from"),
    entitled: str | None = Query(None, description="comma-separated regions"),
    industry: str | None = Query(None, description="which industry to read"),
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
    regions = list(scope) if scope else ["North", "South", "East", "West"]
    # A region the reader picked narrows the queue; entitlement still bounds it,
    # so asking for a region outside the grant returns nothing rather than
    # widening the scope back out.
    if region:
        regions = [r for r in regions if r == region]
    findings: list[dict] = []
    try:
        with warehouse(vertical) as wh:
            for contract in reg:
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

                for region_id in regions:
                    scoped = (
                        raw[raw["region"] == region_id]
                        if "region" in raw.columns else raw
                    )
                    if scoped.empty:
                        continue
                    frame = _roll_up(scoped, contract)
                    try:
                        d = _cached(
                            vertical,
                            ("decompose", contract.kpi_id, region_id),
                            lambda f=frame, c=contract: decompose_for(f, c),
                        )
                    except ValueError:
                        continue

                    flagged = material(
                        find_anomalies(d, contract.materiality.min_abs_robust_z),
                        contract,
                    )
                    drops = sorted(
                        (a for a in flagged if a.direction == "drop"),
                        key=lambda a: a.day,
                    )
                    findings.extend(_episodes(drops, contract, region_id))
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    # The window the rail is showing. Without it the queue answered over the
    # whole three years while the figures beside it answered over ninety days,
    # and the two disagreed on screen about how much was wrong with the
    # business. "Now" is the last day the warehouse actually holds rather than
    # the wall clock, because the wall clock is not where this data lives and a
    # window measured against it would be empty.
    if days and findings:
        latest = max(f["end"] for f in findings)
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
        worst = min(run, key=lambda a: a.delta)
        total = sum(abs(a.delta) for a in run)
        out.append({
            "kpi_id": contract.kpi_id,
            "unit": contract.unit.value,
            "owner_role": contract.owner_role,
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
def document(doc_id: str, industry: str | None = Query(None)) -> dict:
    """The full source record behind a citation.

    A quotation with a character range is only checkable if the reader can open
    the document and see the range in place.
    """
    vertical = _vertical(industry)
    try:
        with warehouse(vertical) as wh:
            docs = wh.table("voice_ops")
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    match = docs[docs["doc_id"] == doc_id]
    if match.empty:
        raise HTTPException(404, f"no document {doc_id}")
    row = match.iloc[0]
    text = str(row["text"])
    return {
        "doc_id": doc_id,
        "doc_type": str(row["doc_type"]),
        "source_id": "voice_ops",
        "ts": pd.Timestamp(row["ts"]).isoformat(),
        "region": str(row["region"]),
        "text": text,
        "length": len(text),
        # Stated rather than assumed: the reader is being shown untrusted text.
        "injection_flags": list(scan(text)),
    }


@app.get("/api/series")
def series(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    channel: str | None = None,
    device: str | None = None,
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    industry: str | None = Query(None, description="which industry to read"),
) -> dict:
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)

    try:
        with warehouse(vertical) as wh:
            raw = _cached(
                vertical,
                ("kpi_series", contract.kpi_id),
                lambda: wh.kpi_series(contract),
            )
            # Freshness is a clock reading, not a derived series: never cached.
            freshness = wh.freshness(contract)
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    for column, value in (("region", region), ("channel", channel), ("device", device)):
        if value and column in raw.columns:
            raw = raw[raw[column] == value]
    if raw.empty:
        raise HTTPException(404, "no data for that slice")

    frame = _roll_up(raw, contract)

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


@app.get("/api/decomposition")
def decomposition(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    event_start: date = Query(..., alias="start"),
    event_end: date = Query(..., alias="end"),
    baseline_days: int = Query(14, ge=7, le=90),
    industry: str | None = Query(None, description="which industry to read"),
) -> dict:
    """Split a movement into price, volume and mix, and locate it by dimension.

    The baseline is the period immediately before the movement, normalised to a
    daily rate so a fortnight can be compared against a week.
    """
    vertical = _vertical(industry)
    contract = _contract(kpi, vertical)  # 404s on an unknown metric before touching the warehouse

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

    if region:
        panel = panel[panel["region"] == region]
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
    for dim in dimensions:
        if region and dim == "region":
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
        documents, event_start, event_end, vocabulary=vertical.corpus.vocabulary
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
        if scope is not None and region not in scope:
            raise HTTPException(
                403,
                {
                    "error": "outside your entitlement",
                    "requested_region": region,
                    "entitled_regions": list(scope),
                    "escalate_to": contract.owner_role,
                    "detail": (
                        f"You are entitled to "
                        f"{', '.join(scope) if scope else 'no regions'} and asked "
                        f"about {region}. Nothing was computed. Escalate to "
                        f"{contract.owner_role} for access."
                    ),
                },
            )
        found = [
            c for c in found
            if not c.exposed_regions or region in c.exposed_regions
        ]

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
            "scope": {k: v2 for k, v2 in
                      (("channel", candidate.channel), ("device", candidate.device),
                       ("category", candidate.category)) if v2},
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


@app.get("/api/diagnose")
def diagnose(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
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
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    # Refused before anything is computed, rather than computed and scrubbed on
    # the way out. See the note on the same guard in `candidates`: this shape of
    # answer carries the same figure in a contribution table, a scenario
    # estimate, a narrative sentence and a per-cause map, and each has to be
    # found and removed separately. Refusing the question removes the class.
    if region and scope is not None and region not in scope:
        raise HTTPException(
            403,
            {
                "error": "outside your entitlement",
                "requested_region": region,
                "entitled_regions": list(scope),
                "escalate_to": contract.owner_role,
                "detail": (
                    f"You are entitled to "
                    f"{', '.join(scope) if scope else 'no regions'} and asked "
                    f"about {region}. Nothing was computed. Escalate to "
                    f"{contract.owner_role} for access."
                ),
            },
        )

    scoped = panel[panel["region"] == region] if region else panel
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
    try:
        with tel.stage("decompose", MethodClass.DETERMINISTIC):
            bridge = compute_bridge(base, current)
    except BridgeError as exc:
        raise HTTPException(422, str(exc)) from exc

    all_regions = tuple(sorted(panel["region"].unique()))
    found, set_aside = filter_relevant(
        from_operations(
            documents, event_start, event_end, vocabulary=vertical.corpus.vocabulary
        )
        + from_promotions(plan, event_start, event_end, vertical.plan),
        event_start, event_end, region,
    )

    with tel.stage("rank", MethodClass.STATISTICAL) as t:
        # The scoping dimension is excluded. With a region selected, the
        # "region = West" slice *is* the total, so it tops the ranking at a
        # 100% share and says nothing; a row that is true, useless, and
        # displaces a real contributor out of the list.
        contributions = [
            contribution_by(base, current, dim)
            for dim in contract.grain.dims
            if dim in base.columns and not (region and dim == "region")
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
            f"track A: {len(ranking.exact)} exact contribution(s); "
            f"track B: {len(ranking.associational)} associational, none stateable"
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
        t.note = f"{len(cards)} decision card(s), every field derived"

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
            f"verdict {gap.verdict.value}, {gap.recurrence} prior episode(s), "
            f"{gap.recurrence_that_hurt} of which moved the metric"
        )

    stale = tuple(f"{f.source_id} is stale by {f.lag}" for f in sources.values()
                  if not f.sla_met)
    result = {
        "kpi_id": kpi,
        "run_id": run_id,
        "region": region,
        "decisions": [c.as_dict() for c in cards],
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
            "overlap": round(overlap, 3),
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
        "set_aside": [
            {"candidate_id": c.candidate_id, "reason": why} for c, why in set_aside
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
                "scope": {k: val for k, val in
                          (("channel", v.candidate.channel), ("device", v.candidate.device),
                           ("category", v.candidate.category)) if val},
            }
            for v in verifications
            if v.state.value == "verified"
        ],
    }

    if confidence.abstained:
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
            f"{story.writer}; {len(story.sentences)} sentence(s) accepted, "
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
    return projected


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI / "index.html")


@app.get("/kpi/{kpi_id}")
def kpi_page(kpi_id: str) -> FileResponse:
    """Serve the app for a deep link.

    A diagnosis someone can send to a colleague is worth more than one they have
    to describe how to reach, so the view has a real URL and the server hands
    back the app rather than a 404 for it.
    """
    return FileResponse(UI / "index.html")


if UI.exists():
    app.mount("/static", StaticFiles(directory=UI), name="static")
