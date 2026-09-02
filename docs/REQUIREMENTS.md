# Requirement → implementation

Every objective and every minimum expectation in the Round 2 brief, mapped to
the code that satisfies it and the command that shows it running. A row that
says "partial" says so; a matrix with a quietly missing row is worse than no
matrix, because it reads as complete.

Run these first, in order. Everything below is reachable from them.

```bash
make setup && make gen-all    # venv, dependencies, all three industries' datasets
make test                     # 440 tests, of which many are marked invariant
make audit                    # 30 executable security, logic and design checks
make bench                    # accuracy, trap rejection, calibration, latency
make demo                     # console at http://localhost:8000
```

`make gen` builds retail alone, which is enough to see everything the eight
objectives are demonstrated against. `make gen-all` adds the petroleum and power
verticals, which is what the scalability criterion rests on.

---

## The eight objectives

| # | Objective | Where it lives | How to see it | State |
|---|---|---|---|---|
| 1 | Detect and prioritise material KPI movements | `whychain/detect/` (MSTL, robust z on the residual), `Materiality.is_material` in `whychain/contracts/models.py`, `_fold_the_graph` in `api/main.py` | Console **Open findings, worst first**, and section **01 The movement**. Materiality is a conjunction, statistical **and** rupee, and each contract declares its own thresholds. The queue ranks across every metric and region in rupees per day through each contract's `value_per_unit_inr`; consecutive flagged days are one finding, and a child metric moving in the same region and window as its parent is folded into the parent rather than queued again, so one event takes one row | Built |
| 2 | Reconcile data and business context across heterogeneous sources | `whychain/ingest/warehouse.py`, `contracts/*.yml` (`calculation.canonical_sql`, `lineage`, `freshness_sla`) | Console section **Where the data came from**: four sources, four cadences, per-source SLA verdict. Each KPI is read through its own contract, never through a shared frame | Built |
| 3 | Identify and rank explanatory drivers using appropriate methods | `whychain/decompose/` (price/volume/mix identity), `whychain/rank/` (two tracks), `whychain/verify/` (event-time isolation, DiD, placebo, exposure consistency) | Console section **Ranking, in two tracks**. Track A is exact and its rows may be stated; Track B is a standardised ridge and every row is labelled `CORRELATIONAL` and barred from becoming a cause | Built |
| 4 | Persona-specific narratives supported by traceable evidence | `whychain/personas/`, `whychain/narrate/` | Masthead **Reading as**: Analyst / CFO / Ops. Every figure in the narrative resolves on click to its query or document span | Built |
| 5 | Communicate uncertainty and abstain when evidence is insufficient | `whychain/confidence/score.py` (banding, abstention), `whychain/confidence/calibrate.py` (isotonic, held-out) | Select **South**, period 90 days: the engine reports UNKNOWN with what it ruled out and the next check. Measured: abstention precision **85.7%** | Built |
| 6 | Actions grounded in levers, constraints and decision rights | `whychain/actions/` | Console section **The decision**: driver → lever → action → expected impact → owner → confidence → monitoring. Every field derived; a cause with no lever returns `controllable: false` and a monitoring rule instead of an invented action | Built |
| 7 | Learns from analyst and business-user feedback | `whychain/feedback/`, `whychain/feedback/apply.py`, overlay composition in `whychain/contracts/registry.py` | Console section **Analyst review and corrections**. Corrections never edit a run and never move a computed value; they propose changes to business-owned inputs and need two independent submitters. A proposal on `materiality_threshold` can then be **applied by a named person and is consumed on the next run** — two analysts rejecting a ₹26,963/day movement takes West's flagged days from 23 to 16. The applied change is an audited overlay, not an edit to the contract, and the new floor is derived from the movements cited rather than typed. The other four targets have no consumer and refuse by name | Built, one of five targets consumable |
| 8 | Realistic security, cost, latency and scalability constraints | `whychain/telemetry/`, `AccessPolicy` in contracts, `whychain/personas/`, `bench/scale.py` | Console section **Run receipt** and the margin column: per-stage latency, model calls, tokens, rupee cost. p95 **0.18s** per diagnosis. `make scale` measures the other two: at 16x the fact rows a region read costs 36x, all of it the per-query `dedupe_order_id` window (the same aggregation without lineage transforms is flat at 1.8x), and under 16 concurrent readers nothing fails but throughput is flat at ~1.7 req/s because the work is single-process | Built; scalability now measured rather than argued |

---

## The ten minimum prototype expectations

| # | Expectation | Evidence | State |
|---|---|---|---|
| 1 | 3–5 connected KPIs across 2–3 sources, different grains or cadences | **5 KPIs per industry, across three industries.** Retail — `net_revenue` (day, INR), `orders` (day, count), `checkout_conversion` (**hour**, ratio), `aov` (day, INR), `on_time_delivery` (day, ratio). **4 sources**: `pos_txn` (6h SLA), `sessions`, `shipments`, `plan_ops` (72h), `voice_ops` (2h), plus the `ext_signals` external feed (36h). Revenue = orders × AOV; orders = sessions × conversion. `make status` prints the graph through the real loader. **Petroleum**: `net_realisation` (day, INR), `consignments` (day, count), `gantry_throughput` (**hour**, ratio), `avg_consignment_value` (day, INR), `supply_reliability` (day, ratio). **Power**: `dispatch_realisation`, `scheduled_blocks`, `dispatch_fulfilment` (**hour**, ratio), `avg_realised_tariff`, `grid_availability`. All three sit on the same source names with different semantics, so the reconciliation layer is exercised identically in each | Met |
| 2 | Lightweight KPI or semantic contract | `contracts/*.yml`: definition, canonical SQL with `dialect_targets`, grain, drivers with owner and controllable lever, materiality thresholds, freshness SLA per source, lineage, access policy. The registry rejects one-sided parent/child edges, cycles, unknown references, duplicate ids, and controllable levers with no owner | Met |
| 3 | At least two personas with different narratives or actions | **Three**: Analyst (everything, including rejected candidates and method), CFO (size, one decision, recoverable vs not), Ops (only levers they hold, plus what they cannot act on). A test asserts the underlying evidence is byte-identical across all three | Met |
| 4 | One multi-factor movement with known drivers | `demo-01-multi-factor`, West, 2026-08-13 to 16. Release regression + competitor price cut + weather, with a **planted decoy** that correlates perfectly and caused nothing | Met |
| 5 | One low-confidence scenario, clarification or abstention | `demo-02-low-confidence`: a nationwide shallow movement leaves difference-in-differences no control group. The engine returns UNKNOWN, names what it ruled out, and asks a clarifying question | Met |
| 6 | One sparse-history or newly launched KPI scenario | `demo-03-sparse-history`, and `datagen/catalog.py` launches one SKU late so its history is genuinely short. The verdict is `CANNOT_VERIFY`, which is deliberately distinct from `REJECTED` | Met |
| 7 | One role-based security or entitlement scenario | Rail control **Entitlement**. Set "South only" while viewing West: verified causes outside scope are removed **before** assembly, and the response says how many were withheld, what they were worth, and which role to escalate to. Row filter, column masks and a PII domain restriction are declared per contract | Met |
| 8 | Evidence of freshness, method, contribution, confidence, lineage | Every `Evidence` record carries provenance (query and row ids, or doc id and character span), a method and method class, and freshness where it applies. Unit/method agreement is enforced at construction, so a price/volume/mix bridge cannot report order counts | Met |
| 9 | Clear LLM vs non-LLM breakdown | Run receipt, per stage, by `MethodClass`: deterministic, statistical, causal, retrieval, LLM. The deterministic share of wall time is measured per run and printed; with no backend it is 100% and the receipt reports zero model calls rather than the count the design intends. A cache hit is counted apart from a call, so a warm run reports the calls it actually made | Met |
| 10 | Runtime telemetry: latency, model calls, tokens, cost | Run receipt and margin column. Rupee cost is arithmetic over declared per-1k rates in `whychain/telemetry/`, not an estimate | Met |

---

## Native / configured / custom-built / externally integrated

The brief asks teams to distinguish these. This build is deliberately
platform-neutral, so most of it is custom.

| Capability | Classification | Note |
|---|---|---|
| Warehouse and SQL execution | **Native** (DuckDB) | Embedded, no server. The same canonical SQL declares `dialect_targets: [duckdb, databricks, snowflake]` |
| Seasonal decomposition (MSTL), isotonic regression, ridge | **Native** (statsmodels, scikit-learn) | Standard implementations, used as intended |
| Retrieval | **Configured** (TF-IDF + SVD, `whychain/corroborate/`) | Behind an `Embedder` protocol. Swapping in a hosted embedder means implementing one interface |
| KPI semantic contracts and the governance layer | **Custom-built** | `contracts/` and `whychain/contracts/` |
| Detection, bridge, causal verification, ranking, confidence, actions, signal gap, feedback | **Custom-built** | The engine |
| Narrative generation | **Externally integrated** (open-weight model over a protocol) | No vendor SDK: `whychain/llm/` defines a three-method `ChatModel` protocol, and `test_llm_backend.py` asserts no vendor package is pinned. Default is Mistral 7B Instruct on Ollama, inference inside the boundary; `OpenAICompatibleModel` reaches Groq, Together, OpenRouter, vLLM or Gemini's compatibility endpoint on four environment variables. Constrained by JSON schema, gated by a deterministic validator, and optional: with no backend the deterministic writer runs and the receipt says so |
| External risk feed | **Externally integrated** (schema), **generated** (data) | `ext_signals` carries the IMD/Open-Meteo schema; every row says `source: generated`. No document claims a live feed |
| Console | **Custom-built** | No framework, no build step |

---

## What the numbers say

160 labelled cases with planted causes, planted decoys, planted noise and
planted unanswerable cases (`make bench`).

| | |
|---|---|
| **Top-1 among movements worth explaining** | **78.6%** (55 of 70) |
| Top-1 over the whole population | 38.9% |
| True cause verified at all | 48.6% |
| **False alarms on noise-only cases** | **0.0%** |
| Planted correlation traps rejected | 87.5% |
| **Cases needing an abstention that got one** | **88.2%** (2 missed of 17) |
| Abstentions that were right | 85.7% |
| Expected calibration error | 0.069 raw, **0.042 calibrated** on held out |
| Latency p50 / p95 | 0.080s / 0.178s |

The first two rows belong together. The engine explains movements that clear
both materiality tests and declines the rest, so top-1 across the whole
population is bounded by how many movements are worth explaining at all rather
than by how often the engine is wrong when it speaks. Lowering a threshold to
raise the headline is T-14 in `BUGS.md`.

## What is not built

Stated here so no row above has to be read carefully.

- **The corroboration extractor is rule-based**, so a keyless run makes zero
  model calls rather than the two the design intends. The receipt reports what
  happened.
- **`ext_signals` is generated.** The schema is the one a cached IMD or
  Open-Meteo snapshot drops into unchanged.
- **Contract-to-warehouse compilation is roadmap.** `dialect_targets` is
  declared; the Databricks and Snowflake renderings are hand-written examples,
  not generated.
- **Four of the five feedback targets still need a human.** `materiality_threshold`
  is applied by a named person and consumed on the next run; `candidate_ranking`,
  `candidate_source`, `driver_mapping` and `retrieval_filter` have no consumer in
  the engine and are refused by name rather than queued. Nothing here retrains
  anything, and the word "learning loop" is still not used.
- **Two scaling limits are now measured, and neither is fixed.** `make scale`
  found them: a region read costs 36x at 16x the fact rows, entirely because
  `dedupe_order_id` is a per-query window no predicate can be pushed below — the
  fix is to materialise the deduped source at ingest, and it is not done. And
  the engine serves about 1.7 diagnoses per second however many readers arrive,
  because it is one process with one warehouse connection; multiple workers and
  an externalised cache are the route out, and are not built. Nothing has been
  run against a warehouse that does not fit on one machine.
