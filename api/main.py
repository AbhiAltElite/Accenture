"""HTTP service for the diagnosis console.

Thin by design: it resolves a contract, reads the series through the warehouse,
runs detection, and returns the result. No analysis happens here.
"""

from __future__ import annotations

import warnings
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from whychain.actions import decision_cards
from whychain.confidence import abstain, explained_movement, score
from whychain.contracts import ContractError, ContractRegistry
from whychain.corroborate import corroborate, scan
from whychain.decompose import compute_bridge, contribution_by
from whychain.decompose.bridge import BridgeError
from whychain.detect import decompose, find_anomalies, material
from whychain.evidence import MethodClass
from whychain.ingest import DEFAULT_WAREHOUSE, IngestError, Warehouse
from whychain.telemetry import Telemetry
from whychain.verify import filter_relevant, from_operations, from_promotions, verify
from whychain.verify.tests import PLACEBO_WINDOWS

# statsmodels warns about period length on short slices; the guard is in decompose().
warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")

app = FastAPI(title="WhyChain", docs_url="/api/docs")
UI = Path("ui")

_registry: ContractRegistry | None = None
_retriever: object | None = None
_retriever_rows: int = 0


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


def _snapshot() -> tuple:
    """What the cached answers are answers about.

    T-06 requires a cache key to carry the data snapshot, the contract version
    and the entitlement context. The first two are here; entitlement is folded in
    by callers that have one, and until a caller does, nothing entitlement-scoped
    may be cached through this. A key that omits any of the three can serve one
    reader another reader's rows, which the same trap calls a P0.
    """
    try:
        stamp = DEFAULT_WAREHOUSE.stat().st_mtime_ns
    except OSError:
        stamp = 0
    return (stamp, tuple(sorted((c.kpi_id, c.version) for c in registry())))


def _cached(key: tuple, build):
    """Memoise against the current snapshot.

    The warehouse is read-only and only `make gen` changes it, so recomputing a
    three-year series on every request re-derives an answer that cannot have
    moved. Entries for a previous snapshot are dropped rather than served.
    """
    snapshot = _snapshot()
    hit = _series_cache.get(key)
    if hit is not None and hit[0] == snapshot:
        return hit[1]
    value = build()
    _series_cache[key] = (snapshot, value)
    return value


def registry() -> ContractRegistry:
    global _registry
    if _registry is None:
        try:
            _registry = ContractRegistry.from_directory("contracts")
        except ContractError as exc:
            raise HTTPException(500, f"contracts failed to load: {exc}") from exc
    return _registry


@app.get("/api/health")
def health() -> dict:
    try:
        with Warehouse() as wh:
            rows = len(wh.table("pos_txn", limit=1))
        return {"status": "ok", "warehouse": "connected", "contracts": len(registry()), "rows": rows}
    except IngestError as exc:
        return {"status": "degraded", "detail": str(exc)}


@app.get("/api/kpis")
def kpis() -> list[dict]:
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
        for c in registry()
    ]


@app.get("/api/overview")
def overview(region: str | None = None, days: int = Query(90, ge=30, le=730)) -> dict:
    """Every KPI at once, with its current state and how the graph connects them.

    A dropdown asks the reader to already know which metric moved. The point of a
    KPI graph is that they usually do not, and that a break in one shows up in
    its children.
    """
    reg = registry()
    try:
        with Warehouse() as wh:
            rows = []
            for contract in reg:
                try:
                    raw = _cached(
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
                if len(frame) < 60:
                    continue
                try:
                    # MSTL over three years is the other half of the cost, and it
                    # is a pure function of the frame it is given.
                    d = _cached(
                        ("decompose", contract.kpi_id, region),
                        lambda f=frame: decompose(f),
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


@app.get("/api/document/{doc_id}")
def document(doc_id: str) -> dict:
    """The full source record behind a citation.

    A quotation with a character range is only checkable if the reader can open
    the document and see the range in place.
    """
    try:
        with Warehouse() as wh:
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
) -> dict:
    contract = _contract(kpi)

    try:
        with Warehouse() as wh:
            raw = _cached(
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
        decomposition = decompose(frame)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

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
        "observed": [round(float(v), 2) for v in decomposition.observed[idx]],
        "expected": [round(float(v), 2) for v in decomposition.expected[idx]],
        "band_low": [round(float(v), 2) for v in decomposition.band_low[idx]],
        "band_high": [round(float(v), 2) for v in decomposition.band_high[idx]],
        "festival": [round(float(v), 3) for v in decomposition.festival[idx]],
        "robust_z": [round(float(v), 2) for v in decomposition.robust_z[idx]],
        "anomalies": [
            {
                "day": a.day.isoformat(),
                "observed": round(a.observed, 2),
                "expected": round(a.expected, 2),
                "delta": round(a.delta, 2),
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
        frame = parts[[time_col, "value"]]
    else:
        grouped = raw.groupby(time_col, as_index=False)["value"]
        frame = grouped.mean() if aggregation == "mean" else grouped.sum()

    return frame.rename(columns={time_col: "d"}).sort_values("d").reset_index(drop=True)


def _contract(kpi: str):
    try:
        return registry().get(kpi)
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
) -> dict:
    """Split a movement into price, volume and mix, and locate it by dimension.

    The baseline is the period immediately before the movement, normalised to a
    daily rate so a fortnight can be compared against a week.
    """
    contract = _contract(kpi)  # 404s on an unknown metric before touching the warehouse

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
        with Warehouse() as wh:
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
) -> dict:
    """Every candidate cause in the record, and whether it survives testing.

    Candidates arrive from the operational data with nothing marking which are
    real. Ranking them by association would promote whatever happened to
    coincide; that is exactly what the tests exist to prevent.
    """
    contract = _contract(kpi)
    try:
        with Warehouse() as wh:
            panel = wh.bridge_facts(
                contract, since=_lookback(event_start, 14), until=event_end
            )
            documents = wh.table("voice_ops")
            plan = wh.table("plan_ops")
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    found = from_operations(documents, event_start, event_end) + from_promotions(
        plan, event_start, event_end
    )
    all_regions = tuple(sorted(panel["region"].unique()))

    # `region` narrows which candidates are worth reporting, never the panel they
    # are tested against. Difference-in-differences needs the unexposed regions
    # to compare with, so filtering the data here would remove the control group
    # and quietly turn every verdict into CANNOT_VERIFY.
    if region:
        if region not in all_regions:
            raise HTTPException(404, f"no data for region {region!r}")
        found = [
            c for c in found
            if not c.exposed_regions or region in c.exposed_regions
        ]

    verified, rejected, untestable = [], [], []
    for candidate in found:
        v = verify(candidate, panel, all_regions)
        corr = corroborate(candidate, documents,
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
                        "issue": e.issue.value,
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


@app.get("/api/diagnose")
def diagnose(
    kpi: str = Query("net_revenue"),
    region: str | None = None,
    event_start: date = Query(..., alias="start"),
    event_end: date = Query(..., alias="end"),
    baseline_days: int = Query(14, ge=7, le=90),
) -> dict:
    """The whole pipeline for one movement: decompose, test, corroborate, score.

    Returns either a diagnosis or an abstention. Never both, and never a
    best guess dressed as the former.
    """
    contract = _contract(kpi)
    if contract.decomposition.method != "pvm":
        raise HTTPException(
            422,
            f"{kpi} is measured in {contract.unit.value} and cannot be "
            "decomposed by the price/volume/mix identity, so a full diagnosis "
            "is not yet available for it. Detection and freshness are.",
        )

    run_id = f"run-{uuid4().hex[:10]}"
    tel = Telemetry(run_id=run_id)

    try:
        with tel.stage("read", MethodClass.DETERMINISTIC), Warehouse() as wh:
            panel = wh.bridge_facts(
                contract,
                since=_lookback(event_start, baseline_days),
                until=event_end,
            )
            documents = wh.table("voice_ops")
            plan = wh.table("plan_ops")
            sources = wh.freshness(contract)
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

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
        from_operations(documents, event_start, event_end)
        + from_promotions(plan, event_start, event_end),
        event_start, event_end, region,
    )
    with tel.stage("verify", MethodClass.CAUSAL) as t:
        verifications = [verify(c, panel, all_regions) for c in found]
        t.note = f"{len(found)} candidates tested"

    with tel.stage("corroborate", MethodClass.RETRIEVAL) as t:
        shared = ticket_retriever(documents)
        corroborations = {
            c.candidate_id: corroborate(c, documents, retriever=shared, index=False)
            for c in found
        }
        # Retrieval and span extraction, not a model call. When the extractor
        # behind this protocol becomes model-backed, the count it records here
        # is what the receipt reports; nothing else changes.
        t.note = "tf-idf retrieval with deterministic span extraction"

    supporting = sum(
        corroborations[v.candidate.candidate_id].support_count
        for v in verifications
        if v.state.value == "verified"
    )
    with tel.stage("confidence", MethodClass.STATISTICAL):
        explained, per_cause = explained_movement(
            verifications, panel, event_start, event_end, baseline_days,
            total_movement=bridge.total_change,
        )
        confidence = score(
            verifications, explained=explained, total_movement=bridge.total_change,
            supporting_documents=supporting, sources=sources,
        )

    with tel.stage("actions", MethodClass.DETERMINISTIC) as t:
        cards = decision_cards(
            verifications, per_cause, contract, confidence.band.value
        )
        t.note = f"{len(cards)} decision card(s), every field derived"

    stale = tuple(f"{f.source_id} is stale by {f.lag}" for f in sources.values()
                  if not f.sla_met)
    result = {
        "kpi_id": kpi,
        "run_id": run_id,
        "region": region,
        "decisions": [c.as_dict() for c in cards],
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
            "per_cause": {k: round(v2, 2) for k, v2 in per_cause.items()},
        },
        "confidence": {
            "score": confidence.score,
            "band": confidence.band.value,
            "components": [
                {"name": c.name, "value": round(c.value, 3), "detail": c.detail}
                for c in confidence.components
            ],
            "reasons": list(confidence.reasons),
        },
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
                "issue": next(
                    (e.issue.value for e in
                     corroborations[v.candidate.candidate_id].supporting), None
                ),
                "citations": [
                    {"doc_id": e.doc_id, "span": list(e.span), "quote": e.quote,
                     "issue": e.issue.value, "flags": list(e.flags)}
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

    # Last, so the receipt covers every stage that actually ran.
    result["telemetry"] = tel.receipt()
    return result


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
