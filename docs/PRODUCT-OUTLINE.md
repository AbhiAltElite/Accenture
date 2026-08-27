# WhyChain — Product Outline

## What we are building

An engine that takes a business metric that moved and returns two answers:

1. **What caused it** — a ranked, causally tested explanation where every sentence resolves on click to the exact query, rows and source document behind it.
2. **Why it went unanticipated** — which warning signal existed, which process failed to consume it, how often this has recurred, and who owns it.

It sits on top of existing BI rather than replacing it. The quantitative layer is deterministic; the language model reads, ranks and writes but never calculates.

---

# 1. Feature list — what / where / why

## Phase A — Detect

| Feature | What it does | Where it sits | Why it exists |
|---|---|---|---|
| **Multi-source reconciliation** | Harmonises grains (order-line → daily → weekly), maps calendars (Gregorian / fiscal / festival), normalises units and currency scale | Ingest, before anything | Three sources with different grains and refresh cadences can't be compared until they're on the same footing |
| **Freshness gate** | Per-source `as_of`, lag, SLA met/breached. Emits evidence on every run | Ingest | When a source is stale, confidence drops and the narrative *says so* rather than failing silently |
| **Seasonality-aware anomaly detection** | Decomposes the series into trend + seasonal patterns + residual; detects only on the residual | Stage 1 | A festival week is a huge movement that means nothing. Detecting on raw values is why people stop trusting alerts |
| **Materiality prioritisation** | Ranks by statistical significance **and** ₹ impact **and** persistence **and** breadth across the KPI graph | Stage 2 | A statistically clean 0.2% move isn't worth an analyst's morning. Both tests must pass |

## Phase B — Explain

| Feature | What it does | Where it sits | Why it exists |
|---|---|---|---|
| **Price/volume/mix bridge** | Splits the movement into price effect, volume effect, mix effect — an identity that sums exactly | Stage 4 | Lets us say contributions total 100%. A model-based attribution can't promise that |
| **Dimensional contribution** | Each slice's signed share of the movement, ranked | Stage 4 | Locates the problem: West / mobile / Product X |
| **Two-track hypothesis ranking** | Track A: internal structural drivers, already ranked by the exact bridge. Track B: external and ops drivers via regularised regression with lag alignment, coefficients read directly | Stage 5 | Two kinds of driver need two methods. Track B output is labelled *hypothesis*, never *cause* |
| **Causal verification** | Event-time isolation → difference-in-differences vs an unaffected group → placebo test. All three must pass | Stage 6 | This is the stage every competing tool skips. Candidates that fail never become claims |
| **Rejected-candidate display** | Failed hypotheses are retained and shown with the test that killed them | Stage 6 output | "Tested and rejected" is a result, not a discard. It's also the most convincing thing on screen |

## Phase C — Prove

| Feature | What it does | Where it sits | Why it exists |
|---|---|---|---|
| **Internal text corroboration** | Semantic search over support tickets, rep notes, deployment logs, windowed to the anomaly; extractions carry exact character spans | Stage 7 | Independent evidence in the company's own words. Also satisfies the structured-plus-unstructured requirement |
| **External signal check** | Weather, holidays, public events — consulted *only* when internal evidence is inconclusive | Stage 8 | Order matters. Jumping to external news when the cause is internal is the failure mode we're fixing |
| **Claim-level evidence chain** | Every computed fact is a typed Evidence record carrying method, provenance, freshness and links to supporting evidence | Data model, everywhere | The click-through is a consequence of this, not a feature bolted on top |
| **Narrative validator** | Rejects any sentence without resolvable evidence IDs; checks every numeral in the text against its cited evidence; retries once, then falls back to template | Stage 13 | Makes hallucinated numbers structurally impossible rather than unlikely |

## Phase D — Communicate

| Feature | What it does | Where it sits | Why it exists |
|---|---|---|---|
| **Calibrated confidence** | Score from coverage, causal strength, corroboration, freshness, minus contradiction penalty — then calibrated on held-out cases | Stage 9 | So that "80% confident" means right 80% of the time. A model-written percentage can't be calibrated |
| **Structured abstention** | Returns UNKNOWN with ruled-out hypotheses and the method that killed each, the named next check, and what data was blocking | Stage 9 | Saying "I don't know" usefully is a feature. Saying it vaguely is a failure |
| **Interactive clarification** | Engine asks a specific question; the user answers in-line; the diagnosis re-runs with that fact injected as evidence | Stage 9 → re-run | The brief asks for "requests clarification **or** abstains". We do both |
| **Sparse-history handling** | Bayesian shrinkage toward the category prior for new SKUs/markets; wide intervals; refuses causal verification and states the refusal | Stage 6 + 9 | A three-week-old product has no comparison group. Pretending otherwise is worse than admitting it |
| **Persona narratives** | Structurally different outputs — different fields present, not different tone | Stage 12 | A CFO and a regional manager need different things. Same paragraph reworded fools nobody |
| **Role-based entitlement** | Row filters, column masks, PII excluded at the projection layer (never via prompt instruction); audit log of what entered each prompt | Projection, before the LLM | Enterprise requirement — and the honest-redaction message is unforgeable by a prompt template |

## Phase E — Act & Learn

| Feature | What it does | Where it sits | Why it exists |
|---|---|---|---|
| **Signal-gap analysis (Answer 2)** | `signals_available ∖ signals_consumed`, foreseeability-gated on public + lead time + specificity; recurrence count; owner from contract | Stage 10 | The differentiator. No BI product ships this |
| **Monitoring-plan generation** | The gap becomes: watch this signal, at this threshold, on this window, routed to this role | Stage 10 → 11 | This is the last link of the brief's own action chain, derived from a measurement instead of written by a model |
| **Action assembly** | driver → lever → action → **expected impact computed from the bridge and elasticity** → owner → confidence → monitoring plan | Stage 11 | Every field is derived. The model only phrases it |
| **Feedback loop** | Per-claim verdict with reason code → Beta-Binomial priors reweight future ranking | Stage 14 | Measurable: run benchmark, inject verdicts, re-run, report the change in rank of the true cause |

## Phase F — Operate

| Feature | What it does | Where it sits | Why it exists |
|---|---|---|---|
| **KPI semantic contract** | One versioned file drives the SQL, the access filter, the alert threshold and the action owner | Governance layer | Executable governance, not documentation. Change the file, four things change |
| **Derived signal coverage** | `signals_consumed` extracted from a real SOP document at registration, stored with character spans | Contract registration (offline) | Kills "you declared your own finding". Also keeps per-diagnosis model calls at two |
| **Telemetry receipt** | Per-run stage latency, model calls, tokens, cache hits, cost per insight, LLM vs non-LLM split | Cross-cutting | The brief asks for it explicitly. Also backs the two-calls claim, which invites checking |
| **Benchmark harness** | Top-1/top-3 accuracy, false-alarm rate, **negative-control rejection rate**, abstention precision/recall, ECE, signal-gap rate | Offline | For a product about evidence, measuring itself is the thesis |

---

# 2. How it should function

## Entry
The user does not start at a dashboard. They open **one diagnosis** — either from an alert, or by selecting a KPI and window.

## The main view — four regions

**1. The metric**
Actual vs expected band, the anomaly window marked. Shows the movement is real and where it starts. Small, not the centrepiece.

**2. The narrative** *(the primary surface)*
Persona-specific text. **Every sentence is a click target.** Clicking opens the evidence for that sentence — the exact SQL, the rows returned, or the source document with the cited span highlighted. Closing returns you in place; the reading position is never lost.

Sentences are visually differentiated by evidence state:
- **verified claim** — passed causal testing
- **hypothesis** — correlational, explicitly marked as untested
- **contextual** — descriptive, no causal assertion

**3. What was ruled out**
Rejected candidates with the test each failed. Collapsed by default, one click to expand. This section is more persuasive than the main narrative and should not be buried.

**4. Answer 2**
Separate panel, visually distinct from the diagnosis — it answers a different question. Contains: warning lead time, the missing signal, the SOP excerpt showing what the process does consume, recurrence count, current owner (or "unowned"), and the generated monitoring plan.

Three possible states, all of which must be reachable in the demo:
- **gap found**
- **not foreseeable** — no public signal existed; the engine declines
- **no gap** — the process already consumes the signal

## Secondary surfaces

**Persona switcher** — top-level control. Switching re-renders the narrative from the same evidence set. The evidence does not change; the projection does. When the requester's entitlement excludes the dominant driver, the narrative states that explicitly and names the escalation role.

**Telemetry receipt** — collapsible. Stage timings, model calls, tokens, cost. Should read like a receipt, not a chart.

**Feedback control** — per claim: accept / reject / correct, with a reason code. Lightweight, inline, not a modal.

**Clarification prompt** — when the engine abstains and has a specific question, it appears as an answerable input, not a static sentence. Answering re-runs the diagnosis.

## States that must be designed, not afterthoughts
- **UNKNOWN** — this is a first-class output, not an error state. It needs the same visual weight as a confident answer, showing ruled-out list, next check, and blocking data.
- **Stale source** — freshness breach visible in the narrative and on the affected evidence.
- **Sparse history** — wide intervals, explicit "insufficient history" labelling, causal verification marked unavailable.
- **Entitlement-limited** — content withheld is *announced*, never silently absent.
- **Validator rejection** — the count is surfaced; the mechanism should be visible, not hidden plumbing.

---

# 3. How it should look — structural requirements

*(Visual style is yours; these are the behavioural and information-design constraints the product imposes.)*

**It is a document, not a dashboard.** The primary surface is text you read, with data supporting it. Do not centre the design on charts — every competitor's demo is a chart grid, and the narrative-with-proof is the differentiator.

**Evidence state must be legible at a glance.** Verified / hypothesis / rejected / unknown need distinct treatment. This is the core information-design problem — a reader must never mistake a correlational hypothesis for a tested cause.

**The click must feel instant and lightweight.** Evidence opens in place — a drawer or inline expansion, not a page navigation or a modal that loses context. This interaction is the product; everything else supports it.

**Answer 2 must read as a different kind of thing.** It's a process finding, not a data explanation. Structurally separate, differently framed, clearly not part of the same panel.

**Density over whitespace.** The analyst persona wants information; this is a working tool, not a marketing page. Numbers in columns should align.

**One page, no navigation.** Everything reachable without leaving the diagnosis.

**Not Streamlit.** Most competing submissions will be Streamlit apps and will look like each other. The click-to-evidence interaction is the thing judges remember — it should not look like a stock expander widget.
