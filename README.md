# WhyChain

An evidence-backed diagnosis engine for business metric movements.

When a KPI moves materially, WhyChain answers two questions. **What caused it**,
with every sentence resolving on click to the query, the rows, or the character
span in the document behind it. And **why it was not anticipated**: which
warning signal existed, which process had no step that consumes it, how often
this has recurred, and who owns the gap.

It sits on top of existing BI rather than replacing it.

**The rule the whole design serves:** the quantitative layer is deterministic.
The language model reads unstructured text, ranks competing hypotheses and
writes the narrative. It never calculates, and it never decides what is true. A
polished false diagnosis is worse than an explicit UNKNOWN.

---

## Table of contents

- [The problem](#the-problem)
- [Approach](#approach)
- [Architecture](#architecture)
- [Key features](#key-features)
- [Where AI is used, and where it is not](#where-ai-is-used-and-where-it-is-not)
- [Measured results](#measured-results)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Execution](#execution)
- [What to look at first](#what-to-look-at-first)
- [Troubleshooting and FAQ](#troubleshooting-and-faq)
- [Limitations](#limitations)
- [Repository map](#repository-map)
- [Maintainers](#maintainers)

---

## The problem

A number moves. An analyst spends two days assembling an explanation. A
paragraph goes into the board pack. Nobody checks the paragraph, because
checking it would mean redoing the two days.

Adding a language model to that process makes the paragraph faster and no more
checkable. That is the reason AI diagnosis stalls at the pilot: a finance
director will not put their name to a conclusion they cannot verify, and a
conclusion that cannot be verified cannot be signed off, however good it looks.

The gap is not explanation. It is **signable** explanation.

## Approach

Five commitments, each of which costs something.

**Separate ranking from verification.** Contribution analysis presented as root
cause is the market norm and it is a category error: a slice that moved is not a
slice that caused. WhyChain computes two rankings and refuses to merge them.
Track A is an exact identity that reconciles to the movement with no residual.
Track B is a standardised ridge fit whose every row is marked `CORRELATIONAL`
and is barred from becoming a stated cause until a causal test promotes it.

**Test causality rather than screen for plausibility.** Every candidate faces
event-time isolation, difference-in-differences against unexposed regions,
exposure consistency across affected slices, and a placebo run over six quiet
windows. A failed placebo is fatal regardless of what else passed. The cost is
coverage: causes that hit every region at once have no control group and are
returned as untestable rather than as answers.

**Make refusal a first-class output.** `UNKNOWN`, `CANNOT_VERIFY`,
`not_foreseeable` and `coverage_unknown` are designed states with their own
rendering, not error paths. The engine abstains on 94.1% of the cases whose
correct answer is an abstention.

**Keep the human in the lead, structurally rather than as a slogan.** Nothing
in this engine executes. A decision card is a draft addressed to a named role
and marked `awaiting_approval`; an agent that rolls back production because a
statistic moved is not deployable, and one that investigates and drafts is. When
the evidence is insufficient the engine abstains and hands the question back
with what it ruled out and the next thing worth checking. When a cause lies
outside the reader's entitlement it says so and names the role to escalate to.
When an analyst disagrees, the correction needs a second independent submitter
before it becomes a proposal, and a human applies it. The model reads and
writes; the arithmetic is deterministic; the decision is a person's.

**Bind every sentence to evidence, and check the binding in code.** The model
writes sentences carrying evidence ids. A deterministic validator then rejects
any sentence that cites nothing, prints a figure absent from a fact it cites,
names an entity the evidence does not contain, or states a rejected candidate as
a cause. Rejected sentences are dropped and counted on the receipt.

## Architecture

```
sources (3 grains + 1 external feed)
   ↓ reconcile · freshness gate
detect (MSTL → robust z on the residual, per the contract's grain)
   ↓ materiality (statistical AND ₹)
decompose (price/volume/mix bridge — exact identity)
   ↓
rank  ├─ track A: exact, from the bridge
      └─ track B: ridge, labelled CORRELATIONAL — never merged with A
   ↓
verify (event-time isolation ∧ DiD ∧ exposure consistency ∧ placebo)
   ↓                                    ← only survivors become claims
corroborate (retrieval + span-cited extraction)     ← model call 1 of 2
   ↓
confidence (deterministic score → isotonic calibration) → abstain if weak
   ↓
actions (driver → lever → action → impact → owner → confidence → monitoring)
   ↓
signal gap (Answer 2) → monitoring plan
   ↓
narrate (constrained to the evidence table)         ← model call 2 of 2
   ↓
validate (binding + numeral + entity + rejected-cause checks)
   ↓
project (persona + entitlement, applied before assembly)
   ↓
feedback (bounded: business inputs only, never a computed value)
```

## Three industries, one engine

The console opens on an industry switcher. The same engine answers the same
eight questions about three businesses whose metrics move for entirely different
reasons, and that contrast is the point of having more than one.

| Industry | What moves it | Headline metric |
|---|---|---|
| **Retail CPG** | Mostly internal: releases, pricing, stock, marketing, with weather and competitors at the edges | `net_revenue` |
| **Petroleum marketing** | Almost entirely external: crude benchmarks, excise notifications, refinery turnarounds, pipeline integrity, port closures | `net_realisation` |
| **Power generation** | Set from outside: regulatory tariff orders, fuel supply, grid constraints, merit order, weather-driven load | `dispatch_realisation` |

Switching industry changes the contracts, the warehouse, the labels and the
dimension names together. It changes no calculation: detection, the price/volume/
mix bridge, both ranking tracks, the causal tests, confidence and every threshold
are the contract's job in all three. What each industry supplies is its own
vocabulary — which words in an operational note name which driver, which
complaint codes corroborate which cause, what its planning extract calls a
planned intervention.

**The externally-driven verticals make a refusal demonstrable that retail
cannot.** A national excise revision or a regulatory tariff order lands on every
region on the same morning. There is no unexposed region, difference-in-
differences has nothing to compare against, and the correct answer is
`cannot_verify` rather than a cause. Both verticals plant one deliberately
alongside regional events that must verify, because a vertical made only of
national policy events would abstain on everything and demonstrate half the
engine.

Build them with `make gen-all`. Retail alone is `make gen`.

**Five connected KPIs across four sources at three grains and four refresh
cadences.** Revenue is orders times average order value; orders come from
sessions times conversion. A break in one shows up in the others, which is why
they are read together.

| KPI | Unit | Grain | Owner | Source |
|---|---|---|---|---|
| `net_revenue` | INR | day | finance director | `pos_txn` (6h SLA) |
| `orders` | count | day | commercial director | `pos_txn` |
| `checkout_conversion` | ratio | **hour** | ecommerce lead | `sessions` + `pos_txn` |
| `aov` | INR | day | category manager | `pos_txn` |
| `on_time_delivery` | ratio | day | supply planner | `shipments` |

Plus `plan_ops` (72h SLA), `voice_ops` (2h) and the `ext_signals` external feed
(36h).

The grain is consumed, not just declared. It picks the seasonal cycle the
detector fits — a day-of-week rhythm for the daily metrics, a trading-day one
for the hourly — sets how much history is required, and decides the unit every
rupee threshold is compared in. Detecting the hourly metric on the daily
default was a real defect that survived until the triage queue put all five
side by side; it is written up as B-018, and the argument for the fix is one
test: the same 60% conversion collapse, flagged across the evening peak and
correctly ignored across the small hours, where it amounts to one order.

**The semantic contract is executable governance, not documentation.** Each
`contracts/*.yml` declares its definition, canonical SQL with dialect targets,
grain, drivers with owner and controllable lever, materiality thresholds,
freshness SLA per source, lineage, and access policy. The registry rejects
one-sided parent/child edges, cycles, unknown references, duplicate ids, drivers
whose source has no freshness SLA, and controllable levers with no owner.

**The evidence record is the spine.** Every computed fact becomes an immutable
`Evidence` object carrying provenance, method, method class and freshness. The
store is append-only, references must resolve at insert time, and unit/method
agreement is enforced at construction — so a price/volume/mix bridge cannot
report order counts.

## Key features

**Answer 2, the signal gap.** For a verified cause, the engine asks whether a
public warning existed, whether it was severe enough and early enough to act on,
whether the registered planning process has a step that consumes it, how often
this class of event has recurred, and who owns the gap. Four verdicts, three of
which decline:

| Verdict | When |
|---|---|
| `gap_found` | a public, actionable warning existed and the process consumes no such signal |
| `not_foreseeable` | a warning existed but arrived too late, too quietly, or privately |
| `no_gap` | nothing was published, or the process already consumes it, or the cause was internal |
| `coverage_unknown` | no process document is registered, so no gap can be claimed |

Foreseeability is decided **before** the gap, so hindsight cannot manufacture
blame. The gap is scoped to the verified cause rather than to the window, so a
weather warning that merely coincides with a release regression is not reported.

**Three personas over one evidence set.** Analyst, CFO and regional manager see
different projections; a test asserts the underlying evidence is byte-identical
across all three. Entitlement is enforced at the projection, before assembly.
When a removal changes the answer the response says so and names the role to
escalate to — a quiet omission would leave a manager reading a diagnosis that
silently excluded the region actually responsible.

**Calibrated confidence.** Five deterministic inputs, then an isotonic curve
fitted on a held-out half of the benchmark and never refitted after the test
half is scored. The raw score is never overwritten and banding still runs on it,
so refitting cannot silently move the point at which the engine refuses.

**Decision cards.** Every verified cause is carried to `driver → lever → action
→ expected impact → owner → confidence → monitoring plan`. Every field is
derived. A cause with no lever — weather has none — returns `controllable:
false` and a monitoring rule instead of an invented action. Nothing executes; a
card is a draft for a named human to approve.

**A bounded feedback loop.** Corrections never edit a past run and never move a
computed value. They propose changes to business-owned inputs, require two
independent submitters, and go contested rather than averaged when readers
disagree. Named misses become labelled regression cases.

**A run receipt.** Per-stage latency, model calls, tokens, rupee cost and the
deterministic share of wall time.

## Where AI is used, and where it is not

Three uses, and one pattern: **the model reads what humans wrote and proposes
structure; deterministic code verifies the proposal against the source and can
reject it.**

| Job | Method | Why |
|---|---|---|
| Detection | MSTL + robust z, configured per grain | seasonality is a solved statistical problem; which seasonality, and how wide the noise is, are not — both come off the contract, see B-018 |
| Decomposition | price/volume/mix identity | an identity, not an estimate |
| Ranking, track A | dimensional contribution | exact, reconciles to the total |
| Ranking, track B | ridge regression | generates candidates; never states one |
| Verification | DiD, placebo, exposure consistency | the question is causal |
| Retrieval | TF-IDF + SVD | offline, deterministic, no account |
| **Reading tickets** | **language model** | *"the card page just spins"* is a checkout failure no keyword table contains |
| Confidence | weighted score + isotonic | must be reproducible and auditable |
| Actions | contract lookup | owners and levers are governance, not inference |
| Signal gap | set difference over the feed | the finding must not come from a model |
| **Writing the narrative** | **language model** | prose is what models are for |
| Validation | deterministic checks | the model must not mark its own work |

**The verification is what makes a small open-weight model safe here.** When the
model quotes a ticket, the code locates that sentence in the source to derive
the character span. A paraphrase is not in the document, the span does not
resolve, and the extraction is dropped with a reason. Taking offsets from the
model would let a hallucinated citation point at real text.

**The model layer is a protocol, not a vendor.** Three obligations: take a
system prompt and a user message, return text matching a JSON schema, report
what it cost. No LLM SDK is in `requirements.txt`. The default is Mistral 7B
Instruct on Ollama — Apache 2.0, no account, no egress, inference inside the
boundary. Qwen2.5 below 35B is the same licence and a drop-in alternative. Llama
is deliberately not the default: its community licence caps free commercial use
at 700M monthly active users and fails the Open Source Definition.

Each task is routed to the model it needs. Extraction is classification against
a closed vocabulary and runs on a small tier; narration is harder and runs on a
standard one. Both are overridable per stage.

**Without any model the engine still runs.** Extraction falls back to a rule
table, the narrative to a deterministic template, and the receipt reports zero
model calls rather than the two the design intends. **The entire benchmark below
was produced in that mode** — which is the point: the accuracy does not come
from the model.

## Measured results

160 labelled cases with planted causes, planted correlation traps, planted noise
and planted unanswerable cases (`make bench`).

| | |
|---|---|
| **Top-1 among movements worth explaining** | **78.6%** (55 of 70) |
| Top-1 over the whole population | 38.9% |
| **False alarms on noise-only cases** | **0.0%** |
| Planted correlation traps rejected | 87.5% |
| **Cases needing an abstention that got one** | **88.2%** (2 missed of 17) |
| Abstentions that were right | 85.7% |
| Expected calibration error | 0.117 raw, **0.104 calibrated** on held out |
| Latency p50 / p95 | 0.080s / 0.178s |

The first two rows belong together. The engine explains movements that clear
both a statistical and a rupee materiality test and declines the rest, so top-1
across the whole population is bounded by how many movements are worth
explaining at all rather than by how often the engine is wrong when it speaks.

**Two of these figures moved because the measurement was wrong, and both are
written up in `BUGS.md`.** B-014: benchmark cases were sitting inside each
other's baseline windows, so an earlier run reported 46.4% top-1 and a perfect
conditional rate. The numbers got worse when the measurement got honest. B-016:
abstention recall counted correct silences as failures, reading 20.9% while the
engine was in fact abstaining on 16 of the 17 cases that called for it.

274 tests, 114 marked `invariant`. `make audit` runs 30 executable security,
logic and design checks.

## Requirements

- **Python 3.12 or later.** Developed on 3.14.6.
- **No database server, no Docker required.** DuckDB is embedded; the whole
  system runs from a clone.
- **No API key required.** The engine runs its deterministic path without one.

Optional:

- **Ollama** to exercise the model stages locally, with `mistral:7b-instruct`
  pulled. Or any OpenAI-compatible endpoint serving open weights.
- **Docker** if you would rather not build a Python environment.

Dependencies are pinned in `requirements.txt` from a verified working
environment: numpy, pandas, scipy, statsmodels, scikit-learn, duckdb, holidays,
pydantic, fastapi, uvicorn, PyYAML. No LLM SDK.

## Installation

```bash
git clone <repository-url> && cd whychain
make setup        # venv and pinned dependencies
make gen          # generate the synthetic warehouse and ground truth (~40s)
make demo         # console at http://localhost:8000
```

Or, without building a Python environment:

```bash
docker compose up                      # console, deterministic path
docker compose --profile ai up         # with an open-weight model alongside
```

The image generates the dataset and fits the calibration at build time, so it
ships having proved the engine works rather than asserting it.

## Configuration

**KPI contracts** in `contracts/*.yml` are the governance layer. Changing a
materiality threshold, adding a driver, or altering an access policy is a
contract edit; no module hardcodes a KPI definition. `make status` reads them
through the real loader and prints the graph.

**Model backend** via `.env` (copy from `.env.example`). Nothing is required.

| Variable | Meaning |
|---|---|
| `WHYCHAIN_LLM_BACKEND` | `ollama` (default), `openai`, or `none` |
| `WHYCHAIN_LLM_MODEL` | `mistral:7b-instruct` by default |
| `WHYCHAIN_LLM_BASE_URL` | for any OpenAI-compatible endpoint |
| `WHYCHAIN_LLM_API_KEY` | only for the hosted path |
| `WHYCHAIN_EXTRACTION_MODEL` | per-stage override, small tier |
| `WHYCHAIN_NARRATIVE_MODEL` | per-stage override, standard tier |

The backend is also selectable at runtime from the console, and per request via
`?backend=`, so the choice is demonstrable rather than only configurable.

## Execution

| Command | What it does |
|---|---|
| `make demo` | the console |
| `make test` | 274 tests; `-m invariant` for the 114 correctness ones |
| `make bench` | accuracy, trap rejection, calibration, latency |
| `make audit` | 30 executable security, logic and design checks |
| `make status` | the KPI graph through the real contract loader |
| `make guardrails` | watch the guardrails refuse bad input |
| `make verify-ai` | prove both model stages work before a demo depends on them |
| `make capture-ai` | run one case with the model and without, and keep both |

`make audit` and `make bench` both need `make gen` to have run.

## What to look at first

Six scenarios are planted in the generated data, each demonstrating a different
required behaviour.

| Scenario | Where | Shows |
|---|---|---|
| Multi-factor movement | `net_revenue`, West, Aug 2026 | three verified causes plus a planted decoy that correlates perfectly and caused nothing |
| Low confidence | `net_revenue`, South | a nationwide shallow movement leaves DiD no control group; the engine returns UNKNOWN with what it ruled out and a clarifying question |
| Sparse history | `aov`, Aug 2026 | a late-launched SKU; the verdict is `CANNOT_VERIFY`, deliberately distinct from `REJECTED` |
| Seasonal decoy | `net_revenue`, Oct 2025 | Diwali peaks then falls 18% overnight; correctly not an anomaly |
| Signal gap | `on_time_delivery`, West, Jul 2026 | 72h of public warning, a process that consumes no external risk signal, prior recurrence |
| Not foreseeable | `on_time_delivery`, South, May 2026 | a 40-minute carrier warning; the engine declines to call it a gap |

Also worth doing: switch **Reading as** between Analyst, CFO and Ops and watch
the projection change while the evidence does not. Set **Entitlement** to "South
only" while viewing West and watch the redaction fire, naming what was withheld,
what it was worth, and who to escalate to.

## Troubleshooting and FAQ

**The console shows no diagnosis, only detection.** Four of five KPIs decline
the price/volume/mix bridge. It is an identity over priced units; a rate has no
units to move and no price to change. Each contract declares whether it can be
decomposed and the other four say no, with a reason.

**The receipt says zero model calls.** No model backend is reachable. That is a
supported state and the benchmark is produced in it. Run `make verify-ai` for
what to configure.

**Persona or entitlement controls appear to do nothing.** Check that the running
server is current — `/openapi.json` should carry the `persona` and `entitled`
parameters. A stale `uvicorn` from before those landed is the most likely cause.

**`make audit` reports ten failures.** They are all the same missing file. Run
`make gen`.

**Why is top-1 only 38.2%?** Because it is measured over every case including
those the engine correctly declines. Among movements that clear materiality it
is 78.6%. Lowering a threshold to raise the headline is trap T-14 in `BUGS.md`.

**Can I run it on my own data?** Not yet. Contracts are hand-authored; inferring
one from an uploaded CSV is on the roadmap.

## Limitations

Stated plainly, because a limitation found by a reader costs more than one
declared by the author.

- **Difference-in-differences needs a control group**, and the control is
  geography. A repricing, a platform release or a policy change that lands
  everywhere at once is returned as untestable. That is honest and it is also a
  real coverage limit: much of what moves a P&L is not geographically
  heterogeneous.
- **Exact decomposition exists for `net_revenue` alone.** For the other four
  KPIs there is no identity, so Track A does not exist.
- **`ext_signals` is generated.** Every row says `source: generated`. The schema
  is the one a cached IMD or Open-Meteo snapshot drops into unchanged, and until
  one does, no document here claims a live external feed.
- **Confidence is still overconfident at the top of its range** after
  calibration. The curve is fitted on 73 cases; a real improvement on a small
  sample, not a solved problem.
- **The process document behind Answer 2** is representative, written for this
  repository, because a public repository cannot redistribute a third party's
  SOP. The underlying claim is cited to public sources rather than rested on it.
- **Contract-to-warehouse compilation is roadmap.** `dialect_targets` is
  declared; the Databricks and Snowflake renderings are hand-written examples.

## Repository map

| Path | Contents |
|---|---|
| `whychain/` | the engine, one package per pipeline stage |
| `whychain/evidence/` | the `Evidence` type — the spine of the system |
| `whychain/llm/` | the model protocol and its backends |
| `contracts/` | KPI semantic contracts (YAML) — executable governance |
| `datagen/` | synthetic dataset generator and planted causes |
| `data/ground_truth/` | **the engine must never read this.** Enforced by test |
| `bench/` | benchmark harness and metrics |
| `api/`, `ui/` | service and console |
| `docs/BRIEF.md` | the problem statement, verbatim. The authority on scope |
| `docs/REQUIREMENTS.md` | every objective mapped to code and a command |
| `DECISIONS.md` | architectural decisions and why alternatives were rejected |
| `BUGS.md` | traps identified in advance, and defects found with root cause |
| `HANDOFF.md` | current state, honestly |

## Maintainers

Team CtrlAltReinvent — Accenture Innovation Challenge 2026, problem statement
BusinessIntelligence.ai.
