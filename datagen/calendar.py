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

from datagen.world import RETAIL_CALENDAR, Calendar

# Retail's own weights and shape, kept under their original names because the
# tests and the docs refer to them. They are read off `RETAIL_CALENDAR` rather
# than restated: two copies of the same eight numbers is how a generator and its
# documentation quietly stop agreeing.
MAJOR_FESTIVALS: dict[str, float] = RETAIL_CALENDAR.festival_weights
BUILD_UP_DAYS = RETAIL_CALENDAR.build_up_days     # demand rises across ~2.5 weeks
HANGOVER_DAYS = RETAIL_CALENDAR.hangover_days     # and falls below baseline after
HANGOVER_DEPTH = RETAIL_CALENDAR.hangover_depth


@lru_cache(maxsize=8)
def _india(years: tuple[int, ...]) -> holidays.HolidayBase:
    return holidays.India(years=list(years))


def holidays_between(start: date, end: date) -> dict[date, str]:
    years = tuple(range(start.year, end.year + 1))
    cal = _india(years)
    return {d: cal[d] for d in sorted(cal) if start <= d <= end}


def _festival_weight(name: str, weights: dict[str, float] = MAJOR_FESTIVALS) -> float:
    """Match a holiday name to a festival weight, or zero if it is not a shopping event.

    Names vary between years ("Diwali (Deepavali)", "Id-ul-Fitr"), so match on
    substrings rather than equality.
    """
    lowered = name.lower()
    for key, weight in weights.items():
        if key.lower() in lowered:
            return weight
    return 0.0


def festival_peaks(
    start: date, end: date, calendar: Calendar = RETAIL_CALENDAR
) -> dict[date, float]:
    """Shopping festivals in the window, with their peak intensity.

    Which festivals matter, and by how much, is a fact about the business rather
    than about the country: a fuel marketer sees festival *travel* and a
    generator sees almost nothing, on the same public holiday calendar. The
    dates come from `holidays` either way.
    """
    peaks: dict[date, float] = {}
    # Widen the lookup so a festival just outside the window still casts its
    # build-up or hangover into it.
    for day, name in holidays_between(start - timedelta(days=40), end + timedelta(days=40)).items():
        weight = _festival_weight(name, calendar.festival_weights)
        if weight and weight > peaks.get(day, 0.0):
            peaks[day] = weight
    return peaks


def festival_uplift(
    start: date, end: date, calendar: Calendar = RETAIL_CALENDAR
) -> dict[date, float]:
    """Multiplicative demand uplift per day: 1.0 is an ordinary day.

    The curve rises quadratically into the festival, early interest is mild,
    the last few days are frantic, then drops below baseline as households stop
    buying. A detector that reacts to the raw series flags both the peak and the
    trough; one that models seasonality first flags neither.
    """
    uplift: dict[date, float] = {}
    build_up, hangover = calendar.build_up_days, calendar.hangover_days
    for peak_day, weight in festival_peaks(start, end, calendar).items():
        for offset in range(-build_up, hangover + 1):
            day = peak_day + timedelta(days=offset)
            if not (start <= day <= end):
                continue
            if offset <= 0:
                closeness = (build_up + offset) / build_up
                effect = 1.0 + weight * closeness**2
            else:
                fading = 1.0 - (offset / hangover)
                effect = 1.0 - weight * calendar.hangover_depth * fading
            uplift[day] = max(uplift.get(day, 1.0), effect) if effect >= 1 else min(
                uplift.get(day, 1.0), effect
            )
    return uplift


def weekday_uplift(day: date, calendar: Calendar = RETAIL_CALENDAR) -> float:
    """Weekly rhythm. Indian retail peaks at the weekend and dips midweek.

    Industrial offtake does the opposite and a generator barely notices, so the
    seven numbers come from the world rather than from here.
    """
    # Monday=0 ... Sunday=6
    return calendar.weekday[day.weekday()]
