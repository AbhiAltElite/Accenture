"""Planted causes, decoys, and the ground truth that describes them.

Two kinds of planted event matter here.

A **cause** perturbs the series. The engine is expected to find it.

A **decoy** does not perturb anything, but is recorded in the operational data
at the same time and place as a real cause, so it correlates with the movement
by construction. A ranking method built on correlation picks it. Verification is
supposed to reject it, and the rate at which it does is the number that answers
"you only find causes you planted yourself".

The decoy is deliberately run in the control region too. That is what gives
difference-in-differences something to bite on: the promotion ran in the East as
well, and the East was fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum


class CauseKind(StrEnum):
    INTERNAL_BUG = "internal_bug"        # release regression on one channel/device
    PRICE_CHANGE = "price_change"
    STOCKOUT = "stockout"
    MARKETING_CUT = "marketing_cut"
    COMPETITOR_PROMO = "competitor_promo"
    EXTERNAL_WEATHER = "external_weather"


class ExpectedVerdict(StrEnum):
    """What a correct engine should conclude for this case."""

    VERIFIED = "verified"          # a cause exists and is testable
    UNKNOWN = "unknown"            # evidence is genuinely insufficient
    NO_ANOMALY = "no_anomaly"      # nothing to explain; silence is the right answer
    CANNOT_VERIFY = "cannot_verify"  # movement is real but untestable (sparse history)


@dataclass(frozen=True)
class Slice:
    """Which part of the business an event touches. None means 'all'."""

    region: str | None = None
    channel: str | None = None
    device: str | None = None
    category: str | None = None
    sku: str | None = None

    def matches(self, **row: str) -> bool:
        return all(
            getattr(self, dim) is None or row.get(dim) == getattr(self, dim)
            for dim in ("region", "channel", "device", "category", "sku")
        )

    def describe(self) -> str:
        parts = [f"{k}={v}" for k, v in self.__dict__.items() if v is not None]
        return " ".join(parts) or "all"


@dataclass(frozen=True)
class PlantedEvent:
    """Something recorded in the operational data.

    `effect` is the multiplicative impact on the metric: -0.30 is a thirty per
    cent reduction. A decoy carries effect 0.0; it is recorded and therefore
    correlates, but it changes nothing.
    """

    event_id: str
    kind: CauseKind
    start: date
    end: date
    target: Slice
    effect: float
    is_decoy: bool = False
    # A decoy must also appear somewhere unaffected, or the comparison group has
    # nothing to distinguish it from a real cause.
    also_in: tuple[str, ...] = ()
    description: str = ""

    def active_on(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True)
class AvailableSignal:
    """A warning that existed before the event, and how usable it was.

    Answer 2 turns on all three fields together. A signal that was public but
    arrived ten minutes ahead, or one with a fourteen-day lead time that covered
    the whole country rather than the affected region, is not actionable, and
    the engine is expected to say *not foreseeable* rather than manufacture a gap.
    """

    signal_id: str
    publisher: str
    available_at: datetime
    lead_time_hours: float
    is_public: bool
    covers: Slice


@dataclass(frozen=True)
class Scenario:
    """One labelled case: what was planted, and what a correct engine concludes."""

    case_id: str
    kpi_id: str
    window_start: date
    window_end: date
    expected: ExpectedVerdict
    causes: tuple[PlantedEvent, ...] = ()
    decoys: tuple[PlantedEvent, ...] = ()
    signals: tuple[AvailableSignal, ...] = ()
    notes: str = ""
    tags: tuple[str, ...] = field(default=())

    @property
    def events(self) -> tuple[PlantedEvent, ...]:
        """Everything written into the operational data, real or not.

        The generator cannot distinguish these when emitting: a decoy has to look
        exactly like a cause in the sources, or the engine could cheat by noticing
        a difference in how it was recorded.
        """
        return (*self.causes, *self.decoys)

    def true_cause_kinds(self) -> tuple[str, ...]:
        return tuple(c.kind.value for c in self.causes)

    def window_days(self) -> int:
        return (self.window_end - self.window_start).days + 1


def anomaly_window(centre: date, before: int = 21, after: int = 7) -> tuple[date, date]:
    """A window with enough pre-period for a baseline and a comparison group."""
    return centre - timedelta(days=before), centre + timedelta(days=after)
