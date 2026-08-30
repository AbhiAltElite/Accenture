"""Measure the engine against cases whose answers it cannot see.

Every metric here is one the engine could fail at. That is the point: a
benchmark that only reports what a system is good at is a brochure.

    make bench
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import time
import warnings
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path

import pandas as pd

from datagen.bulk import BenchCase, BenchPanel, build_cases
from datagen.scenarios import ExpectedVerdict
from datagen.series import build_panel
from datagen.sources import emit_plan_ops, emit_voice_ops
from whychain.confidence import explained_movement, score
from whychain.confidence.calibrate import expected_calibration_error
from whychain.confidence.calibrate import fit as fit_calibration
from whychain.contracts import ContractRegistry
from whychain.corroborate import corroborate
from whychain.corroborate.documents import Document
from whychain.corroborate.retriever import NumpyRetriever
from whychain.decompose import BridgeError, compute_bridge
from whychain.detect import decompose_for, find_anomalies, material
from whychain.evidence import ClaimState, Freshness
from whychain.verify import filter_relevant, from_operations, from_promotions, verify

warnings.filterwarnings("ignore")

BASELINE_DAYS = 14
REPORT = Path("bench/report.json")


# The verdicts whose correct answer is "the evidence is insufficient". Kept as
# a set rather than a literal so `CANNOT_VERIFY` counts the moment the
# generator starts planting sparse-history cases.
UNANSWERABLE = frozenset({"unknown", "cannot_verify"})


@dataclass
class Outcome:
    case_id: str
    expected: str
    tags: tuple[str, ...]
    detected: bool                       # flagged statistically, before the money floor
    material_detected: bool              # and also large enough in rupees to report
    verdict: str                         # explained | unknown
    verified: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    untestable: tuple[str, ...] = ()
    confidence: float = 0.0
    top1: bool | None = None             # true cause ranked first among verified
    topk: bool | None = None             # true cause verified at all
    decoy_rejected: bool | None = None
    seconds: float = 0.0
    error: str | None = None
    # Which half of the population this case belongs to. Calibration is fitted
    # on `fit` and every reported figure comes from `test`, so the curve is
    # never scored against the cases that produced it (BUGS.md T-13).
    split: str = "test"


@dataclass
class Metrics:
    counts: dict[str, int] = field(default_factory=dict)
    rates: dict[str, float | None] = field(default_factory=dict)
    calibration: list[dict] = field(default_factory=list)
    calibration_fit: dict | None = None
    ece: float | None = None
    latency: dict[str, float] = field(default_factory=dict)


def _fresh(contract) -> dict[str, Freshness]:
    """Benchmark cases are evaluated as though every source landed on time.

    Freshness is a real input to confidence, but varying it here would measure
    the generator's staleness model rather than the engine's judgement.
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return {
        source: Freshness(source_id=source, as_of=now - sla / 2, observed_at=now, sla=sla)
        for source, sla in contract.freshness_sla.items()
    }


def run_case(
    case: BenchCase,
    panel: pd.DataFrame,
    documents: pd.DataFrame,
    plan: pd.DataFrame,
    retriever: NumpyRetriever,
    contract,
) -> Outcome:
    started = time.perf_counter()
    regions = tuple(sorted(panel["region"].unique()))
    scoped = panel[panel["region"] == case.region]
    day = pd.to_datetime(scoped["d"]).dt.date

    series = (
        scoped.groupby("d", as_index=False)["revenue"].sum()
        .rename(columns={"revenue": "value"}).sort_values("d")
    )
    # Two separate questions. Did the detector see the movement at all, and was
    # the movement large enough to be worth an analyst's morning? Reporting only
    # the second makes a working detector look broken, because most events
    # planted on a single channel are genuinely immaterial at region level.
    statistical = find_anomalies(
        decompose_for(series, contract), contract.materiality.min_abs_robust_z
    )
    in_window = [
        a for a in statistical
        if case.window_start <= a.day <= case.window_end and a.direction == "drop"
    ]
    detected = bool(in_window)
    material_detected = bool([
        a for a in material(statistical, contract)
        if case.window_start <= a.day <= case.window_end and a.direction == "drop"
    ])

    base = scoped[(day >= case.window_start - timedelta(days=BASELINE_DAYS))
                  & (day < case.window_start)]
    current = scoped[(day >= case.window_start) & (day <= case.window_end)]
    if base.empty or current.empty:
        return Outcome(case.case_id, case.expected.value, case.tags, detected,
                       material_detected, "unknown",
                       seconds=time.perf_counter() - started, error="no data in window")

    days = max((case.window_end - case.window_start).days + 1, 1)
    try:
        bridge = compute_bridge(
            base.assign(units=base["units"] / BASELINE_DAYS,
                        revenue=base["revenue"] / BASELINE_DAYS),
            current.assign(units=current["units"] / days, revenue=current["revenue"] / days),
        )
    except BridgeError as exc:
        return Outcome(case.case_id, case.expected.value, case.tags, detected,
                       material_detected, "unknown",
                       seconds=time.perf_counter() - started, error=str(exc)[:60])

    # Nothing material happened, so there is nothing to explain. Running the rest
    # of the pipeline here is how an engine ends up naming a cause for a quiet
    # week: real events elsewhere in the window verify perfectly well, they just
    # are not explanations of a movement that did not occur.
    if not material_detected:
        return Outcome(
            case.case_id, case.expected.value, case.tags, detected, material_detected,
            "no_movement", top1=False if case.true_causes else None,
            topk=False if case.true_causes else None,
            decoy_rejected=True if case.decoys else None,
            seconds=time.perf_counter() - started,
        )

    candidates, _aside = filter_relevant(
        from_operations(documents, case.window_start, case.window_end)
        + from_promotions(plan, case.window_start, case.window_end),
        case.window_start, case.window_end, case.region,
    )
    verifications = [verify(c, panel, regions) for c in candidates]

    supporting = 0
    for c, v in zip(candidates, verifications, strict=True):
        if v.state is ClaimState.VERIFIED:
            supporting += corroborate(c, documents, retriever=retriever, index=False).support_count

    explained, per_cause, overlap = explained_movement(
        verifications, panel, case.window_start, case.window_end, BASELINE_DAYS,
        total_movement=bridge.total_change,
    )
    confidence = score(verifications, explained=explained,
                       total_movement=bridge.total_change,
                       supporting_documents=supporting, sources=_fresh(contract),
                       overlap=overlap)

    verified = tuple(v.candidate.candidate_id for v in verifications
                     if v.state is ClaimState.VERIFIED)
    rejected = tuple(v.candidate.candidate_id for v in verifications
                     if v.state is ClaimState.REJECTED)
    untestable = tuple(v.candidate.candidate_id for v in verifications
                       if v.state is ClaimState.CANNOT_VERIFY)

    # Rank verified causes by how much of the movement each accounts for.
    ranked = sorted(verified, key=lambda i: -abs(per_cause.get(i, 0.0)))

    top1 = topk = None
    if case.true_causes:
        truth = set(case.true_causes)
        topk = bool(truth & set(verified))
        top1 = bool(ranked) and ranked[0] in truth

    decoy_rejected = None
    if case.decoys:
        decoy_rejected = all(d not in verified for d in case.decoys)

    return Outcome(
        case_id=case.case_id, expected=case.expected.value, tags=case.tags,
        detected=detected, material_detected=material_detected,
        verdict="unknown" if confidence.abstained else "explained",
        verified=ranked, rejected=rejected, untestable=untestable,
        confidence=confidence.score, top1=top1, topk=topk,
        decoy_rejected=decoy_rejected, seconds=time.perf_counter() - started,
    )


def compute_metrics(outcomes: list[Outcome], bins: int = 5) -> Metrics:
    m = Metrics()
    explained = [o for o in outcomes if o.verdict == "explained"]
    quiet = [o for o in outcomes if o.verdict == "no_movement"]
    with_cause = [o for o in outcomes if o.top1 is not None]
    noise = [o for o in outcomes if o.expected == ExpectedVerdict.NO_ANOMALY.value]
    with_decoy = [o for o in outcomes if o.decoy_rejected is not None]

    m.counts = {
        "cases": len(outcomes),
        "with_planted_cause": len(with_cause),
        "noise_only": len(noise),
        "decoy_bearing": len(with_decoy),
        "reported_a_cause": len(explained),
        "no_material_movement": len(quiet),
        "abstained": len(outcomes) - len(explained) - len(quiet),
        "errors": sum(1 for o in outcomes if o.error),
    }

    def rate(hits, total):
        return round(hits / total, 3) if total else None

    m.rates = {
        # Of cases with a planted cause, how often the engine named it.
        "top1_accuracy": rate(sum(1 for o in with_cause if o.top1), len(with_cause)),
        "topk_accuracy": rate(sum(1 for o in with_cause if o.topk), len(with_cause)),
        # Of cases with nothing planted, how often it claimed an explanation anyway.
        "false_alarm_rate": rate(
            sum(1 for o in noise if o.verdict == "explained"), len(noise)
        ),
        # Of planted correlation traps, how often it refused to promote one.
        "negative_control_rejection": rate(
            sum(1 for o in with_decoy if o.decoy_rejected), len(with_decoy)
        ),
        # Of abstentions, how often abstaining was right: the case was labelled
        # unanswerable, or a cause was planted and the engine could not have
        # reached it.
        "abstention_precision": rate(
            sum(1 for o in outcomes if o.verdict == "unknown"
                and (o.expected in UNANSWERABLE or not o.topk)),
            sum(1 for o in outcomes if o.verdict == "unknown"),
        ),
        # Of the cases whose *correct answer is abstention*, how often it
        # abstained.
        #
        # This denominator used to be every case where the true cause was not
        # found, which silently counted correct silences as missed abstentions:
        # a sub-threshold movement reported as "no material movement" and a
        # noise case reported as nothing at all are both right, and neither is
        # an abstention the engine failed to make. With 87 such cases in the
        # denominator the rate read 20.9% while the engine was in fact
        # abstaining on 16 of the 17 cases that called for it. The population
        # carries the label now, so the metric uses it. See B-016.
        "abstention_recall": rate(
            sum(1 for o in outcomes
                if o.expected in UNANSWERABLE and o.verdict == "unknown"),
            sum(1 for o in outcomes if o.expected in UNANSWERABLE),
        ),
        # Cases that called for an abstention and did not get one. Reported as a
        # count rather than folded into a rate, because each one is a case where
        # the engine answered something it could not support.
        "missed_abstentions": sum(
            1 for o in outcomes
            if o.expected in UNANSWERABLE and o.verdict != "unknown"
        ),
        "detection_rate": rate(
            sum(1 for o in with_cause if o.detected), len(with_cause)
        ),
        "material_detection_rate": rate(
            sum(1 for o in with_cause if o.material_detected), len(with_cause)
        ),
    }

    # Calibration is measured on the held-out half only. Reporting it over the
    # whole population would include the cases the curve was fitted on, which
    # is a measure of memorisation.
    scored = [o for o in outcomes if o.top1 is not None and o.split == "test"]
    if scored:
        edges = [i / bins for i in range(bins + 1)]
        total_error, total_n = 0.0, 0
        for lo, hi in itertools.pairwise(edges):
            bucket = [o for o in scored if lo <= o.confidence < hi or (hi == 1.0 and o.confidence == 1.0)]
            if not bucket:
                continue
            mean_score = statistics.fmean(o.confidence for o in bucket)
            accuracy = statistics.fmean(1.0 if o.top1 else 0.0 for o in bucket)
            m.calibration.append({
                "range": f"{lo:.1f}-{hi:.1f}", "n": len(bucket),
                "mean_score": round(mean_score, 3), "accuracy": round(accuracy, 3),
                "gap": round(accuracy - mean_score, 3),
            })
            total_error += len(bucket) * abs(accuracy - mean_score)
            total_n += len(bucket)
        m.ece = round(total_error / total_n, 3) if total_n else None

    times = sorted(o.seconds for o in outcomes)
    if times:
        m.latency = {
            "p50_seconds": round(times[len(times) // 2], 3),
            "p95_seconds": round(times[int(len(times) * 0.95)], 3),
            "total_seconds": round(sum(times), 1),
        }
    return m


# Panels, not cases, are split. Cases inside one panel share a generated world
# and its seasonal draws, so splitting at case level would leak the world's
# character across the boundary and flatter the calibration.
def _split_for(panel_id: int, panels: int) -> str:
    return "fit" if panel_id < panels // 2 else "test"


def run(panels: int = 10, per_region: int = 4) -> tuple[list[Outcome], Metrics]:
    contract = ContractRegistry.from_directory("contracts").get("net_revenue")
    generated = build_cases(panels=panels, per_region=per_region)
    outcomes: list[Outcome] = []

    for bench_panel in generated:
        panel, documents, plan, retriever = _materialise(bench_panel)
        split = _split_for(bench_panel.panel_id, len(generated))
        for case in bench_panel.cases:
            outcome = run_case(case, panel, documents, plan, retriever, contract)
            outcomes.append(replace(outcome, split=split))
        print(f"  panel {bench_panel.panel_id + 1}/{len(generated)}: "
              f"{len(bench_panel.cases)} cases [{split}]", flush=True)

    return outcomes, compute_metrics(outcomes)


def _materialise(bench_panel: BenchPanel):
    """Build one world and index its documents once, for all its cases."""
    from datetime import UTC

    from datagen.bulk import PANEL_DAYS, PANEL_START

    events = tuple(bench_panel.events)
    panel = build_panel(
        start=PANEL_START, end=PANEL_START + timedelta(days=PANEL_DAYS),
        events=events, seed=20260828 + bench_panel.panel_id,
    )
    documents = emit_voice_ops(panel, events, seed=13 + bench_panel.panel_id)
    plan = emit_plan_ops(panel, events, seed=11 + bench_panel.panel_id)

    tickets = documents[documents["doc_type"] == "support_ticket"]
    retriever = NumpyRetriever()
    retriever.index([
        Document(doc_id=str(r["doc_id"]), source_id="voice_ops", text=str(r["text"]),
                 ts=pd.Timestamp(r["ts"]).to_pydatetime().replace(tzinfo=UTC))
        for _, r in tickets.iterrows()
    ])
    return panel, documents, plan, retriever


def print_report(metrics: Metrics) -> None:
    print("\n" + "=" * 74)
    print("BENCHMARK")
    print("=" * 74)
    print("\nPopulation")
    for k, v in metrics.counts.items():
        print(f"  {k.replace('_', ' '):<28} {v:>6}")

    print("\nRates")
    labels = {
        "detection_rate": "planted movements seen by the detector",
        "material_detection_rate": "and large enough to be worth reporting",
        "top1_accuracy": "true cause ranked first",
        "topk_accuracy": "true cause verified at all",
        "false_alarm_rate": "explained something on noise",
        "negative_control_rejection": "correlation traps rejected",
        "abstention_precision": "abstentions that were right",
        "abstention_recall": "unanswerable cases abstained on",
        "missed_abstentions": "cases that needed an abstention and did not get one",
    }
    # Counts print as counts. Sending an integer through a percentage format
    # renders "1 missed abstention" as "100.0%", which is not a smaller mistake
    # for being cosmetic.
    counts = {"missed_abstentions"}
    for key, label in labels.items():
        value = metrics.rates.get(key)
        if value is None:
            rendered = "n/a"
        elif key in counts:
            rendered = f"{value:>6d}"
        else:
            rendered = f"{value:>6.1%}"
        print(f"  {label:<50} {rendered}")

    if metrics.calibration:
        print("\nCalibration   does a higher score mean more often right?")
        print(f"  {'score range':<14}{'n':>5}{'mean score':>12}{'accuracy':>11}{'gap':>8}")
        for row in metrics.calibration:
            print(f"  {row['range']:<14}{row['n']:>5}{row['mean_score']:>12.3f}"
                  f"{row['accuracy']:>11.3f}{row['gap']:>+8.3f}")
        print(f"  expected calibration error: {metrics.ece}")
    if metrics.calibration_fit:
        f = metrics.calibration_fit
        print("\nIsotonic calibration   fitted on a held-out split")
        if "note" in f:
            print(f"  {f['note']}")
        else:
            print(f"  fitted on {f['fitted_on']} cases ({f['split']})")
            print(f"  evaluated on {f['evaluated_on']} held-out cases")
            print(f"  ECE {f['ece_before']} -> {f['ece_after']}"
                  f"{'  (improved)' if f['improved'] else '  (no improvement, not applied)'}")

    if metrics.latency:
        print("\nLatency")
        for k, v in metrics.latency.items():
            print(f"  {k.replace('_', ' '):<28} {v:>8}")
    print()


def _jsonable(value):
    """Coerce numpy scalars on the way out of the harness.

    Comparisons on pandas and numpy values return `np.bool_`, not `bool`, and
    `json.dumps` refuses it. The failure was invisible in the worst way: the
    report printed in full, then the write raised, so `bench/report.json` kept
    the *previous* run's numbers while the terminal showed the new ones. Any
    document written from the file disagreed with the run that produced it.
    """
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"cannot serialise {type(value).__name__} into the report")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the WhyChain benchmark.")
    parser.add_argument("--panels", type=int, default=10)
    parser.add_argument("--per-region", type=int, default=4)
    parser.add_argument("--report", action="store_true", help="write bench/report.json")
    args = parser.parse_args()

    print(f"Running {args.panels} panels x 4 regions x {args.per_region} slots...")
    outcomes, metrics = run(args.panels, args.per_region)

    # Fit the calibration on the fit half, and report what it does to the held-out
    # half. The order matters: fitting after seeing the test result, or on the
    # whole population, produces a curve that reports its own training error
    # (BUGS.md T-13).
    fit_rows = [o for o in outcomes if o.split == "fit" and o.top1 is not None]
    test_rows = [o for o in outcomes if o.split == "test" and o.top1 is not None]
    curve = fit_calibration(
        [o.confidence for o in fit_rows],
        [bool(o.top1) for o in fit_rows],
        split=f"panels 0-{args.panels // 2 - 1} of {args.panels}",
    )
    if curve is not None and test_rows:
        raw = [o.confidence for o in test_rows]
        correct = [bool(o.top1) for o in test_rows]
        before = expected_calibration_error(raw, correct)
        after = expected_calibration_error([curve.probability(r) for r in raw], correct)
        curve.save()
        metrics.calibration_fit = {
            "fitted_on": curve.fitted_on,
            "split": curve.split,
            "evaluated_on": len(test_rows),
            "ece_before": before,
            "ece_after": after,
            "improved": after <= before,
        }
    elif fit_rows:
        metrics.calibration_fit = {
            "fitted_on": len(fit_rows),
            "note": (
                "not fitted: too few labelled outcomes, or the curve did not "
                "improve on the raw score. The score is reported as a score."
            ),
        }

    print_report(metrics)

    if args.report:
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(
            {
                "counts": metrics.counts, "rates": metrics.rates,
                "calibration": metrics.calibration, "ece": metrics.ece,
                "calibration_fit": metrics.calibration_fit,
                "latency": metrics.latency,
                "cases": [
                    {"case_id": o.case_id, "expected": o.expected, "tags": list(o.tags),
                     "verdict": o.verdict, "confidence": o.confidence,
                     "top1": o.top1, "decoy_rejected": o.decoy_rejected,
                     "verified": list(o.verified), "error": o.error}
                    for o in outcomes
                ],
            }, indent=2, default=_jsonable))
        print(f"written to {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
