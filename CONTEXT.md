# Context — read this first

**Any new session, new teammate, or return after a gap starts here.**

## What WhyChain is

An engine that takes a business metric that materially moved and answers two questions:

1. **What caused it** — a causally tested explanation where every sentence resolves on click to the exact query, rows, or source document behind it.
2. **Why it went unanticipated** — which warning signal existed, which process failed to consume it, how often this has recurred, who owns it, and what should now be monitored.

It sits on top of existing BI rather than replacing it.

## The one rule everything else serves

> **The quantitative layer is deterministic. The language model reads, ranks and writes — it never calculates, and it never decides what is true.**

A polished false diagnosis is worse than an explicit UNKNOWN. If a change would let the model determine a number, a causal status, an owner, a threshold, or an authorisation, that change is wrong regardless of how good the output looks.

## Architecture in one screen

```
sources (3 grains + 1 external feed)
   ↓ reconcile · freshness gate
detect (MSTL → robust z on residual)
   ↓ materiality (statistical AND ₹)
decompose (price/volume/mix bridge — exact identity)
   ↓
rank  ├─ track A: exact, from the bridge
      └─ track B: ridge/lasso, labelled CORRELATIONAL
   ↓
verify (event-time isolation ∧ DiD ∧ placebo)   ← only survivors become claims
   ↓
corroborate (retrieval + span-cited extraction)   ← LLM call 1 of 2
   ↓
confidence (deterministic score → isotonic calibration) → abstain if weak
   ↓
actions (driver → lever → impact → owner → monitoring)  ← every field derived
   ↓
scenarios (if we act) ← projections, assumptions stated, never causal facts
   ↓
signal gap (Answer 2) → monitoring plan           ← NOT BUILT
   ↓
narrate (constrained to the evidence table)       ← NOT BUILT (LLM call 2 of 2)
   ↓
validate (binding + numeral + entity checks)      ← NOT BUILT
   ↓
project (persona + entitlement)                   ← the last stage, always
```

**Two model calls per diagnosis is the design.** The running system currently
makes zero: the extractor behind the corroboration protocol is rule-based and
there is no narrate stage, so the narrative comes from a deterministic template.
The run receipt reports the count it observed rather than the count intended, so
this is visible rather than assumed. SOP parsing happens once at contract
registration, offline, and stays outside the per-diagnosis count either way.

**The bridge applies to `net_revenue` alone.** It is an identity over priced
units; a rate has no units to move and no price to change. Each contract
declares whether it can be decomposed, and the other four decline.

## Where things live

| Path | Contents |
|---|---|
| `whychain/` | the engine, one package per pipeline stage |
| `whychain/evidence/` | the `Evidence` type — the spine of the system |
| `contracts/` | KPI semantic contracts (YAML) — executable governance |
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
| `DECISIONS.md` | **before proposing an architectural change** — it may already have been decided and rejected |
| `BUGS.md` | before writing a stage; it lists traps already identified |
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
make test      # 160 tests; -m invariant for the hard correctness ones
make audit     # 30 executable security, logic and design checks
make bench     # accuracy, trap rejection, calibration, latency
```

`make audit` and `make bench` both need `make gen` to have run. Without a
warehouse the audit reports ten failures that are all the same missing file.

`make status` is not a mock — if it prints the KPI graph, the governance layer
genuinely loads and cross-validates.

### When each phase becomes visible

| Phase | Built | What you can see |
|---|---|---|
| 1 ✅ | evidence model, retrieval, contracts | `make status`, `make test` |
| 2 ✅ | data generation | `make gen` then query the DuckDB file directly |
| 3 ✅ | reconcile + detect | metric chart, expected band, anomaly window |
| 4 ✅ | decompose + verify | contribution table, candidates, rejected ones with the test that killed each |
| 5 ◐ | corroborate + confidence | the diagnosis, click-to-evidence, UNKNOWN when weak. **narrate and validate are not built**: the narrative is a deterministic template |
| 6 ◐ | actions + personas + telemetry | decision card with lever, owner, impact and monitoring rule; impact scenarios; CFO/ops/analyst projections with entitlement enforced and announced; run receipt. **Answer 2 is not built** |
| 7 ✅ | benchmark | `make bench` — accuracy, trap rejection, calibration, latency |

**Where the honest line is.** `whychain/signalgap/`, `whychain/narrate/` and
`whychain/rank/` are empty files. Answer 2, the model-written narrative and the
two-track ranking are specified in `docs/` and do not exist in code. Everything
else in the diagram above runs.

Read a claim in `docs/PROTOTYPE-SPEC.md` or `docs/PRODUCT-OUTLINE.md` as a
design intent, not a description of the running system. This file and
`HANDOFF.md` are the ones kept honest about what is built.

## Current state

See `HANDOFF.md`.
