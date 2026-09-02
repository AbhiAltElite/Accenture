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

# Which case to run twice, and it matters more than anything else in this file.
#
# This used to be retail's multi-factor case, and it made the wrong argument.
# Retail's release notes and retail's tickets already share vocabulary, so
# deterministic retrieval finds everything, the model changes nothing a reader
# can see, and the panel showed a model column with fewer sentences and more
# rejections beside a template column with more of both. The artefact built to
# show what the model contributes was demonstrating that it contributes less.
#
# Petroleum's multi-factor case is where the model does the job the README
# claims for it. A terminal writes "turnaround extended by nine days; downstream
# allocation reduced to 55 per cent of indent" and the dealer writes "no stock at
# the depot since Monday". Term-frequency retrieval bridges that by accident if
# at all, and query expansion is the stage that closes it -- which is a
# difference in what was *found*, not in how it was worded.
#
# Overridable, because the argument is stronger if a reader can point it at
# their own case and check.
CASES = {
    "petroleum": {
        "industry": "petroleum",
        "kpi": "net_realisation",
        "region": "West",
        "start": "2026-08-13",
        "end": "2026-08-16",
    },
    "retail": {
        "industry": "retail",
        "kpi": "net_revenue",
        "region": "West",
        "start": "2026-08-13",
        "end": "2026-08-16",
    },
}
# Retail by default, because it is the case the console opens on and a panel
# describing a different industry's diagnosis beside a retail page is its own
# small dishonesty.
#
# Petroleum was tried as the default on the theory that its register mismatch --
# a terminal writing "allocation reduced to 55 per cent of indent" against a
# dealer writing "no stock since Monday" -- would show the model finding
# documents term-frequency retrieval misses. Measured, it does not: the
# deterministic query clears the retrieval floor on every case in this dataset,
# so expansion never fires, and the model's extraction is *more* conservative
# than the rule table rather than broader. The mechanism works; the planted data
# does not exercise it. That is written up rather than papered over, because a
# panel arguing the model wins on evidence that says otherwise is the failure
# this whole engine is built against.
CASE = CASES["retail"]


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

    # What the model actually changes, and the reason the panel exists. Sentence
    # counts were the only thing measured here, which is the least interesting
    # difference and the one that flatters the template: retrieval is where a
    # register mismatch is either bridged or not.
    verified = result.get("verified") or []
    corroborate = next(
        (st for st in (telemetry.get("stages") or [])
         if st.get("stage") == "corroborate"),
        {},
    )

    return {
        "narrative": narrative.get("text", ""),
        "writer": narrative.get("writer"),
        "documents_found": sum(v.get("supporting_documents") or 0 for v in verified),
        "retrieval_note": corroborate.get("note", ""),
        # How many document spans ended up cited. This sat in `figures` below,
        # among the values asserted to be identical, and it does not belong
        # there: it is an output of *reading*, which is the one thing the model
        # is supposed to change. The invariant as written made a correctly
        # working model trip a "correctness defect" alarm, which is worse than
        # not checking -- it teaches a reader to distrust the check.
        "citations": sum(
            len(v.get("citations") or []) for v in verified
        ),
        "sentences": len(narrative.get("sentences") or []),
        "rejected": len(validation.get("rejected") or []),
        "rejections": [
            {"failure": r["failure"], "detail": r["detail"]}
            for r in (validation.get("rejected") or [])
        ],
        "model_calls": totals.get("model_calls", 0),
        "tokens": (totals.get("tokens_in") or 0) + (totals.get("tokens_out") or 0),
        "seconds": totals.get("seconds"),
        # The half that must not move: the movement, what explains it, how
        # confident the engine is, and which candidates survived testing. The
        # README's claim is exactly this list and no more.
        "figures": {
            "total_change": movement.get("total_change"),
            "explained": movement.get("explained"),
            "confidence": (result.get("confidence") or {}).get("score"),
            "verdict": result.get("verdict"),
            "verified": sorted(
                v["candidate_id"] for v in (result.get("verified") or [])
            ),
        },
    }


def main() -> int:
    global CASE
    if len(sys.argv) > 1:
        if sys.argv[1] not in CASES:
            print(f"unknown case {sys.argv[1]!r}; choose from {sorted(CASES)}")
            return 2
        CASE = CASES[sys.argv[1]]

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
                    "What differs is how many of the operational documents were "
                    "found at all, and how the sentences were written."
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
