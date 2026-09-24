"""Fill the model cache before a demo, so nothing is generated on camera.

Every model call here is a pure function of its inputs and is cached on disk by
content, so the only slow run is the first one. That is fine in a deployment and
unacceptable in a ten-minute pitch, where a stage that takes forty seconds the
first time takes forty seconds in front of the jury.

So this walks the cases the demo actually opens, with the model on, and throws
the answers away. Afterwards the console composes those cases instantly *and*
reports real model calls answered from cache, which is the honest version of a
fast demo: the work was done, it is simply not being done again.

    make warm-ai

Run it after any change to a prompt, a schema or the model, because all three
are in the cache key and a change to any of them is a different question.

It goes through HTTP, the way the console does, rather than calling the handler
as a function. The first version called `diagnose()` directly, and when the
scope filters were added to its signature the parameters it did not pass
arrived as FastAPI `Query` objects, which are truthy: every case asked for a
slice that does not exist, every case 404ed, and the script still printed that
re-running was now instant and exited 0 (B-040). Over HTTP, an omitted
parameter is omitted.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whychain.env import load_env
from whychain.llm import default_model, describe

# Before anything reads the environment, and after the imports so the path
# bootstrap above still comes first. Settings are read when a backend is
# constructed, not when this module is imported, so here is early enough.
load_env()

# The model-backed request each console scenario makes, to the day, because the
# window is inside every prompt and so inside every cache key. The first
# version warmed West 13-16 Aug while the triage row opens 13-15 Aug; the warm
# run succeeded, the cache filled, and the demo still waited on the model for
# every page. These are read off the console's own requests (`DEMOS` in
# ui/index.html): open `?demo=<id>` and copy the `/api/diagnose` call that has
# no `backend=none`. If a scenario's day changes there, it changes here.
#
# `graph`, `hourly` are absent on purpose: they are non-currency metrics, the
# endpoint refuses them with 422 before any model runs, and there is nothing to
# warm.
CASES: list[tuple[str, str]] = [
    ("trap, gap", "kpi=net_revenue&start=2026-08-13&end=2026-08-15&region=West"),
    ("channel", "kpi=net_revenue&start=2026-08-12&end=2026-08-20&region=West&channel=app"),
    ("refusal", "kpi=net_revenue&start=2026-07-27&end=2026-07-28&region=West"),
    ("contradiction", "kpi=net_revenue&start=2026-06-10&end=2026-06-12&region=North"),
    ("entitled", "kpi=net_revenue&start=2026-07-30&end=2026-08-04&entitled=South"),
    ("petroleum", "kpi=net_realisation&start=2026-08-14&end=2026-08-15&industry=petroleum"),
    # Not a scenario button, but the industry switcher reaches it in one click.
    ("power", "kpi=dispatch_realisation&start=2026-07-01&end=2026-07-05"
              "&region=North&industry=power"),
]


PERSONAS = ("analyst", "cfo", "ops")


def _totals(body: dict) -> dict:
    return (body.get("telemetry") or {}).get("totals") or {}


def main() -> int:
    backend = default_model()
    if backend is None:
        print("No model backend is reachable, so there is nothing to warm.")
        print(f"  {describe(None)}")
        print("\nThe console runs deterministically without one; this script")
        print("only matters when a demo is going to pin a backend.")
        return 0

    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    print(f"Backend      {describe(backend)}")
    print("Warming the cases the demo opens. The first pass is the slow one.\n")

    failed: list[str] = []
    total = 0.0
    # Every reader, because the decision view asks for the prose in whichever
    # persona is selected, and opens as the finance director.
    for name, query in [(f"{n} · {p}", f"{q}&persona={p}") for n, q in CASES for p in PERSONAS]:
        began = time.perf_counter()
        response = client.get(f"/api/diagnose?{query}")
        elapsed = time.perf_counter() - began
        total += elapsed
        if response.status_code != 200:
            failed.append(name)
            print(f"  {name:14s} FAILED  {response.status_code}: {response.text[:120]}")
            continue
        totals = _totals(response.json())
        print(
            f"  {name:14s} {elapsed:6.1f}s  "
            f"{totals.get('model_calls', '-')} call(s), "
            f"{totals.get('cache_hits', '-')} from cache"
        )

    # The claim this script exists to make is that nothing will be generated on
    # camera, so it is checked rather than asserted: ask again, and any case
    # that still reaches the model is named. The finance and area-sales
    # projections withhold the receipt, so they are read through the analyst's.
    print("\nChecking that a second request is answered from cache.")
    cold: list[str] = []
    for name, query in CASES:
        if any(f.startswith(name + " ") for f in failed):
            continue
        again = client.get(f"/api/diagnose?{query}")
        calls = _totals(again.json()).get("model_calls", 0) if again.status_code == 200 else None
        if calls:
            cold.append(f"{name} ({calls} live call(s))")

    print(f"\n{total:.1f}s total.")
    if failed or cold:
        if failed:
            print(f"NOT WARM, failed: {', '.join(failed)}")
        if cold:
            print(f"NOT WARM, still reaching the model: {', '.join(cold)}")
        print("Those scenarios will wait on the model in front of an audience.")
        return 1
    print(f"All {len(CASES)} cases warm, for {len(PERSONAS)} readers each. Re-running any is now instant.")
    print("Re-run this after changing a prompt, a schema or the model: all")
    print("three are in the cache key, so a change to any is a different key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
