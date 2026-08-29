# Context, read this first

**Any new session, new teammate, or return after a gap starts here.**

## What WhyChain is

An engine that takes a business metric that materially moved and answers two questions:

1. **What caused it**, a causally tested explanation where every sentence resolves on click to the exact query, rows, or source document behind it.
2. **Why it went unanticipated**, which warning signal existed, which process failed to consume it, how often this has recurred, who owns it, and what should now be monitored.

It sits on top of existing BI rather than replacing it.

## The one rule everything else serves

> **The quantitative layer is deterministic. The language model reads, ranks and writes, it never calculates, and it never decides what is true.**

A polished false diagnosis is worse than an explicit UNKNOWN. If a change would let the model determine a number, a causal status, an owner, a threshold, or an authorisation, that change is wrong regardless of how good the output looks.

## Architecture in one screen

```
sources (3 grains + 1 external feed)
   ↓ reconcile · freshness gate
detect (MSTL → robust z on residual)
   ↓ materiality (statistical AND ₹)
decompose (price/volume/mix bridge, exact identity)
   ↓
rank  ├─ track A: exact, from the bridge
      └─ track B: ridge, labelled CORRELATIONAL, never merged with A
   ↓
verify (event-time isolation ∧ DiD ∧ placebo)   ← only survivors become claims
   ↓
corroborate (retrieval + span-cited extraction)   ← LLM call 1 of 2
   ↓
confidence (deterministic score → isotonic calibration) → abstain if weak
   ↓
actions (driver → lever → impact → owner → monitoring)  ← every field derived
   ↓
signal gap (Answer 2) → monitoring plan
   ↓
narrate (constrained to the evidence table)       ← LLM call 2 of 2
   ↓
validate (binding + numeral + entity + rejected-cause checks)
   ↓
feedback (bounded: business inputs only, never a computed value)
```

**Two model calls per diagnosis is the design.** Both stages now exist. The
narrate stage makes its call only when `ANTHROPIC_API_KEY` is set; without one
it falls back to a deterministic template over the same evidence table, put
through the same validator, and the receipt reports the count it *observed*
rather than the count intended. The corroboration extractor is still rule-based.
So a keyless clone reports zero model calls and says so, and that is the honest
reading rather than a missing feature. SOP parsing happens once at contract
registration, offline, and stays outside the per-diagnosis count either way.

**The validator is the load-bearing part of the narrative stage.** The model
writes sentences carrying evidence ids; a deterministic checker then rejects any
sentence that cites nothing, prints a figure not present in a fact it cites,
names an entity the evidence does not contain, or states a rejected candidate as
a cause. Rejected sentences are dropped and counted on the receipt, never
repaired. If every sentence fails, the template writes it and the fallback is
reported.

**The bridge applies to `net_revenue` alone.** It is an identity over priced
units; a rate has no units to move and no price to change. Each contract
declares whether it can be decomposed, and the other four decline.

## Where things live

| Path | Contents |
|---|---|
| `whychain/` | the engine, one package per pipeline stage |
| `whychain/evidence/` | the `Evidence` type, the spine of the system |
| `contracts/` | KPI semantic contracts (YAML), executable governance |
| `datagen/` | synthetic dataset generator + planted causes |
| `data/ground_truth/` | **the engine must never read this.** Enforced by test |
| `bench/` | benchmark harness and metrics |
| `api/`, `ui/` | service and console |
| `docs/` | design and product specs (public) |
| `_internal/` | team-only material, gitignored |

## Documents, and when to read them

| Doc | Read when |
|---|---|
| `CONTEXT.md` | starting any session |
| `HANDOFF.md` | picking up where someone stopped |
| `DECISIONS.md` | **before proposing an architectural change**; it may already have been decided and rejected |
| `BUGS.md` | before writing a stage; it lists traps already identified |
| `docs/BRIEF.md` | **the brief, verbatim. It is the authority on scope; read it rather than recalling it** |
| `docs/REQUIREMENTS.md` | checking the build against the brief, objective by objective |
| `docs/PROTOTYPE-SPEC.md` | implementing a stage |
| `docs/SECURITY-LOGIC-CHECKLIST.md` | writing tests, or before demoing |
| `docs/DESIGN-CHECKLIST.md` | building any UI |
| `docs/PRODUCT-OUTLINE.md` | deciding what a feature should do |
| `docs/CONCEPTS.md` | any unfamiliar term |

## How to check progress

The engine is built bottom-up, so there is no interface until detection lands.
Until then:

```bash
make status    # read the real contracts through the real loader
make test      # 258 tests; -m invariant for the 106 hard correctness ones
make audit     # 30 executable security, logic and design checks
make bench     # accuracy, trap rejection, calibration, latency
```

`make audit` and `make bench` both need `make gen` to have run. Without a
warehouse the audit reports ten failures that are all the same missing file.

`make status` is not a mock, if it prints the KPI graph, the governance layer
genuinely loads and cross-validates.

### When each phase becomes visible

| Phase | Built | What you can see |
|---|---|---|
| 1 ✅ | evidence model, retrieval, contracts | `make status`, `make test` |
| 2 ✅ | data generation | `make gen` then query the DuckDB file directly |
| 3 ✅ | reconcile + detect | metric chart, expected band, anomaly window |
| 4 ✅ | decompose + verify | contribution table, candidates, rejected ones with the test that killed each |
| 5 ✅ | corroborate + confidence + narrate + validate | the diagnosis, click-to-evidence, UNKNOWN when weak, and a live count of sentences the validator rejected |
| 6 ✅ | actions + telemetry + personas + signal gap + feedback | decision card with lever, owner, impact and monitoring rule; Answer 2 with all four verdicts; three reader projections; run receipt; bounded correction loop |
| 7 ✅ | benchmark | `make bench`, accuracy, trap rejection, calibration, latency |

**Where the honest line is.** Every stage in the diagram above now exists in
code and runs. Two things remain true and should be stated rather than glossed:

- **The corroboration extractor is rule-based**, so a keyless clone makes zero
  model calls, not two. The receipt reports what happened.
- **`ext_signals` is generated**, and every row says `source: generated`. The
  schema is the one a cached IMD or Open-Meteo snapshot drops into unchanged,
  and until one does, no document may claim a live external feed.

**What the benchmark says, over 160 labelled cases.** Of the 70 movements
that clear both materiality tests, the true cause is ranked first in 78.6%;
over the whole population, including movements not worth explaining, top-1 is
38.2%. False alarms on noise 0.0%. Planted correlation traps rejected
87.5%. Of the 17 cases whose correct answer is an abstention, 94.1% got
one, and 1 did not. Expected calibration error 0.1171 raw, 0.1043 after an
isotonic curve fitted on a held-out half. p95 latency 0.178s.

**Two of those figures have moved for reasons worth knowing before quoting
them.** B-014: benchmark cases were sitting inside each other's baseline
windows, so an earlier run reported 46.4% top-1 and a perfect conditional rate,
and the numbers got worse when the measurement got honest. B-016: abstention
recall counted correct silences as missed abstentions, reading 20.9% while the
engine was in fact abstaining on 16 of the 17 cases that called for it. Both
are written up in `BUGS.md` with the old numbers.

Read a claim in `docs/PROTOTYPE-SPEC.md` or `docs/PRODUCT-OUTLINE.md` as a
design intent, not a description of the running system. This file and
`HANDOFF.md` are the ones kept honest about what is built.

## Current state

See `HANDOFF.md`.
