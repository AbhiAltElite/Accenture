"""Indian retail calendar.

Holiday dates come from the `holidays` package rather than being hard-coded,
because Diwali and Eid move each year and a wrong festival date would put the
seasonal decoy in the wrong week, quietly turning the false-alarm test into a
test of something else.

Retail does not spike on the festival day itself. Demand builds over the weeks
before it and collapses immediately after, and that shape is what makes a
festival genuinely hard to tell from a real break. A generator that only bumps
the single day produces a decoy any detector would pass.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import holidays

# Festivals with a real shopping run-up, and how strongly each lifts demand at
# its peak. Diwali dominates the Indian retail year; the others are smaller.
MAJOR_FESTIVALS: dict[str, float] = {
    "Diwali": 0.85,
    "Dussehra": 0.35,
    "Holi": 0.25,
    "Eid": 0.30,
    "Pongal": 0.20,
    "Onam": 0.25,
    "Christmas": 0.20,
    "Raksha": 0.15,
}

BUILD_UP_DAYS = 18   # demand rises across roughly two and a half weeks
HANGOVER_DAYS = 7    # and falls below baseline for a week afterwards
HANGOVER_DEPTH = 0.25


@lru_cache(maxsize=8)
def _india(years: tuple[int, ...]) -> holidays.HolidayBase:
    return holidays.India(years=list(years))


def holidays_between(start: date, end: date) -> dict[date, str]:
    years = tuple(range(start.year, end.year + 1))
    cal = _india(years)
    return {d: cal[d] for d in sorted(cal) if start <= d <= end}


def _festival_weight(name: str) -> float:
    """Match a holiday name to a festival weight, or zero if it is not a shopping event.

    Names vary between years ("Diwali (Deepavali)", "Id-ul-Fitr"), so match on
    substrings rather than equality.
    """
    lowered = name.lower()
    for key, weight in MAJOR_FESTIVALS.items():
        if key.lower() in lowered:
            return weight
    return 0.0


def festival_peaks(start: date, end: date) -> dict[date, float]:
    """Shopping festivals in the window, with their peak intensity."""
    peaks: dict[date, float] = {}
    # Widen the lookup so a festival just outside the window still casts its
    # build-up or hangover into it.
    for day, name in holidays_between(start - timedelta(days=40), end + timedelta(days=40)).items():
        weight = _festival_weight(name)
        if weight and weight > peaks.get(day, 0.0):
            peaks[day] = weight
    return peaks


def festival_uplift(start: date, end: date) -> dict[date, float]:
    """Multiplicative demand uplift per day: 1.0 is an ordinary day.

    The curve rises quadratically into the festival, early interest is mild,
    the last few days are frantic, then drops below baseline as households stop
    buying. A detector that reacts to the raw series flags both the peak and the
    trough; one that models seasonality first flags neither.
    """
    uplift: dict[date, float] = {}
    for peak_day, weight in festival_peaks(start, end).items():
        for offset in range(-BUILD_UP_DAYS, HANGOVER_DAYS + 1):
            day = peak_day + timedelta(days=offset)
            if not (start <= day <= end):
                continue
            if offset <= 0:
                closeness = (BUILD_UP_DAYS + offset) / BUILD_UP_DAYS
                effect = 1.0 + weight * closeness**2
            else:
                fading = 1.0 - (offset / HANGOVER_DAYS)
                effect = 1.0 - weight * HANGOVER_DEPTH * fading
            uplift[day] = max(uplift.get(day, 1.0), effect) if effect >= 1 else min(
                uplift.get(day, 1.0), effect
            )
    return uplift


def weekday_uplift(day: date) -> float:
    """Weekly rhythm. Indian retail peaks at the weekend and dips midweek."""
    # Monday=0 ... Sunday=6
    return (0.94, 0.92, 0.95, 0.99, 1.08, 1.18, 1.12)[day.weekday()]
