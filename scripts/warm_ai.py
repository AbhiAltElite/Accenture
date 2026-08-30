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
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whychain.env import load_env
from whychain.llm import default_model, describe

# Before anything reads the environment, and after the imports so the path
# bootstrap above still comes first. Settings are read when a backend is
# constructed, not when this module is imported, so here is early enough.
load_env()

# The windows the console opens on, per industry. Kept short deliberately: the
# point is to warm what a demo touches, not to precompute the whole warehouse.
CASES = [
    ("retail", "net_revenue", "West", date(2026, 8, 13), date(2026, 8, 16)),
    ("petroleum", "net_realisation", "West", date(2026, 8, 14), date(2026, 8, 18)),
    ("power", "dispatch_realisation", "South", date(2026, 5, 11), date(2026, 5, 16)),
]


def main() -> int:
    backend = default_model()
    if backend is None:
        print("No model backend is reachable, so there is nothing to warm.")
        print(f"  {describe(None)}")
        print("\nThe console runs deterministically without one; this script")
        print("only matters when a demo is going to pin a backend.")
        return 0

    print(f"Backend      {describe(backend)}")
    print("Warming the cases the demo opens. The first pass is the slow one.\n")

    from api.main import diagnose

    total = 0.0
    for industry, kpi, region, start, end in CASES:
        began = time.perf_counter()
        try:
            result = diagnose(
                kpi=kpi, region=region, event_start=start, event_end=end,
                baseline_days=14, persona="analyst", entitled=None,
                price_delta=-0.05, horizon_days=14, backend=None,
                llm_model=None, industry=industry,
            )
        except Exception as exc:
            print(f"  {industry:11s} FAILED  {type(exc).__name__}: {exc}")
            continue
        elapsed = time.perf_counter() - began
        total += elapsed
        totals = result.get("telemetry", {}).get("totals", {})
        print(
            f"  {industry:11s} {elapsed:6.1f}s  "
            f"{totals.get('model_calls', 0)} call(s), "
            f"{totals.get('cache_hits', 0)} from cache"
        )

    print(f"\n{total:.1f}s total. Re-running any of these is now instant.")
    print("Re-run this after changing a prompt, a schema or the model: all")
    print("three are in the cache key, so a change to any is a different key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
