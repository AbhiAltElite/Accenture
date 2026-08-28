"""Anomaly detection on the residual, not the raw series.

Revenue moves for reasons nobody needs telling about: it is higher at weekends,
it doubles before Diwali and collapses the day after. Detecting on raw values
means firing on all of that, which is how alerting earns the reputation it has.

So the series is decomposed into trend, seasonality and residual, and only the
residual is examined. A festival is absorbed into the seasonal component and
never reaches the detector.

Deviation is measured with the median and MAD rather than mean and standard
deviation, because a genuine shock in the history inflates the standard
deviation enough to hide the next one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import MSTL

from whychain.contracts import KPIContract
from whychain.detect.calendar import festival_factor
from whychain.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceStore,
    MethodClass,
    Provenance,
    Unit,
)

# 0.6745 is the 75th percentile of the standard normal: scaling the MAD by it
# makes the robust score comparable to a conventional z-score.
MAD_TO_SIGMA = 0.6745


@dataclass(frozen=True)
class Decomposition:
    """The series split into parts a reader can look at."""

    days: pd.Series
    observed: np.ndarray
    festival: np.ndarray
    trend: np.ndarray
    seasonal: np.ndarray
    residual: np.ndarray
    expected: np.ndarray       # trend + seasonality: what a normal day looks like
    band_low: np.ndarray
    band_high: np.ndarray
    robust_z: np.ndarray


@dataclass(frozen=True)
class Anomaly:
    day: date
    observed: float
    expected: float
    delta: float               # signed, in the metric's own unit
    robust_z: float
    direction: str             # "drop" or "spike"


def decompose(series: pd.DataFrame, periods: tuple[int, ...] = (7,)) -> Decomposition:
    """Split a daily series into calendar effect, trend, weekly rhythm and residual.

    Two deliberate choices, both there to stop the decomposition swallowing the
    event it is meant to reveal:

    The retail calendar is divided out first, from known festival dates, rather
    than estimated as an annual seasonal component. Three years of history gives
    only three observations per day-of-year, so an estimated annual pattern
    absorbs a single-year event into "what this month looks like".

    The trend window is held stiff over roughly four weeks. LOESS with the
    default window follows a sudden level shift, leaving a residual near zero
    exactly where the anomaly is; too long a window cannot track real growth and
    biases the end of the series instead. Four seasonal periods separates a
    week-long event from a year-long trend.
    """
    if len(series) < 60:
        raise ValueError(
            f"need at least 60 days to separate seasonality from noise, got {len(series)}"
        )

    values = series["value"].to_numpy(dtype=float)
    festival = festival_factor(series["d"])

    # Decompose in log space. Retail variation is proportional, not absolute: a
    # busy Saturday swings by more rupees than a quiet Tuesday for entirely
    # ordinary reasons. An additive decomposition leaves residual variance that
    # scales with the level, so every high-volume day looks anomalous and the
    # detector fires constantly. Working in logs makes the noise homoscedastic
    # and turns the residual into a proportional deviation, which is also what a
    # reader means by "down eight per cent".
    floor = max(values[values > 0].min() * 1e-3, 1e-9) if (values > 0).any() else 1e-9
    raw_log = np.log(np.maximum(values, floor))

    # How strongly this series actually responds to the retail calendar, fitted
    # rather than assumed. A configured calendar that the business does not
    # follow would otherwise inject the very anomalies it claims to remove: a
    # grocery chain and a B2B supplier see the same Diwali on the calendar and
    # completely different demand. The coefficient is clamped to sensible bounds
    # so a short or noisy series cannot produce a wild correction.
    beta = _festival_response(raw_log, festival)
    log_values = raw_log - beta * np.log(festival)

    usable = tuple(p for p in periods if len(series) > 2 * p) or (7,)
    trend_window = (4 * max(usable) + 1) | 1
    result = MSTL(log_values, periods=usable, stl_kwargs={"trend": trend_window}).fit()

    log_seasonal = (
        result.seasonal.sum(axis=1) if result.seasonal.ndim > 1 else np.asarray(result.seasonal)
    )
    log_trend = np.asarray(result.trend)
    log_residual = log_values - log_trend - log_seasonal

    median = float(np.median(log_residual))
    mad = float(np.median(np.abs(log_residual - median)))
    scale = mad / MAD_TO_SIGMA if mad > 0 else max(float(np.std(log_residual)), 1e-6)
    robust_z = (log_residual - median) / scale

    # Back to rupees for everything a reader sees, so the chart and the table
    # are in the metric's own unit rather than log points.
    calendar_effect = festival**beta
    expected = np.exp(log_trend + log_seasonal + median) * calendar_effect
    trend = np.exp(log_trend) * calendar_effect
    seasonal = expected - trend
    residual = values - expected
    band_low = expected * np.exp(-3.0 * scale)
    band_high = expected * np.exp(3.0 * scale)

    return Decomposition(
        days=series["d"],
        observed=values,
        festival=festival,
        trend=trend,
        seasonal=seasonal,
        residual=residual,
        expected=expected,
        band_low=band_low,
        band_high=band_high,
        robust_z=robust_z,
    )


def _festival_response(log_values: np.ndarray, festival: np.ndarray) -> float:
    """Least-squares coefficient of the log series on the log calendar curve.

    Returns 0.0 when the calendar is flat over the window, or when the series
    shows no calendar response at all, in which case nothing is removed.
    """
    x = np.log(festival)
    if np.allclose(x, 0.0):
        return 0.0
    # Detrend both sides crudely so a growth trend does not leak into the fit.
    xc = x - x.mean()
    yc = log_values - log_values.mean()
    denominator = float(xc @ xc)
    if denominator < 1e-12:
        return 0.0
    return float(np.clip((xc @ yc) / denominator, 0.0, 1.5))


def find_anomalies(decomposition: Decomposition, threshold: float) -> list[Anomaly]:
    flagged: list[Anomaly] = []
    for i, z in enumerate(decomposition.robust_z):
        if abs(z) < threshold:
            continue
        observed = float(decomposition.observed[i])
        expected = float(decomposition.expected[i])
        flagged.append(
            Anomaly(
                day=pd.Timestamp(decomposition.days.iloc[i]).date(),
                observed=observed,
                expected=expected,
                delta=observed - expected,
                robust_z=float(z),
                direction="drop" if z < 0 else "spike",
            )
        )
    return flagged


def material(anomalies: list[Anomaly], contract: KPIContract) -> list[Anomaly]:
    """Both materiality tests, as the contract defines them.

    Statistical significance alone surfaces clean but trivial movements. Rupee
    impact alone surfaces noise that happens to be large. The brief asks for
    both, and the contract is where the thresholds live.
    """
    return [a for a in anomalies if contract.materiality.is_material(a.delta, a.robust_z)]


def detect(
    series: pd.DataFrame,
    contract: KPIContract,
    store: EvidenceStore,
    query: str = "",
) -> tuple[Decomposition, list[Anomaly], list[Evidence]]:
    """Run detection and record what was found as evidence."""
    decomposition = decompose(series)
    candidates = find_anomalies(decomposition, contract.materiality.min_abs_robust_z)
    survivors = material(candidates, contract)

    evidence: list[Evidence] = []
    for anomaly in survivors:
        evidence.append(
            store.add(
                Evidence(
                    id=store.next_id(),
                    kind=EvidenceKind.ANOMALY,
                    claim=(
                        f"{contract.kpi_id} on {anomaly.day} was "
                        f"{abs(anomaly.delta):,.0f} {'below' if anomaly.delta < 0 else 'above'} "
                        f"the seasonally adjusted expectation."
                    ),
                    value=anomaly.robust_z,
                    unit=Unit.RATIO,
                    method="mstl_robust_z",
                    method_class=MethodClass.STATISTICAL,
                    provenance=Provenance(
                        source_id=contract.lineage.upstream[0].split(".")[0],
                        query=query or contract.calculation.canonical_sql,
                        row_count=len(series),
                    ),
                    run_id=store.run_id,
                    extra={
                        "day": anomaly.day.isoformat(),
                        "observed": anomaly.observed,
                        "expected": anomaly.expected,
                        "delta": anomaly.delta,
                        "direction": anomaly.direction,
                    },
                )
            )
        )
    return decomposition, survivors, evidence
