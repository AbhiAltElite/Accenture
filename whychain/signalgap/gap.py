"""Answer 2: which warning existed, and which process failed to read it.

Answer 1 ends with a verified cause. That is the question every BI tool already
claims to answer. The question nobody answers is why the business was surprised
by something the outside world had already published, and that is what this
stage computes.

The finding is a set difference, and both sides of it are evidenced:

    signals_available: rows in `ext_signals` that overlap the anomaly window
                         and cover the affected slice
    signals_consumed: extracted from the planning document at contract
                         registration, with a character span per signal

    gap = available \\ consumed, after three gates

**Foreseeability is decided before the gap, not after it.** Hindsight makes
everything look preventable, so a signal only counts as one the business could
have acted on if it was public, if it was severe enough to be actionable, and
if it landed far enough ahead of the event to do anything with. A red warning
issued ninety minutes before the rain is not a process failure, and an engine
that reports one as a gap is manufacturing blame. That case has its own verdict.

**Not knowing is a verdict, not a silence.** If the contract has no SOP behind
its `signals_consumed`, this stage cannot claim the process missed anything;
it does not know what the process reads. `coverage_unknown` says exactly that
and names the document that would settle it. The alternative, assuming a gap
whenever we lack evidence of consumption, would make Answer 2 a generator of
accusations.

**Recurrence is what turns an incident into a finding.** One missed warning is
an anecdote. The same class of warning arriving eleven times over two years,
against a process that consumes none of them, is a control that does not exist.
The precedent count is computed over the same feed, so it is auditable in the
same click.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

import pandas as pd

from whychain.contracts import KPIContract
from whychain.evidence import (
    Evidence,
    EvidenceKind,
    MethodClass,
    Provenance,
    Unit,
)

# A warning has to arrive with enough time to do something. Below this it is
# information, not an opportunity, and the verdict is `not_foreseeable`.
MIN_ACTIONABLE_LEAD_HOURS = 24.0

# Severity bands that a planner would be expected to act on. Yellow is advisory
# and fires most weeks in monsoon season; treating it as actionable would make
# the gap finding meaningless through sheer volume.
ACTIONABLE_SEVERITY: frozenset[str] = frozenset({"amber", "red"})

_SEVERITY_ORDER = ("green", "yellow", "amber", "red")

# How far back recurrence is counted. Two years spans two monsoons and two
# festival cycles, so a seasonal pattern shows up as a pattern.
PRECEDENT_LOOKBACK_DAYS = 730

# Two actionable warnings closer together than this are the same episode, not
# two precedents.
EPISODE_GAP_DAYS = 5


class GapVerdict(StrEnum):
    """The four things this stage is allowed to conclude.

    All four are reachable, and all four are correct answers to a real
    situation. A stage that can only return `gap_found` is not detecting
    anything; it is asserting its own premise.
    """

    GAP_FOUND = "gap_found"
    NO_GAP = "no_gap"
    NOT_FORESEEABLE = "not_foreseeable"
    COVERAGE_UNKNOWN = "coverage_unknown"


@dataclass(frozen=True)
class WarningSignal:
    """One published warning, as the external feed delivered it.

    `lead_time_hours` is issue-to-onset and is carried from the feed rather than
    recomputed, because the feed is the record of when the warning was actually
    available, not when we would like it to have been.
    """

    signal_id: str
    signal_type: str
    city: str
    region: str
    severity: str
    issued_at: datetime
    valid_from: datetime
    valid_to: datetime
    lead_time_hours: float
    is_public: bool
    publisher: str
    source: str
    source_url: str | None = None

    @property
    def actionable(self) -> bool:
        return (
            self.is_public
            and self.severity in ACTIONABLE_SEVERITY
            and self.lead_time_hours >= MIN_ACTIONABLE_LEAD_HOURS
        )

    def as_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "city": self.city,
            "region": self.region,
            "severity": self.severity,
            "issued_at": self.issued_at.isoformat(),
            "valid_from": self.valid_from.isoformat(),
            "lead_time_hours": round(self.lead_time_hours, 1),
            "is_public": self.is_public,
            "publisher": self.publisher,
            "source": self.source,
            "source_url": self.source_url,
            "actionable": self.actionable,
        }


@dataclass(frozen=True)
class Precedent:
    """A prior episode of the same warning class over the same slice.

    `hurt` is the field that keeps this honest. Counting episodes answers "how
    often has this weather happened", and a reader takes it to mean "how often
    has this cost us money". Those are different numbers and the second is the
    one the finding actually rests on, so it is measured rather than implied.
    `None` means the metric history needed to decide was not supplied, which is
    reported as unknown rather than assumed either way.
    """

    start: date
    end: date
    region: str
    max_severity: str
    signal_count: int
    hurt: bool | None = None

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "region": self.region,
            "max_severity": self.max_severity,
            "signal_count": self.signal_count,
            "hurt": self.hurt,
        }


@dataclass(frozen=True)
class SignalGap:
    """Answer 2 for one movement.

    Every field is either read from the feed, read from the contract, or
    derived from those two. Nothing here is written by a model, and the reason
    string is assembled from the same values the caller can see.
    """

    verdict: GapVerdict
    reason: str
    signal_type: str | None
    signals: tuple[WarningSignal, ...]
    actionable_signals: tuple[WarningSignal, ...]
    consumed: tuple[str, ...]
    process_document: str | None
    process_spans: tuple[dict, ...]
    owner_role: str | None
    best_lead_time_hours: float | None
    precedents: tuple[Precedent, ...]
    window: tuple[date, date]
    region: str | None
    monitoring: dict | None = None
    caveats: tuple[str, ...] = field(default_factory=tuple)

    @property
    def recurrence(self) -> int:
        return len(self.precedents)

    @property
    def recurrence_that_hurt(self) -> int | None:
        """How many prior episodes actually moved the metric.

        None when no episode could be judged, which is the honest answer when
        the metric history was not supplied.
        """
        judged = [p for p in self.precedents if p.hurt is not None]
        return sum(1 for p in judged if p.hurt) if judged else None

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "signal_type": self.signal_type,
            "signals": [s.as_dict() for s in self.signals[:12]],
            "signal_count": len(self.signals),
            "actionable_count": len(self.actionable_signals),
            "consumed": list(self.consumed),
            "process_document": self.process_document,
            "process_spans": list(self.process_spans),
            "owner_role": self.owner_role,
            "best_lead_time_hours": (
                round(self.best_lead_time_hours, 1)
                if self.best_lead_time_hours is not None
                else None
            ),
            "recurrence": self.recurrence,
            "recurrence_that_hurt": self.recurrence_that_hurt,
            "precedents": [p.as_dict() for p in self.precedents],
            "window": {"from": self.window[0].isoformat(),
                       "to": self.window[1].isoformat()},
            "region": self.region,
            "monitoring": self.monitoring,
            "caveats": list(self.caveats),
        }


def _as_utc(value) -> datetime:
    """Every timestamp crossing this boundary is aware UTC (BUGS.md T-15)."""
    ts = pd.Timestamp(value)
    ts = ts.tz_localize(UTC) if ts.tzinfo is None else ts.tz_convert(UTC)
    return ts.to_pydatetime()


def read_signals(
    ext_signals: pd.DataFrame,
    *,
    window: tuple[date, date],
    region: str | None = None,
    signal_type: str | None = None,
) -> tuple[WarningSignal, ...]:
    """Warnings whose validity overlaps the window and covers the slice.

    Overlap, not containment: a warning that opened the day before the window
    and ran into it was available to the planner, and one that opened on the
    last day was not available for the first four. Both are kept and the lead
    time is what separates them.
    """
    if ext_signals is None or ext_signals.empty:
        return ()

    start, end = window
    lo = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    hi = datetime.combine(end, datetime.max.time(), tzinfo=UTC)

    df = ext_signals.copy()
    for col in ("issued_at", "valid_from", "valid_to"):
        df[col] = pd.to_datetime(df[col], utc=True)

    overlap = (df["valid_from"] <= hi) & (df["valid_to"] >= lo)
    df = df[overlap]
    if region:
        df = df[df["region"] == region]
    if signal_type:
        df = df[df["signal_type"] == signal_type]

    return tuple(
        WarningSignal(
            signal_id=str(r.signal_id),
            signal_type=str(r.signal_type),
            city=str(r.city),
            region=str(r.region),
            severity=str(r.severity),
            issued_at=_as_utc(r.issued_at),
            valid_from=_as_utc(r.valid_from),
            valid_to=_as_utc(r.valid_to),
            lead_time_hours=float(r.lead_time_hours),
            is_public=bool(r.is_public),
            publisher=str(r.publisher),
            source=str(r.source),
            source_url=getattr(r, "source_url", None),
        )
        for r in df.sort_values("valid_from").itertuples()
    )


def find_precedents(
    ext_signals: pd.DataFrame,
    *,
    before: date,
    region: str | None,
    signal_type: str,
    lookback_days: int = PRECEDENT_LOOKBACK_DAYS,
    history: pd.Series | None = None,
) -> tuple[Precedent, ...]:
    """Prior episodes of the same actionable warning over the same slice.

    Consecutive warning days are collapsed into one episode, so a five-day
    cyclone is one precedent rather than five. Counting rows here would inflate
    recurrence by exactly the length of the weather.

    `history` is the metric's own daily series. When it is given, each episode
    is checked against it and marked for whether the metric actually moved
    against its own recent level during the episode. Without that check the
    recurrence figure says only that the weather recurred, which is not the
    claim a reader takes from it.
    """
    if ext_signals is None or ext_signals.empty:
        return ()

    df = ext_signals.copy()
    df["valid_from"] = pd.to_datetime(df["valid_from"], utc=True)
    floor = datetime.combine(
        before - timedelta(days=lookback_days), datetime.min.time(), tzinfo=UTC
    )
    ceiling = datetime.combine(before, datetime.min.time(), tzinfo=UTC)

    df = df[
        (df["signal_type"] == signal_type)
        & (df["valid_from"] >= floor)
        & (df["valid_from"] < ceiling)
        & (df["severity"].isin(ACTIONABLE_SEVERITY))
        & (df["is_public"])
    ]
    if region:
        df = df[df["region"] == region]
    if df.empty:
        return ()

    df = df.assign(day=df["valid_from"].dt.date).sort_values("day")
    episodes: list[list] = []
    for day, chunk in df.groupby("day", sort=True):
        if episodes and (day - episodes[-1][-1]["day"]).days <= EPISODE_GAP_DAYS:
            episodes[-1].append({"day": day, "rows": chunk})
        else:
            episodes.append([{"day": day, "rows": chunk}])

    out: list[Precedent] = []
    for episode in episodes:
        rows = pd.concat([d["rows"] for d in episode])
        start, end = episode[0]["day"], episode[-1]["day"]
        out.append(
            Precedent(
                start=start,
                end=end,
                region=region or "all regions",
                max_severity=max(
                    rows["severity"], key=lambda s: _SEVERITY_ORDER.index(s)
                ),
                signal_count=len(rows),
                hurt=_moved_during(history, start, end),
            )
        )
    return tuple(reversed(out))


# How far the metric must fall below its own trailing level during an episode
# before that episode counts as one that hurt. Deliberately looser than the
# contract's detection threshold: this is asking "did the business feel it",
# not "would the detector have fired", and holding it to the stricter bar would
# undercount episodes that were real but sat just under the z gate.
PRECEDENT_IMPACT_DROP = 0.06
PRECEDENT_BASELINE_DAYS = 28


def _moved_during(
    history: pd.Series | None, start: date, end: date
) -> bool | None:
    """Whether the metric fell materially while this episode was running.

    Returns None when there is not enough history either side to judge, because
    "we could not tell" and "it did not hurt" are different answers and only one
    of them is evidence.
    """
    if history is None or history.empty:
        return None
    index = pd.Series(list(history.index))
    during = history[(index >= start).to_numpy() & (index <= end).to_numpy()]
    before = history[
        ((index < start) & (index >= start - timedelta(days=PRECEDENT_BASELINE_DAYS)))
        .to_numpy()
    ]
    if during.empty or len(before) < 7:
        return None
    baseline = float(before.mean())
    if not baseline:
        return None
    return bool((float(during.mean()) / baseline - 1.0) <= -PRECEDENT_IMPACT_DROP)


def _driver_for_signal(contract: KPIContract, signal_type: str):
    """The contract driver fed by this signal, if the contract declares one."""
    driver = next((d for d in contract.drivers if d.id == signal_type), None)
    if driver is not None:
        return driver
    # Contracts name the driver, not the feed's type string, so fall back to a
    # driver whose declared source is the external feed and whose id the signal
    # type contains. `severe_weather` and the `severe_weather` driver line up
    # directly; `carrier_disruption` does not, and returning None there is the
    # correct answer rather than a near-match.
    return next(
        (
            d for d in contract.drivers
            if d.source == "ext_signals" and d.id in signal_type
        ),
        None,
    )


# Which external signal type could plausibly have warned about a cause of this
# shape. Shared vocabulary with `whychain.actions`, so a cause routed to the
# `severe_weather` driver there is checked against the weather feed here; the
# two stages cannot disagree about what kind of thing a cause is.
CAUSE_TO_SIGNAL: tuple[tuple[tuple[str, ...], str], ...] = (
    (("weather", "rainfall", "storm", "flood", "monsoon", "cyclone"), "severe_weather"),
    (("carrier", "courier", "logistics", "3pl"), "carrier_disruption"),
    (("competitor", "rival"), "competitor_action"),
    (("supplier", "shortfall", "stockout", "out of stock"), "supply_disruption"),
)

# Causes nothing outside the company would have published a warning about. A
# release that broke checkout is not something the met office announces, and an
# engine that answers "you missed a weather warning" for an internal regression
# is producing a coincidence, not a finding.
INTERNAL_MARKERS: tuple[str, ...] = (
    "release", "deploy", "rollout", "bug", "regression", "checkout flow",
    "pricing change", "list price", "discount", "campaign", "marketing",
)


def signal_types_for(causes: Sequence[str]) -> tuple[str, ...]:
    """Which external feeds are relevant to these verified causes.

    Empty means "none of them", and that is a real answer: it produces a
    `no_gap` whose reason names the cause as internal. It is not the same as
    the empty-causes case, where nothing has been verified and every external
    feed is still a live hypothesis, the caller distinguishes them.
    """
    out: list[str] = []
    for description in causes:
        text = description.lower()
        for words, signal_type in CAUSE_TO_SIGNAL:
            if any(w in text for w in words) and signal_type not in out:
                out.append(signal_type)
    return tuple(out)


def causes_are_internal(causes: Sequence[str]) -> bool:
    """Whether every verified cause is one no outside body would warn about."""
    if not causes:
        return False
    return all(
        any(marker in c.lower() for marker in INTERNAL_MARKERS) for c in causes
    )


def _monitoring(
    signal_type: str,
    owner_role: str | None,
    lead_hours: float | None,
    recurrence: int,
) -> dict:
    """What to add so this is consumed next time.

    A rule is only worth adopting if it would have caught the case in hand, so
    the threshold is stated in the feed's own terms, severity and lead time,
    and both come from the signals just read. `would_have_fired` records that
    check against the rule, not against anyone's conduct: it is what separates
    a rule worth adopting from one written to fit a case it could never have
    caught. The console labels it accordingly.
    """
    return {
        "watch": f"{signal_type.replace('_', ' ')} warnings covering the affected region",
        "threshold": (
            f"severity amber or above with at least "
            f"{MIN_ACTIONABLE_LEAD_HOURS:g} hours of lead time"
        ),
        "window": "checked at every planning cycle, and on publication",
        "route_to": owner_role or "unassigned, no driver owner in the contract",
        "would_have_fired": lead_hours is not None
        and lead_hours >= MIN_ACTIONABLE_LEAD_HOURS,
        "prior_occurrences": recurrence,
    }



def _hours(value: float) -> str:
    """One hour, not one hours. The sentence is read by a person."""
    rounded = round(value)
    return f"{rounded:.0f} hour" + ("" if rounded == 1 else "s")


def _why_not_actionable(signals: Sequence[WarningSignal]) -> str:
    """Explain the refusal by naming which gate each near-miss failed.

    An earlier version asked three aggregate questions — was anything public,
    was anything severe, was the earliest early enough — and reported whichever
    came back false. That reads correctly until the answers separate: a red
    nowcast fifty minutes ahead alongside a yellow advisory two days ahead makes
    every aggregate question individually false, and the explanation came out as
    an empty string mid-sentence.

    The gates are per signal, so the explanation is too. It names the warning
    that came closest to being usable and says what stopped it, which is also
    the more useful sentence: "serious, and far too late" is a different finding
    from "nothing was serious", and a reader needs to know which one they have.
    """
    if not signals:
        return "No warning covered this window."

    private = [s for s in signals if not s.is_public]
    severe = [s for s in signals if s.severity in ACTIONABLE_SEVERITY and s.is_public]
    timely = [
        s for s in signals
        if s.lead_time_hours >= MIN_ACTIONABLE_LEAD_HOURS and s.is_public
    ]
    head = f"{len(signals)} warning(s) covered this window. "

    if severe and timely:
        # Both properties present, never in the same warning. The most
        # interesting case, and the one the old code rendered as a blank.
        best_severe = max(severe, key=lambda s: s.lead_time_hours)
        best_timely = max(timely, key=lambda s: _SEVERITY_ORDER.index(s.severity))
        return (
            head
            + f"The most serious of them ({best_severe.severity}) arrived "
            f"{_hours(best_severe.lead_time_hours)} ahead, under the "
            f"{MIN_ACTIONABLE_LEAD_HOURS:g} needed to act on it. The warnings "
            f"that did arrive in time only reached {best_timely.severity}. "
            "No single warning was both serious enough and early enough, so "
            "this was not a process failure."
        )

    if severe:
        best = max(severe, key=lambda s: s.lead_time_hours)
        return (
            head
            + f"The earliest that reached {best.severity} arrived "
            f"{_hours(best.lead_time_hours)} ahead, under the "
            f"{MIN_ACTIONABLE_LEAD_HOURS:g} needed to act on it. This was not a "
            "process failure."
        )

    if timely:
        best = max(timely, key=lambda s: _SEVERITY_ORDER.index(s.severity))
        return (
            head
            + f"None reached amber severity; the most serious was {best.severity}, "
            "which is advisory and fires most weeks in monsoon season. This was "
            "not a process failure."
        )

    if private and len(private) == len(signals):
        return (
            head + "None of them was public, so nobody outside the publisher "
            "could have acted on one. This was not a process failure."
        )

    return (
        head + "None was both public, severe enough to act on, and early enough "
        "to act within. This was not a process failure."
    )


def assess(
    contract: KPIContract,
    signals: Sequence[WarningSignal],
    *,
    window: tuple[date, date],
    region: str | None = None,
    precedents: Iterable[Precedent] = (),
    signal_type: str | None = None,
) -> SignalGap:
    """Decide the verdict from the signals and the contract. No I/O.

    The order of the checks is the argument. Coverage is settled first, because
    without it every other conclusion is an assumption about a process we have
    not read. Foreseeability is settled second, before the set difference,
    because a signal nobody could have acted on is not evidence of a gap
    regardless of whether the process consumes it.
    """
    consumed = tuple(sorted(contract.signals_consumed.signal_ids))
    spans = tuple(
        {"signal": s.signal, "span": list(s.span)}
        for s in contract.signals_consumed.extracted
    )
    document = contract.signals_consumed.derived_from
    precedents = tuple(precedents)
    kind = signal_type or (signals[0].signal_type if signals else None)
    driver = _driver_for_signal(contract, kind) if kind else None
    # An external driver usually has no owner, because nobody owns the weather.
    # Somebody does own the decision to consume the warning, though, and that is
    # the KPI owner. Routing a monitoring rule to "unassigned" would make the
    # finding unactionable at the exact point it becomes actionable.
    owner = (driver.owner_role if driver and driver.owner_role else contract.owner_role)
    actionable = tuple(s for s in signals if s.actionable)
    best_lead = max((s.lead_time_hours for s in actionable), default=None)

    common = {
        "signal_type": kind,
        "signals": tuple(signals),
        "actionable_signals": actionable,
        "consumed": consumed,
        "process_document": document,
        "process_spans": spans,
        "owner_role": owner,
        "best_lead_time_hours": best_lead,
        "precedents": precedents,
        "window": window,
        "region": region,
    }

    # 1. Do we know what the process reads? If not, nothing else is decidable.
    if contract.signals_consumed.coverage.value == "unknown" or document is None:
        return SignalGap(
            verdict=GapVerdict.COVERAGE_UNKNOWN,
            reason=(
                "No process document is registered against this KPI, so the "
                "engine does not know which signals the planning cycle consumes "
                "and will not infer a gap from that absence."
            ),
            caveats=(
                "register a process document on the contract's signals_consumed "
                "to make this question answerable",
            ),
            **common,
        )

    # 2. Was there anything to consume at all?
    if not signals:
        return SignalGap(
            verdict=GapVerdict.NO_GAP,
            reason=(
                "No external warning covering this window and slice was "
                "published, so the movement was not foreseeable from an "
                "external feed. The cause, if any, is internal."
            ),
            **common,
        )

    # 3. Was it foreseeable? Decided before the set difference, on purpose.
    if not actionable:
        return SignalGap(
            verdict=GapVerdict.NOT_FORESEEABLE,
            reason=_why_not_actionable(signals),
            **common,
        )

    # 4. The set difference itself.
    if kind in contract.signals_consumed.signal_ids:
        return SignalGap(
            verdict=GapVerdict.NO_GAP,
            reason=(
                f"{kind.replace('_', ' ')} is already consumed by the registered "
                f"planning process ({document}), so the warning was available to "
                "it. If the movement still surprised the business, the failure is "
                "in acting on the signal rather than in receiving it."
            ),
            **common,
        )

    hurt = sum(1 for p in precedents if p.hurt)
    judged = any(p.hurt is not None for p in precedents)
    recurrence_clause = (
        f" The same warning class has covered this slice on {len(precedents)} "
        f"prior occasion(s), {hurt} of which coincided with a material movement."
        if precedents and judged else
        f" The same warning class has covered this slice on {len(precedents)} "
        "prior occasion(s); whether those coincided with a material movement "
        "was not assessed." if precedents else ""
    )
    return SignalGap(
        verdict=GapVerdict.GAP_FOUND,
        reason=(
            f"{len(actionable)} public {kind.replace('_', ' ')} warning(s) at "
            f"amber or above covered this window with up to {best_lead:.0f} hours "
            f"of lead time. The registered planning process consumes "
            f"{', '.join(c.replace('_', ' ') for c in consumed)} and no external "
            f"risk signal, so nothing in the cycle could have read them."
            + recurrence_clause
        ),
        monitoring=_monitoring(kind, owner, best_lead, len(precedents)),
        **common,
    )


def find_gap(
    contract: KPIContract,
    ext_signals: pd.DataFrame,
    *,
    event_start: date,
    event_end: date,
    region: str | None = None,
    causes: Sequence[str] = (),
    signal_type: str | None = None,
    history: pd.Series | None = None,
) -> SignalGap:
    """Read the feed and assess it. The one entry point the API calls.

    The feed is consulted *for the cause that was verified*, not for the window
    in general. Weather warnings are in the feed most weeks of the monsoon, so
    an engine that checks the window alone will report a signal gap on a
    release regression; the warning was real, it was public, it had days of
    lead time, and it had nothing whatever to do with what happened. That is
    the most damaging output this stage could produce, because it is
    superficially well-evidenced.
    """
    window = (event_start, event_end)

    if signal_type is None:
        if causes_are_internal(causes):
            base = assess(
                contract, (), window=window, region=region, signal_type=None
            )
            # `coverage_unknown` still outranks this: if we do not know what the
            # process reads, we cannot say the cause being internal settles it.
            if base.verdict is GapVerdict.COVERAGE_UNKNOWN:
                return base
            return replace(
                base,
                verdict=GapVerdict.NO_GAP,
                reason=(
                    "Every verified cause is internal, something no external "
                    "body publishes a warning about. External feeds were not "
                    "consulted, because a warning that merely coincides with an "
                    "internal regression is a coincidence, and reporting it as a "
                    "gap would be false."
                ),
            )
        relevant = signal_types_for(causes)
        # Nothing verified yet: every external feed the contract declares is
        # still a live hypothesis, so the widest one is checked.
        signal_type = relevant[0] if relevant else "severe_weather"

    signals = read_signals(
        ext_signals, window=window, region=region, signal_type=signal_type
    )
    precedents = find_precedents(
        ext_signals, before=event_start, region=region,
        signal_type=signal_type, history=history,
    )
    return assess(
        contract,
        signals,
        window=window,
        region=region,
        precedents=precedents,
        signal_type=signal_type,
    )


def as_evidence(gap: SignalGap, run_id: str) -> Evidence:
    """The gap as a citable record, so the narrative can reference it by id."""
    value: float | None
    if gap.verdict is GapVerdict.GAP_FOUND and gap.best_lead_time_hours is not None:
        value, unit = gap.best_lead_time_hours, Unit.HOURS
    else:
        value, unit = None, Unit.NONE

    return Evidence(
        id=f"{run_id}-signalgap",
        kind=EvidenceKind.SIGNAL_GAP,
        claim=gap.reason,
        value=value,
        unit=unit,
        method="signal_gap",
        method_class=MethodClass.DETERMINISTIC,
        provenance=Provenance(
            source_id="ext_signals",
            query=(
                "SELECT * FROM ext_signals WHERE signal_type = "
                f"'{gap.signal_type}' AND valid_to >= '{gap.window[0]}' "
                f"AND valid_from <= '{gap.window[1]}'"
                + (f" AND region = '{gap.region}'" if gap.region else "")
            ),
            row_count=len(gap.signals),
            row_ids=[s.signal_id for s in gap.signals[:20]],
        ),
        run_id=run_id,
        extra={
            "verdict": gap.verdict.value,
            "recurrence": gap.recurrence,
            "consumed": list(gap.consumed),
        },
    )
