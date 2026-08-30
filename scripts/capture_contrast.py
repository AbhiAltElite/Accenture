"""Run one diagnosis twice, with the model and without, and keep both.

A reader who clones this repository and runs it will almost certainly have no
model backend configured. They see a complete diagnosis, a receipt reporting
zero model calls, and no way to tell whether the model stages exist at all.
Telling them the stages are there is worth less than showing what they do.

So this captures the same case under both conditions and writes the pair to
`data/demo/contrast.json`. The console renders it beside the narrative, which
turns an invisible capability into a visible one and makes the central claim
checkable rather than asserted:

**The numbers are byte-identical.** Same movement, same verified causes, same
contributions, same confidence, same verdict. That is the claim the whole
architecture rests on, and a reader can compare the two columns rather than
take it on trust.

**The prose and the reading differ.** The model catches tickets phrased in ways
no keyword table anticipates, and writes better sentences. Both go through the
same validator, and the rejection counts are recorded for each.

This is generated, never hand-written. With no backend reachable it refuses to
write anything, because a fabricated "this is what the model would have said"
would be precisely the unearned claim the rest of this project argues against.
Run it once, with a backend, and commit the artefact.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whychain.env import load_env
from whychain.llm import default_model, describe

# Before anything reads the environment, and after the imports so the path
# bootstrap above still comes first. Settings are read when a backend is
# constructed, not when this module is imported, so here is early enough.
load_env()

OUT = Path("data/demo/contrast.json")

# The multi-factor demo case: three verified causes, a planted decoy, and enough
# tickets that the difference between a keyword table and a reader is visible.
CASE = {
    "industry": "retail",
    "kpi": "net_revenue",
    "region": "West",
    "start": "2026-08-13",
    "end": "2026-08-16",
}


def _diagnose(backend: str) -> dict:
    """One run through the real API function, not a reimplementation of it."""
    from datetime import date

    from api.main import diagnose

    return diagnose(
        kpi=CASE["kpi"],
        region=CASE["region"],
        event_start=date.fromisoformat(CASE["start"]),
        event_end=date.fromisoformat(CASE["end"]),
        baseline_days=14,
        persona="analyst",
        entitled=None,
        price_delta=-0.05,
        horizon_days=14,
        backend=backend,
        llm_model=None,
        # Named explicitly because this calls the endpoint as a plain function.
        # Every parameter left out falls back to its FastAPI `Query(...)`
        # default, which is a Query object rather than the value it wraps, and
        # `_vertical` correctly refuses it as an unknown industry.
        industry=CASE["industry"],
    )


def _summarise(result: dict) -> dict:
    narrative = result.get("narrative") or {}
    validation = narrative.get("validation") or {}
    telemetry = result.get("telemetry") or {}
    totals = telemetry.get("totals") or {}
    movement = result.get("movement") or {}

    return {
        "narrative": narrative.get("text", ""),
        "writer": narrative.get("writer"),
        "sentences": len(narrative.get("sentences") or []),
        "rejected": len(validation.get("rejected") or []),
        "rejections": [
            {"failure": r["failure"], "detail": r["detail"]}
            for r in (validation.get("rejected") or [])
        ],
        "model_calls": totals.get("model_calls", 0),
        "tokens": (totals.get("tokens_in") or 0) + (totals.get("tokens_out") or 0),
        "seconds": totals.get("seconds"),
        # The half that must not move. Compared field by field below.
        "figures": {
            "total_change": movement.get("total_change"),
            "explained": movement.get("explained"),
            "confidence": (result.get("confidence") or {}).get("score"),
            "verdict": result.get("verdict"),
            "verified": sorted(
                v["candidate_id"] for v in (result.get("verified") or [])
            ),
            "citations": sum(
                len(v.get("citations") or []) for v in (result.get("verified") or [])
            ),
        },
    }


def main() -> int:
    backend = default_model()
    if backend is None:
        print("No model backend is reachable, so there is nothing to contrast.")
        print(f"  {describe(None)}")
        print("\nThis script deliberately writes nothing in that state. An")
        print("artefact claiming to show what a model produced, generated")
        print("without running one, would be the exact failure this engine")
        print("exists to prevent.")
        return 1

    print(f"Backend      {describe(backend)}")
    print("Running the same case twice, with the model and without.\n")

    with_model = _summarise(_diagnose("ollama" if backend.backend == "ollama" else "openai"))
    without = _summarise(_diagnose("none"))

    # The claim, checked rather than asserted. If this ever fails, the model has
    # reached something it must not reach, and that is a defect, not a note.
    drifted = [
        key
        for key in with_model["figures"]
        if with_model["figures"][key] != without["figures"][key]
    ]
    if drifted:
        print("FAILED: the model changed a computed value.")
        for key in drifted:
            print(f"  {key}: {without['figures'][key]!r} -> {with_model['figures'][key]!r}")
        print("\nNothing written. This is a correctness defect in the pipeline,")
        print("not a difference worth displaying.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "case": CASE,
                "captured_at": datetime.now(UTC).isoformat(),
                "backend": describe(backend),
                "with_model": with_model,
                "without_model": without,
                "figures_identical": True,
                "note": (
                    "The same case run twice. Every computed figure is identical "
                    "because the model reads and writes and never calculates. "
                    "What differs is how the tickets were read and how the "
                    "sentences were written."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"with model     {with_model['model_calls']} call(s), "
          f"{with_model['tokens']} tokens, {with_model['sentences']} sentence(s), "
          f"{with_model['rejected']} rejected")
    print(f"without        {without['model_calls']} call(s), "
          f"{without['sentences']} sentence(s), {without['rejected']} rejected")
    print("\nEvery computed figure identical across both runs.")
    print(f"written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
