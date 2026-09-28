"""How accurately each reader classifies support tickets: `make eval-extraction`.

Two readers, the same tickets, one scoring rule.

- **rules**: the keyword table (`RuleExtractor`), offline and deterministic.
- **model**: the language model (`ModelExtractor`), whose citation must be found
  verbatim in the ticket or the reading is dropped.

Three sets:

- **generator, in vocabulary**: every distinct complaint the data generator
  writes in words the keyword table was built from, once each.
- **generator, off vocabulary**: every distinct complaint it writes in words
  deliberately kept out of that table. The ones the model is there for.
- **held out**: `bench/tickets_heldout.json`, harder tickets labelled and
  committed before either reader was run on them.

Plus every ticket that describes no problem, which measures false alarms: a
reader that sees a checkout failure in "delivery was on time" is worse than one
that sees nothing.

A reading is **correct** when it names an accepted issue and no other event
issue. Each distinct phrasing is scored once; random draws from a pool of 23
phrasings would count the same sentence many times and inflate the total.

The honest limit, printed with the result: every ticket here was written by the
team, not by a customer. This measures the reader on hard phrasing we could
think of, not on the phrasing a real estate holds. That needs a client's
labelled tickets.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datagen.scenarios import CauseKind  # noqa: E402
from datagen.voices import RETAIL_VOICES, _distort  # noqa: E402
from whychain.corroborate.extract import RuleExtractor  # noqa: E402
from whychain.corroborate.quarantine import quarantine  # noqa: E402
from whychain.env import load_env  # noqa: E402

HELDOUT = ROOT / "bench" / "tickets_heldout.json"
REPORT = ROOT / "bench" / "extraction.json"

# The issues a movement's cause is read from. `quality` and `other` are what an
# ordinary contact is about, so reading one of them from a no-problem ticket is
# not an alarm.
EVENT = {"checkout_failure", "payment_failure", "delivery_delay", "stockout", "pricing"}

# What a correct reading of each planted cause is. A broken release shows up to
# a customer as a checkout or a payment failure, and either is a right reading.
EXPECT = {
    CauseKind.INTERNAL_BUG: ["checkout_failure", "payment_failure"],
    CauseKind.EXTERNAL_WEATHER: ["delivery_delay"],
    CauseKind.STOCKOUT: ["stockout"],
    CauseKind.COMPETITOR_PROMO: ["pricing"],
    CauseKind.PRICE_CHANGE: ["pricing"],
}


def tickets() -> list[dict]:
    rng = random.Random(26092026)
    pack = RETAIL_VOICES
    out: list[dict] = []

    def compose(body: str) -> str:
        return _distort(rng.choice(pack.openers) + body + rng.choice(pack.closers), rng, pack.typos)

    for label, pool in (("generator, in vocabulary", pack.in_vocabulary),
                        ("generator, off vocabulary", pack.off_vocabulary)):
        for kind, bodies in pool.items():
            for body in bodies:
                out.append({"id": f"G{len(out):03d}", "set": label, "text": compose(body),
                            "expect": EXPECT[kind]})
    for body in pack.background:
        out.append({"id": f"G{len(out):03d}", "set": "no problem", "text": compose(body),
                    "expect": []})
    for t in json.loads(HELDOUT.read_text(encoding="utf-8"))["tickets"]:
        out.append({**t, "set": "held out" if t["expect"] else "no problem"})
    # Mixed, as a real batch is: problems and ordinary contacts side by side.
    rng.shuffle(out)
    return out


def score(items: list[dict], readings: dict[str, set[str]]) -> dict:
    by_set: dict[str, dict] = defaultdict(lambda: {"n": 0, "right": 0, "misses": []})
    for t in items:
        got = readings.get(t["id"], set())
        row = by_set[t["set"]]
        row["n"] += 1
        if t["expect"]:
            ok = bool(got & set(t["expect"])) and (got & EVENT) <= set(t["expect"])
        else:
            ok = not (got & EVENT)  # right means no false alarm
        if ok:
            row["right"] += 1
        else:
            row["misses"].append({"id": t["id"], "text": t["text"], "expected": t["expect"],
                                  "read": sorted(got)})
    return {k: {**v, "pct": round(100 * v["right"] / v["n"], 1)} for k, v in by_set.items()}


def read_rules(docs) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for e in RuleExtractor().extract(docs):
        out[e.doc_id].add(str(e.issue))
    return out


def read_model(docs) -> tuple[dict[str, set[str]], dict]:
    from whychain.corroborate.model_extract import ModelExtractor
    extractor = ModelExtractor()
    if not extractor.available:
        raise SystemExit("No model backend is configured; set it in .env (see make verify-ai).")
    started = time.perf_counter()
    found = extractor.extract(docs)
    if "failed" in extractor.note or "rule-based" in extractor.note:
        # The extractor falls back to the rules rather than fail a diagnosis.
        # Scoring that as the model would credit the rules to it.
        raise SystemExit(f"The model did not answer: {extractor.note}")
    out: dict[str, set[str]] = defaultdict(set)
    for e in found:
        out[e.doc_id].add(str(e.issue))
    return out, {"model": extractor.model, "calls": extractor.calls,
                 "cache_hits": extractor.cache_hits,
                 "readings": len(found), "citations_dropped": len(extractor.dropped),
                 "dropped": list(extractor.dropped),
                 "seconds": round(time.perf_counter() - started, 1)}


ORDER = ("generator, in vocabulary", "generator, off vocabulary", "held out", "no problem")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", type=int, default=3, help="model runs, to show how much it varies")
    parser.add_argument("--rules-only", action="store_true")
    args = parser.parse_args()
    load_env()

    items = tickets()
    docs = [quarantine(t["id"], t["text"]) for t in items]
    report = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "tickets": len(items),
              "sets": {k: sum(t["set"] == k for t in items) for k in ORDER},
              "rules": score(items, read_rules(docs)), "model_runs": []}
    if not args.rules_only:
        for _ in range(args.runs):
            readings, receipt = read_model(docs)
            report["model_runs"].append({**receipt, "score": score(items, readings)})

    print(f"{len(items)} tickets, each distinct phrasing once\n")
    head = f"{'set':28} {'n':>4}  {'rules':>7}"
    runs = report["model_runs"]
    head += "".join(f"  {'model ' + str(i + 1):>8}" for i in range(len(runs)))
    print(head)
    for k in ORDER:
        n = report["sets"][k]
        line = f"{k:28} {n:>4}  {report['rules'][k]['pct']:>6.1f}%"
        for r in runs:
            line += f"  {r['score'][k]['pct']:>7.1f}%"
        print(line)
    print("\n(no problem: the share with no false alarm)")
    for i, r in enumerate(runs, 1):
        print(f"model {i}: {r['model']}, {r['calls']} call(s), {r['cache_hits']} cached, "
              f"{r['readings']} readings, {r['citations_dropped']} dropped for a quote not in "
              f"the ticket, {r['seconds']} s")
    print("\nEvery ticket was written by the team, not by a customer. See bench/extraction.json.")

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())
