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


# Which country's public-holiday set a contract's declared calendar means.
# `fiscal_in` is the Indian fiscal year, and the holidays that matter to a
# business trading on it are India's.
CALENDARS: dict[str, str] = {
    "fiscal_in": "India", "india": "India", "in": "India",
    "fiscal_uk": "UnitedKingdom", "uk": "UnitedKingdom", "gb": "UnitedKingdom",
}
DEFAULT_MARKET = "India"


def market_for(calendar: str | None) -> str:
    """The holiday market a declared calendar names, defaulting to the deployment's.

    Declared values that are not calendars of a country, `gregorian` among them,
    fall back rather than raise: a contract that says nothing about a market is
    not making a claim about one.
    """
    return CALENDARS.get((calendar or "").strip().lower(), DEFAULT_MARKET)


@lru_cache(maxsize=16)
def holidays_for(market: str, years: tuple[int, ...]) -> holidays.HolidayBase:
    """A market's public holidays, by name."""
    return holidays.country_holidays(market, years=list(years))


@lru_cache(maxsize=8)
def _calendar(years: tuple[int, ...]) -> holidays.HolidayBase:
    """The market the *detector* detrends against.

    Deliberately `DEFAULT_MARKET` and not the contract's declared calendar. That
    is B-033, and it is left open here on purpose: `festival_factor` feeds every
    expected value, every robust z and therefore every published accuracy
    figure, so changing which calendar it reads is a change that has to be
    re-benchmarked rather than slipped in. `market_for` exists for readers that
    only display a calendar, and the fix is to call it from here once there is
    time to measure what moves.
    """
    return holidays_for(DEFAULT_MARKET, years)


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
