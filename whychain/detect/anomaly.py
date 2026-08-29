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

Two things about this module are set by the *contract*, not by a default, and
both are here because getting them from a default was wrong. The seasonal
periods are the rhythms the series actually carries, which depend on its time
grain. And for a rate, the width of the noise depends on how many observations
the rate was estimated from, so the scale is per-observation rather than global.
Callers should reach for `decompose_for`, which reads both off the contract.
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

# The rhythms a series carries, by the time grain its contract declares.
#
# The old default of (7,) was written for daily data, where 7 means "day of
# week". Applied to an hourly contract it asks MSTL to fit a seven-*hour* cycle:
# a period with no physical meaning, which beats against the real 24-hour day on
# a 168-hour cycle and leaves the intraday shape sitting in the residual for the
# detector to find. That is T-19 once more, a constant derived at one grain
# applied at another, which is why the periods now come from the contract.
#
# Hourly fits the trading day and stops there. Adding the 168-hour week is the
# obvious next term and it was measured rather than assumed: on three years of
# West checkout conversion it moved the flag rate from 0.35% to 0.30% against a
# nominal 0.27%, and took the decomposition from 0.50s to 10.23s — twenty times
# the cost, per region, for eleven flags in 20,824 observations. Objective 8
# names latency as a constraint the engine has to work inside, and a landing
# page that takes forty seconds to compose itself is not working inside it.
#
# The weekly term is small here for a reason worth stating: this is a *rate*.
# Its level barely moves across the day at all (4.14% at 07:00 against 4.40% at
# midnight) while the session volume behind it swings twentyfold, and volume is
# handled by the noise model below rather than by a seasonal term. A daily
# revenue series, where the weekly rhythm is the dominant shape, still gets it.
SEASONAL_PERIODS: dict[str, tuple[int, ...]] = {
    "hour": (24,),       # the trading day
    "day": (7,),         # day of week
    "week": (52,),       # week of year
}

# Four full cycles of the longest rhythm, and never fewer than sixty
# observations. Stated in the series' own units: sixty *days* of hourly data is
# 1,440 rows, and sixty rows of it is two and a half days.
MIN_CYCLES = 4
MIN_OBSERVATIONS = 60


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
    # Per observation, not a single number. For a rate estimated from a varying
    # number of trials, how far a reading can drift for no reason at all depends
    # on how many trials there were, so the band is wider on a thin hour than a
    # busy one and the chart shows that honestly.
    scale: np.ndarray


@dataclass(frozen=True)
class Anomaly:
    day: date
    observed: float
    expected: float
    delta: float               # signed, in the metric's own unit
    robust_z: float
    direction: str             # "drop" or "spike"


def decompose(
    series: pd.DataFrame,
    periods: tuple[int, ...] = (7,),
    denominator: pd.Series | np.ndarray | None = None,
    grain: str = "day",
    proportion: bool = False,
    noise_model: str = "binomial",
) -> Decomposition:
    """Split a series into calendar effect, trend, seasonal rhythm and residual.

    `periods` are the seasonal cycles in *observations*, so they only mean
    anything alongside the grain the observations are on; `grain` names that
    unit so the history requirement can be stated in it. `denominator` is the
    trial count behind each reading of a rate, which is what makes one hour's
    four per cent a firmer number than another's, and `proportion` says whether
    that rate is a share of trials or an average over them, because the two
    have different noise, and `noise_model` says which of the two rate forms
    applies. `decompose_for` reads all five off a contract, and is what callers
    should use.

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
    usable = tuple(p for p in periods if len(series) > 2 * p) or (min(periods),)
    minimum = max(MIN_OBSERVATIONS, MIN_CYCLES * max(usable))
    if len(series) < minimum:
        raise ValueError(
            f"need at least {minimum} {grain}s to separate seasonality from "
            f"noise, got {len(series)}"
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
    #
    # A rate of exactly zero has no logarithm, and flooring it makes every empty
    # period a guaranteed extreme outlier: all 226 hours in which West took no
    # checkout conversions at all were flagged, though at a 4.3% rate over about
    # fifty sessions an empty hour is simply what happens roughly one time in
    # nine. Where the trial count is known, the half-count (Jeffreys) estimate
    # gives the reading a finite logarithm without moving a well-populated one.
    # It is applied only to the series being fitted: `observed` stays the rate
    # that actually occurred, because that is the number a reader is shown.
    fitted = values
    trials = None
    if denominator is not None:
        trials = np.asarray(denominator, dtype=float)
        fitted = (values * trials + 0.5) / (trials + 1.0)

    floor = max(fitted[fitted > 0].min() * 1e-3, 1e-9) if (fitted > 0).any() else 1e-9
    raw_log = np.log(np.maximum(fitted, floor))

    # How strongly this series actually responds to the retail calendar, fitted
    # rather than assumed. A configured calendar that the business does not
    # follow would otherwise inject the very anomalies it claims to remove: a
    # grocery chain and a B2B supplier see the same Diwali on the calendar and
    # completely different demand. The coefficient is clamped to sensible bounds
    # so a short or noisy series cannot produce a wild correction.
    beta = _festival_response(raw_log, festival)
    log_values = raw_log - beta * np.log(festival)

    trend_window = (MIN_CYCLES * max(usable) + 1) | 1
    result = MSTL(log_values, periods=usable, stl_kwargs={"trend": trend_window}).fit()

    log_seasonal = (
        result.seasonal.sum(axis=1) if result.seasonal.ndim > 1 else np.asarray(result.seasonal)
    )
    log_trend = np.asarray(result.trend)
    log_residual = log_values - log_trend - log_seasonal

    median = float(np.median(log_residual))
    mad = float(np.median(np.abs(log_residual - median)))
    fitted_scale = mad / MAD_TO_SIGMA if mad > 0 else max(float(np.std(log_residual)), 1e-6)

    # Back to the metric's own unit for everything a reader sees, so the chart
    # and the table are in rupees or points rather than log points.
    calendar_effect = festival**beta
    expected = np.exp(log_trend + log_seasonal + median) * calendar_effect
    trend = np.exp(log_trend) * calendar_effect
    seasonal = expected - trend
    residual = values - expected

    scale = fitted_scale * _noise_profile(trials, expected, proportion, noise_model)
    robust_z = (log_residual - median) / scale
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
        scale=scale,
    )


def _noise_profile(
    trials: np.ndarray | None,
    expected: np.ndarray,
    proportion: bool,
    noise_model: str = "binomial",
) -> np.ndarray:
    """How much wider or narrower each observation's noise is than the typical one.

    A rate read off fifty sessions and one read off nine hundred are not equally
    certain, but a single MAD calibrates to the typical volume and then judges
    both against it. The quiet periods flag constantly as a result: on West
    checkout conversion the thinnest decile of hours fired at 14.4% against
    about 5% for the busiest, which is a statement about session counts and not
    about checkout.

    The correction is the standard error of the rate in log space, normalised so
    the median observation keeps exactly the scale the MAD already fitted. Busy
    periods are then held to a tighter band and thin ones to a wider one, and
    the overall calibration is unchanged rather than loosened — which is the
    difference between this and simply raising the z threshold, where every
    period gets a wider band and the real movements in the quiet ones are lost
    along with the noise.

    Which standard error depends on what kind of rate it is, and the contract
    says. An **average** over n items, such as order value, has error in
    `1 / sqrt(n)`; its coefficient of variation is a constant the MAD has
    already absorbed. Deciding this by looking at the numbers instead would mean
    reading 447 rupees as a probability, which is how a clamp turns a wrong
    model into a silent one.

    A **rate** takes one of the two forms the contract's `noise_model` names.
    `binomial`, `sqrt((1 - p) / (n * p))`, is right when the numerator is a
    subset of the denominator, and its variance correctly falls away as the rate
    approaches one. `counting`, `sqrt(1 / (n * p))`, is right when the numerator
    is measured separately and keeps its own variance however high the rate
    runs. Below about a tenth they agree; near one they differ by a factor of
    `1 / sqrt(1 - p)`, which at 91% is three and a half.

    Returns a flat 1.0 when there is no trial count to weight by, which is every
    metric that is a sum rather than a rate.
    """
    if trials is None:
        return np.ones(len(expected))
    n = np.maximum(np.asarray(trials, dtype=float), 1e-9)
    if proportion:
        p = np.clip(np.asarray(expected, dtype=float), 1e-9, 1.0 - 1e-9)
        headroom = (1.0 - p) if noise_model == "binomial" else 1.0
        relative_se = np.sqrt(headroom / (n * p))
    else:
        relative_se = 1.0 / np.sqrt(n)
    typical = float(np.median(relative_se))
    if not np.isfinite(typical) or typical <= 0.0:
        return np.ones(len(expected))
    return relative_se / typical


def decompose_for(series: pd.DataFrame, contract: KPIContract) -> Decomposition:
    """Decompose at the grain and with the noise model the contract declares.

    The single entry point every caller should use. `decompose` still takes its
    parameters directly because the tests need to vary them, but a caller that
    passes them by hand is a caller that can get them wrong for a metric it was
    not thinking about — which is exactly how an hourly contract came to be
    detected on a seven-hour seasonal cycle.

    `series` is the rolled-up frame: a `d` column at the contract's time grain,
    a `value` column, and for a ratio an `n` column carrying the denominator
    the rate was computed from.
    """
    return decompose(
        series,
        periods=seasonal_periods(contract.grain.time),
        denominator=series["n"] if "n" in series.columns else None,
        grain=contract.grain.time,
        proportion=contract.unit is Unit.RATIO,
        noise_model=contract.grain.noise_model,
    )


def seasonal_periods(time_grain: str) -> tuple[int, ...]:
    """The seasonal cycles a series at this grain carries, in observations."""
    try:
        return SEASONAL_PERIODS[time_grain]
    except KeyError:
        raise ValueError(
            f"no seasonal periods configured for a '{time_grain}' grain; known "
            f"grains are {sorted(SEASONAL_PERIODS)}. Falling back to a default "
            f"here would repeat the defect this map exists to prevent (T-19)"
        ) from None


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
    decomposition = decompose_for(series, contract)
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
