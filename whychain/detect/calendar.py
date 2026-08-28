"""Retail calendar effects, as known information rather than estimated pattern.

Festival dates are not a mystery to be recovered from the data. They are on a
calendar, and a deployment configures the calendar its business trades against.
Estimating a 365-day seasonal pattern from three years of history instead means
each day-of-year is fitted from three observations, so a single bad August gets
absorbed into "what August looks like", and the event disappears into the
seasonality it caused.

This module supplies the known effect so it can be divided out before anything
is estimated. The generator uses the same public holiday source independently;
neither reads the other.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import holidays
import numpy as np
import pandas as pd

# Shopping festivals and their peak intensity, as configured for Indian retail.
FESTIVAL_WEIGHTS: dict[str, float] = {
    "diwali": 0.85, "dussehra": 0.35, "holi": 0.25, "id-ul-fitr": 0.30,
    "eid": 0.30, "pongal": 0.20, "onam": 0.25, "christmas": 0.20,
}
BUILD_UP_DAYS = 18
HANGOVER_DAYS = 7
HANGOVER_DEPTH = 0.25


@lru_cache(maxsize=8)
def _calendar(years: tuple[int, ...]) -> holidays.HolidayBase:
    return holidays.India(years=list(years))


def festival_factor(days: pd.Series) -> np.ndarray:
    """Expected multiplicative effect of the retail calendar, per day.

    1.0 means an ordinary day. Dividing the series by this leaves a series in
    which festival weeks are no longer remarkable.
    """
    dates = pd.to_datetime(days).dt.date
    start, end = min(dates), max(dates)
    cal = _calendar(tuple(range(start.year - 1, end.year + 2)))

    peaks: dict[date, float] = {}
    for day in cal:
        if not (start - timedelta(days=40) <= day <= end + timedelta(days=40)):
            continue
        name = cal[day].lower()
        for key, weight in FESTIVAL_WEIGHTS.items():
            if key in name:
                peaks[day] = max(peaks.get(day, 0.0), weight)

    factor: dict[date, float] = {}
    for peak_day, weight in peaks.items():
        for offset in range(-BUILD_UP_DAYS, HANGOVER_DAYS + 1):
            day = peak_day + timedelta(days=offset)
            if offset <= 0:
                closeness = (BUILD_UP_DAYS + offset) / BUILD_UP_DAYS
                effect = 1.0 + weight * closeness**2
            else:
                fading = 1.0 - offset / HANGOVER_DAYS
                effect = 1.0 - weight * HANGOVER_DEPTH * fading
            current = factor.get(day, 1.0)
            factor[day] = max(current, effect) if effect >= 1 else min(current, effect)

    return np.array([factor.get(d, 1.0) for d in dates])
