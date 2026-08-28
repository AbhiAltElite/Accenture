"""Show the guardrails refusing bad input.

A guardrail described in a document is a claim. A guardrail you can watch reject
something is a mechanism. This script deliberately feeds the engine input it must
refuse, and prints what happened.

    make guardrails
"""

from __future__ import annotations

import sys
import warnings
from datetime import date, datetime, timedelta

import pandas as pd

warnings.filterwarnings("ignore")

FAILURES: list[str] = []


def attempt(label: str, fn) -> None:
    """Run something that must be refused, and report whether it was."""
    try:
        fn()
    except Exception as exc:
        first = str(exc).split("\n")[1].strip() if "\n" in str(exc) else str(exc)
        print(f"  refused   {label}")
        print(f"            {first[:100]}")
        return
    print(f"  ALLOWED   {label}")
    FAILURES.append(label)


def type_guardrails() -> None:
    from whychain.evidence import (
        Evidence,
        EvidenceKind,
        Freshness,
        MethodClass,
        Provenance,
        Unit,
    )

    def evidence(**kw):
        base = {
            "id": "e", "kind": EvidenceKind.DECOMPOSITION, "claim": "x", "value": 1.0,
            "unit": Unit.INR, "method": "pvm_bridge",
            "method_class": MethodClass.DETERMINISTIC,
            "provenance": Provenance(source_id="s", query="SELECT 1"), "run_id": "r",
        }
        return Evidence(**{**base, **kw})

    print("\nTYPE GUARDRAILS   enforced when a fact is constructed")
    attempt("a bridge reporting order counts instead of rupees",
            lambda: evidence(unit=Unit.COUNT))
    attempt("a difference-in-differences result labelled percent, not percentage point",
            lambda: evidence(method="did", unit=Unit.PCT))
    attempt("evidence with neither a query nor a document behind it",
            lambda: Provenance(source_id="pos_txn"))
    attempt("a document citation with no character span",
            lambda: Provenance(source_id="voice_ops", doc_id="TK1"))
    attempt("an inverted confidence interval", lambda: evidence(ci=(0.9, 0.1)))
    attempt("a confidence outside zero to one", lambda: evidence(confidence=1.4))
    attempt("a naive timestamp in freshness arithmetic",
            lambda: Freshness(
                source_id="s",
                as_of=datetime(2026, 8, 1),  # noqa: DTZ001
                observed_at=datetime(2026, 8, 2),  # noqa: DTZ001
                sla=timedelta(hours=6),
            ))


def arithmetic_guardrails() -> None:
    from whychain.decompose import contribution_by
    from whychain.decompose.bridge import Bridge

    print("\nARITHMETIC GUARDRAILS   the identity is checked before anything is reported")
    attempt("a bridge whose legs do not sum to the movement",
            lambda: Bridge(
                base_revenue=1000.0, current_revenue=900.0, volume_effect=-10.0,
                mix_effect=0.0, price_effect=0.0, base_units=10.0,
                current_units=9.0, products=1,
            ).assert_reconciles())
    attempt("contribution over a dimension that does not exist",
            lambda: contribution_by(
                pd.DataFrame({"region": ["W"], "revenue": [1.0]}),
                pd.DataFrame({"region": ["W"], "revenue": [2.0]}), "planet"))


def graph_guardrails() -> None:
    from whychain.evidence import (
        Evidence,
        EvidenceKind,
        EvidenceStore,
        MethodClass,
        Provenance,
        Unit,
    )

    store = EvidenceStore("run")

    def record(**kw):
        base = {
            "id": store.next_id(), "kind": EvidenceKind.ANOMALY, "claim": "x",
            "value": 1.0, "unit": Unit.RATIO, "method": "mstl_robust_z",
            "method_class": MethodClass.STATISTICAL,
            "provenance": Provenance(source_id="s", query="SELECT 1"), "run_id": "run",
        }
        return Evidence(**{**base, **kw})

    first = store.add(record())

    print("\nEVIDENCE GRAPH GUARDRAILS")
    attempt("citing evidence that does not exist",
            lambda: store.add(record(supports=("ev_9999",))))
    attempt("mutating a fact after it was recorded",
            lambda: setattr(first, "claim", "something else"))
    attempt("recording the same fact twice", lambda: store.add(first))
    attempt("resolving an unknown id, as the narrative validator will",
            lambda: store.resolve_all([first.id, "ev_9999"]))
    attempt("evidence belonging to another run",
            lambda: store.add(record(run_id="other_run")))


def access_guardrails() -> None:
    from whychain.contracts import ContractRegistry
    from whychain.ingest import Warehouse

    contract = ContractRegistry.from_directory("contracts").get("net_revenue")
    print("\nACCESS GUARDRAILS")
    with Warehouse() as wh:
        attempt("an empty entitlement treated as unrestricted",
                lambda: wh.kpi_series(contract, entitled_regions=()))
        attempt("the engine writing to the source of truth",
                lambda: wh._con.execute("CREATE TABLE probe(x INT)"))


def contract_guardrails() -> None:
    from whychain.contracts import (
        ContractError,
        ContractRegistry,
        Coverage,
        Driver,
        SignalsConsumed,
    )

    print("\nCONTRACT GUARDRAILS   at load, so a bad contract never runs")
    attempt("a controllable lever with nobody accountable",
            lambda: Driver(id="price", source="pos_txn", controllable_lever="pricing"))
    attempt("claiming signal coverage with no source document",
            lambda: SignalsConsumed(coverage=Coverage.COMPLETE))
    attempt("loading contracts from a directory that has none",
            lambda: ContractRegistry.from_directory("scripts"))
    _ = ContractError


def verification_guardrails() -> None:
    from whychain.evidence import ClaimState
    from whychain.verify import Candidate, verify

    print("\nVERIFICATION GUARDRAILS   an untestable candidate is never a verified one")
    days = pd.date_range("2026-06-01", "2026-09-01", freq="D")
    everywhere = pd.DataFrame([
        {"d": d, "region": r, "channel": "app", "device": "mobile", "category": "x",
         "revenue": 100_000.0 * (0.75 if d.date() >= date(2026, 8, 12) else 1.0),
         "units": 500.0}
        for d in days for r in ("North", "South", "East", "West")
    ])
    candidate = Candidate(
        candidate_id="everywhere", kind="test",
        start=date(2026, 8, 12), end=date(2026, 8, 18),
        exposed_regions=("North", "South", "East", "West"),
    )
    result = verify(candidate, everywhere, ("North", "South", "East", "West"))
    if result.state is ClaimState.VERIFIED:
        print("  ALLOWED   a cause present everywhere reported as verified")
        FAILURES.append("verification without a comparison group")
    else:
        print("  refused   a cause present everywhere, so no comparison group exists")
        print(f"            {result.state.value}: {result.reason}")


def main() -> int:
    print("Feeding the engine input it must refuse.")
    for section in (
        type_guardrails, arithmetic_guardrails, graph_guardrails,
        access_guardrails, contract_guardrails, verification_guardrails,
    ):
        section()

    print("\nNOT YET GUARDED, because the stage does not exist yet:")
    for pending in (
        "narrative binding: every sentence must resolve to evidence",
        "numeral checking: every number in the text must match its cited evidence",
        "prompt injection: retrieved ticket text treated as data, never instruction",
        "confidence calibration: a stated 80 per cent must be right 80 per cent of the time",
    ):
        print(f"  pending   {pending}")

    if FAILURES:
        print(f"\n{len(FAILURES)} guardrail(s) did not fire:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nEvery guardrail fired.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
