"""HTTP service for the diagnosis console.

Thin by design: it resolves a contract, reads the series through the warehouse,
runs detection, and returns the result. No analysis happens here.
"""

from __future__ import annotations

import warnings
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from whychain.contracts import ContractError, ContractRegistry
from whychain.detect import decompose, find_anomalies, material
from whychain.ingest import IngestError, Warehouse

# statsmodels warns about period length on short slices; the guard is in decompose().
warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")

app = FastAPI(title="WhyChain", docs_url="/api/docs")
UI = Path("ui")

_registry: ContractRegistry | None = None


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
            raw = wh.kpi_series(contract)
            freshness = wh.freshness(contract)
    except IngestError as exc:
        raise HTTPException(503, str(exc)) from exc

    for column, value in (("region", region), ("channel", channel), ("device", device)):
        if value and column in raw.columns:
            raw = raw[raw[column] == value]
    if raw.empty:
        raise HTTPException(404, "no data for that slice")

    time_col = raw.columns[0]
    frame = raw.groupby(time_col, as_index=False)["value"].sum().sort_values(time_col)
    frame = frame.rename(columns={time_col: "d"})

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
        "unit": "INR" if contract.kpi_id != "checkout_conversion" else "ratio",
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


def _contract(kpi: str):
    try:
        return registry().get(kpi)
    except ContractError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI / "index.html")


if UI.exists():
    app.mount("/static", StaticFiles(directory=UI), name="static")
