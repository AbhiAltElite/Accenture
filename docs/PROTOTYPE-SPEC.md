# WhyChain — Prototype Design Specification

An engine that takes a moved business metric and returns two things: a **verified cause with every claim bound to its source**, and a **detection gap** — what signal was missing, which process should have consumed it, who owns it.

---

## 0. The architectural spine

Three decisions that everything else follows from. Get these right and the rest is mechanical.

**1. Every computed fact becomes an `Evidence` record.** Not a number in a variable — a typed, addressable object with its method, its provenance, its freshness and its links to other evidence. The evidence set is the engine's entire output. The narrative is a *view* over it.

**2. The narrative layer may only reference evidence IDs, and a validator enforces it.** The LLM receives an evidence table and returns sentences tagged with the IDs they rest on. Any sentence that fails to bind, or that contains a number not present in its cited evidence, is rejected before a human sees it.

**3. Each stage is a pure function over a `RunContext`.** `stage(ctx) -> list[Evidence]`, with the context carrying config, contracts and accumulated evidence. Telemetry, latency, the trace, replay and the LLM-vs-non-LLM split all fall out of this for free rather than being instrumented in afterwards.

```
RunContext
├── run_id, kpi_id, window, requester (role, entitlements)
├── contracts: dict[kpi_id, KPIContract]
├── evidence: EvidenceStore          # append-only, DAG
├── trace: list[StageTrace]          # latency, method_class, tokens, cost
└── budget: TokenBudget
```

---

## 1. Data model

### Sources — deliberately incompatible

| id | contents | grain | cadence | notes |
|---|---|---|---|---|
| `pos_txn` | order lines: SKU, price, discount, qty, city, channel, device | order-line | hourly | duplicate order ids, timezone drift |
| `plan_ops` | marketing spend, planned stock, competitor price index | weekly × region × category | T+2 | nulls, late arrival, ₹ vs ₹-lakh unit mix |
| `voice_ops` | support tickets, rep notes, release/deploy log | event, unstructured | near-real-time | free text, inconsistent tagging |
| `ext_signals` | weather by city (real, Open-Meteo ERA5); festival/holiday calendar | daily × city | T+1 | genuine coverage gaps |

`ext_signals` is a **feed**, not a peer source — it is consulted, never joined into the primary fact grain.

### KPI graph — connected by identity, so movement cascades exactly

```
Net Revenue  =  Orders × AOV
     Orders  =  Sessions × Checkout Conversion
        AOV  =  f(unit price, mix)
On-Time Delivery %  →  Return Rate  →  Net Revenue
```

Five KPIs. Conversion is hourly and digital-only — a different grain *and* cadence from its own parent, which is what forces the reconciliation layer to be real.

### Reconciliation layer

- **Grain harmoniser** — order-line → daily → weekly, with declared aggregation rules per measure (sum, weighted mean, ratio-of-sums)
- **Calendar mapper** — Gregorian ↔ fiscal ↔ festival calendar
- **Unit normaliser** — currency scale, UoM
- **Freshness scorecard** — per source: `as_of`, lag, SLA met. Emits an `Evidence(kind=freshness)` on every run, which the confidence model consumes and the narrative must mention when breached

---

## 2. KPI contract

Executable, not documentation. One file drives the SQL, the access filter, the alert threshold and the action owner.

```yaml
kpi_id: net_revenue
version: 3
owner_role: finance_director
definition: "Gross merchandise value net of returns and discounts, excluding tax"
calculation:
  canonical_sql: |
    SELECT date_trunc('day', order_ts) AS d, region, channel,
           SUM(qty * unit_price - discount) AS value
    FROM pos_txn WHERE status NOT IN ('cancelled') GROUP BY 1,2,3
  dialect_targets: [duckdb, databricks, snowflake]
grain: {time: day, dims: [region, channel, category, device]}
calendar: fiscal_in
parents: []
children: [orders, aov]
dimensions: [region, channel, category, device, sku]

drivers:
  - id: unit_price
    source: pos_txn
    controllable_lever: pricing
    owner_role: category_manager
    elasticity_prior: -1.4
  - id: marketing_spend
    source: plan_ops
    controllable_lever: media_budget
    owner_role: marketing_lead
  - id: stock_position
    source: plan_ops
    controllable_lever: replenishment
    owner_role: supply_planner
  - id: competitor_price_index
    source: plan_ops
    controllable_lever: null          # not controllable — informs, never actioned
    owner_role: null
  - id: severe_weather
    source: ext_signals
    controllable_lever: null
    owner_role: null

materiality:
  statistical: {min_abs_robust_z: 3.0}
  business:    {min_abs_delta_inr: 500000}   # both must hold

freshness_sla: {pos_txn: 6h, plan_ops: 72h, voice_ops: 2h, ext_signals: 36h}

access_policy:
  row_filter: "region IN :entitled_regions"
  column_masks: [unit_margin, customer_email]
  domain_restriction: [pii]                   # never enters an LLM prompt

signals_consumed:                             # DERIVED at registration — never hand-written
  derived_from: docs/sop/sop_demand_planning_v2.pdf
  extracted:
    - {signal: historical_sales,   span: [1204, 1263]}
    - {signal: inventory_position, span: [1290, 1341]}
    - {signal: capacity_metrics,   span: [1402, 1455]}
  extracted_at: 2026-08-20T10:14:00Z
  coverage: complete                          # complete | partial | unknown
lineage: {upstream: [pos_txn.orders, pos_txn.order_items], transforms: [dedupe_order_id, tz_normalise]}
```

**`signals_consumed` is derived, never typed.** At contract registration a model reads the SOP once, offline, and stores extracted signals plus character spans. Three sourcing tiers, strongest first: a **published third-party S&OP process description** (the industry-standard cycle documents itself as consuming historical sales, inventory, capacity and financial inputs — and conspicuously *no external risk signal*); an SOP written by someone blind to the planted scenarios; your own only as a last resort.

---

## 3. The Evidence object

The core abstraction. Everything the engine knows is one of these.

```python
@dataclass(frozen=True)
class Evidence:
    id: str                     # "ev_007"
    kind: Kind                  # anomaly | decomposition | contribution | association
                                # | causal_test | corroboration | external_event
                                # | signal_gap | freshness | precedent | counterfactual
    claim: str                  # templated factual sentence, machine-generated
    value: float | dict
    unit: str                   # "INR" | "pct" | "count" | "hours"
    method: str                 # "mstl_robust_z" | "pvm_bridge" | "did" | "ridge" | ...
    method_class: MethodClass   # DETERMINISTIC | STATISTICAL | CAUSAL | RETRIEVAL | LLM
    confidence: float | None
    ci: tuple[float, float] | None
    provenance: Provenance
    freshness: Freshness
    supports:    list[str]      # evidence ids this rests on  → the DAG
    contradicts: list[str]      # populated by the contradiction detector
    run_id: str

@dataclass(frozen=True)
class Provenance:
    source_id: str
    query: str | None           # the EXACT SQL executed
    row_ids: list[str] | None
    row_count: int | None
    doc_id: str | None
    span: tuple[int, int] | None   # character range in the source document
    quote: str | None
```

**The click-through is `render(evidence.provenance)`.** Nothing more. The UI feature that carries the whole trust story is a consequence of the data model, not a feature built on top of it.

---

## 4. Pipeline

`method_class` is recorded per stage, which produces the LLM-vs-non-LLM breakdown automatically.

| # | Stage | Method | Emits | Class |
|---|---|---|---|---|
| 0 | Reconcile | grain harmonise, calendar map, unit normalise, freshness score | `freshness` | DET |
| 1 | Detect | MSTL decomposition → robust z (median/MAD) on residual; festivals as exogenous regressor | `anomaly` | STAT |
| 2 | Prioritise | materiality = stat significance × ₹ impact × persistence × breadth across KPI graph × recurrence | ranking | DET |
| 3 | Contextualise | contract, lineage, known releases/promos, open incidents | context | DET |
| 4 | Decompose | **price/volume/mix bridge** (exact, additive) + dimensional contribution | `decomposition`, `contribution` | DET |
| 5 | Rank — **two tracks** | **A (exact):** stage-4 output already ranks internal structural drivers as an identity summing to the total. **B (correlational, labelled):** ridge/lasso over standardised external+ops drivers with lag alignment; coefficients read directly | `association` | DET / STAT |
| 6 | **Verify** | event-time isolation → DiD vs unaffected comparison group → placebo test. Only survivors become claims | `causal_test` | CAUSAL |
| 7 | Corroborate | pgvector retrieval over tickets/notes/release logs windowed to the anomaly; structured extraction returning spans | `corroboration` | **LLM (call 1)** |
| 8 | External check | consulted only if internal inconclusive; tests public availability, lead time, spatial specificity | `external_event` | DET |
| 9 | Confidence | scoring + isotonic calibration + contradiction detection | scores | STAT |
| 10 | **Signal gap** | `signals_available ∖ signals_consumed`, foreseeability-gated; recurrence from case history; owner from contract | `signal_gap` | DET |
| 11 | Action assembly | driver → lever → action → **expected impact from stage 4 + elasticity** → owner → confidence → **monitoring plan from stage 10** | actions | DET |
| 12 | Narrate | one constrained call per persona-set, over the evidence table | narrative JSON | **LLM (call 2)** |
| 13 | Validate | binding check, numeral check, entity check | accept/reject | DET |

**Exactly two model invocations per diagnosis.** SOP parsing happens once at contract registration, offline — so Answer 2's expensive work is amortised across every future diagnosis of that KPI rather than charged per run.

### Stage 4 — the exact bridge

```
Δrevenue = Δprice_effect + Δvolume_effect + Δmix_effect      (identity, sums exactly)

price_effect  = Σ_sku  (p1 - p0) · q0
volume_effect = Σ_sku  (q1 - q0) · p0
mix_effect    = Σ_sku  (p1 - p0) · (q1 - q0)
```
Then dimensional contribution: each slice's signed share of the total movement, ranked. Because it is arithmetic, you can state that contributions sum to 100% — a model-based attribution cannot promise that.

### Stage 6 — verification, and what makes it non-circular

```
event_time_isolation:  effect starts strictly after t_event, not before
difference_in_diff:    (affected_post − affected_pre) − (control_post − control_pre)
placebo:               same test on a period where the cause was absent → must find nothing
```
A candidate becomes a **claim** only if all three pass. Failures are retained and surfaced — "tested and rejected" is a displayed result, not a discarded one.

**Negative controls.** The case generator plants events that correlate perfectly with the drop but caused none of it (a promotion launched the same day as a checkout regression). A correlation-ranking approach picks the trap; verification must reject it. This is the standard negative-control device from observational causal inference — Lipsitch, Tchetgen Tchetgen & Cohen, *Epidemiology* (2010) — and that literature lists DiD among the recognised negative-control methods, so the pairing is textbook. Rejection rate is a reported metric.

### Stage 9 — confidence and abstention

```
raw = w1·coverage            # share of the movement explained by surviving claims
    + w2·causal_strength     # DiD effect size / CI width
    + w3·corroboration       # independent internal documents supporting it
    + w4·freshness_ok
    − w5·contradiction_penalty

p = isotonic_calibrate(raw)   # fitted on held-out planted cases
```

**Abstain if any holds:**
- `p < τ_abstain`
- an unresolved contradiction exists (two claims of opposite sign on the same slice)
- `coverage < 0.5` — most of the movement is unexplained
- a required source is stale beyond SLA

**Abstention output is structured, never a shrug:**
```json
{"verdict":"UNKNOWN","coverage":0.31,
 "ruled_out":[{"hypothesis":"pricing","method":"did","reason":"no effect in comparison group"}],
 "next_check":"pull store-level footfall for West, 12–19 Aug",
 "blocking_data":["plan_ops stale by 96h (SLA 72h)"],
 "clarifying_question":"Was the Nagpur DC outage on 14 Aug in scope for this region?"}
```
The clarifying question is a live input — answering it re-runs the diagnosis with the extra fact injected as evidence.

### Stage 10 — signal gap (the monitoring-plan generator)

```
signals_available: [{signal_id, publisher, public: bool, lead_time_h, spatial_specificity}]
gap = available ∖ contract.signals_consumed.extracted

foreseeable(s) ⇔ s.public
              ∧ s.lead_time_h ≥ actionable_threshold(kpi)
              ∧ s.spatial_specificity covers affected_slice
```
All three must hold, or the engine returns **`not_foreseeable`** rather than manufacturing a gap — hindsight bias is a known failure mode and is guarded explicitly. If `signals_consumed.coverage == unknown` (no SOP available) it returns **`coverage_unknown`**, never an asserted gap.

Output is the `monitoring_plan` that stage 11 requires:
```json
{"watch":"IMD severe weather alert, Maharashtra",
 "threshold":"amber or above, ≥48h lead",
 "window":"rolling 7d","route_to":"supply_planner",
 "recurrence":"3rd occurrence in 18 months","currently_owned_by":null}
```

Three outcomes must all be demonstrable: a **gap found**, a **refusal** (no public warning existed), and a **no-gap** (the SOP already consumes the signal). A system that always finds a gap has found nothing.

---

## 5. Narrative + validator

The model receives the evidence table and the persona spec, and returns:

```json
{"persona":"cfo",
 "sentences":[
   {"text":"Net revenue fell ₹18.4 lakh in the West region, 68% of it concentrated in mobile checkout.",
    "evidence_ids":["ev_001","ev_014"]},
   {"text":"The drop begins the day after release 4.05 and is absent in the East.",
    "evidence_ids":["ev_022","ev_027"]}],
 "caveats":["plan_ops stale by 96h"]}
```

**Validator (deterministic, post-LLM):**
1. every sentence carries ≥1 `evidence_id`, all resolvable in the store
2. every numeral in `text` (₹, %, ×, counts) matches a value in its cited evidence within tolerance
3. every named entity (region, SKU, channel) appears in the cited evidence
4. on failure → one retry with the specific error → else deterministic template fallback

Rejections are counted and surfaced in the UI. That counter is the anti-hallucination claim made observable.

### Personas — structurally different, not tonally

| Persona | Fields rendered | Withheld |
|---|---|---|
| CFO | ₹ impact, recovery outlook, one decision, confidence band. 5 sentences | methods, CIs, rejected candidates |
| Category / Ops manager (regional) | levers they control, action + owner + monitoring plan, scoped to entitled rows | cross-region comparison, masked columns |
| Analyst (the console) | full evidence DAG, method per claim, CIs, rejected candidates, telemetry | — |

**Entitlement is enforced at projection, not in the prompt.** When the dominant driver lies outside the requester's scope, the narrative says so explicitly — *"the largest contributor is outside your entitlement scope; escalated to finance_director"* — rather than silently omitting it. An audit record logs exactly which rows and columns entered each prompt.

---

## 6. Benchmark

The case generator writes ground truth to a directory the engine has no code path to read, enforced by test.

| Metric | What it answers |
|---|---|
| top-1 / top-3 root-cause accuracy | does it find the right cause |
| false-alarm rate on seasonal decoys | does it stay quiet on festivals |
| **negative-control rejection rate** | **does it refuse correlation traps** — the anti-circularity number |
| abstention precision / recall | does it say UNKNOWN exactly when it should |
| ECE + reliability diagram | does "80% confident" mean 80% |
| signal-gap detection rate | Answer 2 accuracy |
| p50/p95 latency, ₹ per insight | operating cost |

Case mix: single internal cause · external shock · **two interacting causes** · seasonal decoy · **negative control** · pure noise · sparse history · stale-source. Generate 150+ labelled cases, not just the demo scenarios — calibration needs a population to fit against.

---

## 7. Interfaces

```
POST /diagnose      {kpi_id, window, persona, role}  → diagnosis + evidence + trace
GET  /evidence/{id}                                   → provenance, rows, document span
POST /clarify       {run_id, answer}                  → re-run with injected evidence
POST /feedback      {claim_id, verdict, reason_code}  → Beta-Binomial prior update
GET  /telemetry/{run_id}                              → latency, calls, tokens, cost
POST /contracts/register {kpi_id, sop_path}           → offline SOP parse → signals_consumed
```

**UI — one page, four panels:** metric with anomaly band · narrative where every sentence is clickable to its evidence · Answer 2 with the monitoring plan · telemetry receipt. Persona switcher in the header. Not Streamlit — the click-to-evidence interaction is the product and should not look like a stock expander widget.

**Feedback loop:** verdict per claim → Beta-Binomial priors per `(kpi, hypothesis_class)` reweight future ranking. Measurable: run the benchmark, inject verdicts, re-run, report the change in mean rank of the true cause.

---

## 8. Stack

DuckDB (analytics) · Postgres + pgvector (documents, feedback, case history) · FastAPI with Pydantic evidence types end to end · hand-rolled single-page front end · a small model for extraction and a frontier model for narration. Runs from a clone with one command, no cloud account in the path.

**Framing note:** this is an orchestrated agentic pipeline — tool use, retrieval, multi-step reasoning — with *deterministic control flow* rather than LLM-decided routing, chosen for auditability and replayability. The orchestration is agentic; the arithmetic is not.
