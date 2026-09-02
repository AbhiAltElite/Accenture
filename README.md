# WhyChain - Accenture Innovation Challenge 2026 Team- CtrlAltReinvent , IIT Hyderabad 
# Abhiram Ramachandran , Madiha Ahmed ,Polisetti Likhit Sai

[![CI](https://github.com/AbhiAltElite/Accenture/actions/workflows/ci.yml/badge.svg)](https://github.com/AbhiAltElite/Accenture/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-486-informational)](tests/)
[![Audit checks](https://img.shields.io/badge/audit-33%2F33-informational)](docs/SECURITY-LOGIC-CHECKLIST.md)

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

## For reviewers, in twenty minutes

Four commands and one page. Nothing here needs an API key, a database server or
a network connection.

```bash
make setup && make gen     # environment, then the synthetic warehouse (~40s)
make demo                  # console at http://localhost:8000
```

1. **Open `net_revenue`, West, Aug 2026.** Three verified causes, and a planted
   decoy that correlates perfectly and caused nothing. Click any sentence and it
   resolves to the query, the rows, or the character span behind it.
2. **Open `net_revenue`, South.** The engine returns UNKNOWN, says what it ruled
   out, and asks a clarifying question. Refusal is the feature.
3. **Set Entitlement to "South only" while viewing West.** The redaction fires
   and names what was withheld, what it was worth, and who to escalate to.
4. **Run `make bench`** for accuracy, trap rejection, calibration and latency,
   and **`make audit`** for 33 executable security, logic and design checks.

Then read **[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)**, which maps every
objective in the brief to the module that satisfies it and the command that
demonstrates it, and marks the rows only partly met. The other working documents
are indexed in **[docs/README.md](docs/README.md)**.

If you have twenty minutes and not twenty-five, skip step 4 and read
[*Measured results*](#measured-results) instead — `make bench` reproduces it.

---

## Table of contents

- [For reviewers, in twenty minutes](#for-reviewers-in-twenty-minutes)
- [The problem](#the-problem)
- [Approach](#approach)
- [Architecture](#architecture)
- [Three industries, one engine](#three-industries-one-engine)
- [Key features](#key-features)
- [Where AI is used, and where it is not](#where-ai-is-used-and-where-it-is-not)
- [Measured results](#measured-results)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Execution](#execution)
- [What to look at first](#what-to-look-at-first)
- [Troubleshooting and FAQ](#troubleshooting-and-faq)
- [Scalability](#scalability)
- [How this answers the challenge](#how-this-answers-the-challenge)
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
rendering, not error paths. The engine abstains on 88.2% of the cases whose
correct answer is an abstention — 15 of 17, the same figure as the results
table, which `make bench` prints.

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
sources (3 grains + 1 external feed + a second system posting the same number)
   ↓ reconcile grain · freshness gate
detect (MSTL → robust z on the residual, per the contract's grain)
   ↓ materiality (statistical AND ₹)
reconcile against the ledger → CONTRADICTED stops here, before any explanation
   ↓
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
next check, when abstaining (gated: no cause, no invented name, no invented
   figure)                                          ← model call 2 of 3
   ↓
narrate (constrained to the evidence table)         ← model call 3 of 3
   ↓
validate (binding + numeral + entity + rejected-cause checks)
   ↓
project (persona + entitlement, applied before assembly)
   ↓
feedback (bounded: business inputs only, never a computed value)
```

### What is simulated, stated plainly

Three things in this build are simulated rather than integrated, and it is worth
reading them here rather than discovering them later. Each is a deliberate scope
decision, not an oversight, and each is labelled in the system itself.

**The sources are heterogeneous in grain, and in one case in origin.** Seven
source tables with genuinely different grains (hourly checkout conversion against
daily revenue), different declared freshness SLAs, and different business
meanings — all emitted by one generator into one DuckDB file, so there is no
late-arriving partition and no schema drift.

One of them is a **second system posting the same quantity**, which is the part
that was missing. `finance_ledger` nets returns on the date the credit note is
raised rather than the date of sale, and posts to the rupee at invoice level, so
it and `pos_txn` sit **2.1% apart on a median region-day** — an ordinary
disagreement that a reconciliation has to tolerate rather than escalate, and the
thing a tolerance is calibrated against. Measuring the whole distribution rather
than its middle found the limit of stating that tolerance as a percentage: North,
South and West breach 5% on under 1% of days, and East, the smallest region,
breaches on 55.7% and reaches the contradiction threshold on 10.7%, because an
unchanged absolute posting lag is a larger share of a smaller number. It is
recorded in the contract rather than retuned, for the reason the feedback design
gives: a threshold moved to improve a verdict is how thresholds stop meaning
anything. Reconciling
*grain* is a shape problem and the engine already solved it. Reconciling two
independent postings of one number is a different problem, and it needed
something capable of disagreeing.

**The external feed carries real provenance and generated rows.** Publisher
names, source URLs, severities and lead times are the real ones; every row says
`source: generated`, and the console shows that field.

**The rupee cost is indicative.** Tokens, calls, cache hits and latency are
measured. The cost line applies one reference rate uniformly, which is wrong for
a self-hosted open-weight model (the cost is compute) and for a free tier (there
isn't one). The receipt carries the basis alongside the number.

**And one that is not simulated but is worth the same clarity:** entitlement is
enforced — in SQL from the contract's own `row_filter`, at the request boundary,
and again at the projection — but it enforces a *claim*, because there is no
identity provider here. Binding an identity to a scope is the deployment's job.

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

**A contradiction is its own verdict, not a lower confidence.** Before anything
is explained, the engine asks whether the second system agrees that the movement
happened. Three states, and the middle one is the useful one: `agreed` is the
ordinary day; `drift` is further apart than posting policy explains, which lowers
confidence and gets said out loud without stopping anything; `contradicted` is
far enough apart that the quantity itself is in question.

The reason it sits *above* the explanation rather than among it is that nothing
below can catch this. The dataset plants a window where the POS extract silently
loses a channel while the ledger keeps posting the truth. Detection flags the
movement, because the series really does fall. Ranking finds the slice, because
that slice really is missing. The causal tests confirm the fall is isolated,
because it is. **Every stage does its job correctly and arrives at a confident,
well-evidenced diagnosis of an event that did not happen** — and from inside the
POS extract there is no way to know, because in there the orders genuinely are
not present. The only available evidence is a second system that disagrees.

So the verdict is `contradicted` rather than `unknown`, and the distinction is
not cosmetic: "we could not tell what caused this" sends a finance director
looking for a commercial explanation, and "two systems disagree that this
happened" sends someone to the pipeline. Select **North, 10–12 June 2026**.

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

**A governed correction workflow.** Corrections never edit a past run and never
move a computed value. They propose changes to business-owned inputs, require two
independent submitters, and go contested rather than averaged when readers
disagree. Named misses become labelled regression cases.

**The loop closes on one target, and says so about the other four.** A proposal
that reaches quorum on `materiality_threshold` can be applied by a named person,
and the next diagnosis reads the new floor: measured, two analysts calling a
₹26,963/day movement not worth diagnosing takes West's flagged days from 23 to
16. Three properties make that safe to have built:

- **The new value is derived, not typed.** The floor moves to 1% clear of the
  largest movement the supporting readers rejected, capped at twice the previous
  floor, and the record carries the movements it was computed from. A threshold
  somebody picked to make a complaint go away is how a materiality floor becomes
  the place inconvenient findings are buried.
- **An applied change is an overlay, not an edit.** The `.yml` stays the
  reviewed definition; applications are appended to `data/feedback/applied.jsonl`
  and composed at load, before validation, so feedback cannot produce a contract
  a person could not have written. Lifting a change is deleting a line.
- **Everything else refuses by name.** `candidate_ranking`, `candidate_source`,
  `driver_mapping` and `retrieval_filter` have no consumer, and the console says
  which and why rather than offering a button that can only fail. A refusal a
  reader can act on beats a queue nobody drains.

Still called a workflow rather than a learning loop: **nothing here retrains
anything, and four of the five targets remain a proposal a human acts on.** What
changed is that the fifth is no longer a promise.

**A run receipt.** Per-stage latency, model calls, cache hits, tokens, the
deterministic share of wall time, and a rupee figure carrying its own basis —
a reference rate, which is not what a self-hosted or free-tier run actually
costs.

## Where AI is used, and where it is not

Four uses, and one pattern: **the model handles what is language; deterministic
code checks the proposal against the source and can reject it.** It never
touches a number.

| Job | Method | Why |
|---|---|---|
| Detection | MSTL + robust z, configured per grain | seasonality is a solved statistical problem; which seasonality, and how wide the noise is, are not — both come off the contract, see B-018 |
| Decomposition | price/volume/mix identity | an identity, not an estimate |
| Ranking, track A | dimensional contribution | exact, reconciles to the total |
| Ranking, track B | ridge regression | generates candidates; never states one |
| Verification | DiD, placebo, exposure consistency | the question is causal |
| Cross-source reconciliation | residual against a declared tolerance | two systems agreeing is arithmetic, not a judgement |
| Retrieval | TF-IDF + SVD | offline, deterministic, no account |
| **Writing the search query** | **language model** | an ops note and the complaint it causes are different registers; see below |
| **Reading tickets** | **language model** | *"the card page just spins"* is a checkout failure no keyword table contains |
| Confidence | weighted score + isotonic | must be reproducible and auditable |
| Actions | contract lookup | owners and levers are governance, not inference |
| Signal gap | set difference over the feed | the finding must not come from a model |
| External context on a cause | window/region overlap over the feed | a published warning is a fact with a publisher, not an inference |
| **Writing the narrative** | **language model** | prose is what models are for |
| **Proposing the next check** | **language model** | the useful next step depends on the shape of a particular failure, which is what a three-way branch cannot reach |
| Validation | deterministic checks | the model must not mark its own work |

**The most useful sentence in the product is written by the model, and it is the
one it is hardest to let it write.** On the days there is no diagnosis, what an
analyst gets is the next check — and an abstention that only says "unknown"
wastes the hour as surely as a wrong answer. That sentence was three template
branches, and templates are exactly wrong for it: the useful next step depends
on which candidates were rejected and why, which sources were stale, whether the
two systems reconciled. On the planted feed break the model writes *"Verify that
the net_revenue extract for North region from 2026-06-10 to 2026-06-12 is
complete"*, which no branch would have produced.

It is also the one place a model is asked to be constructive about a movement
nobody has explained, which is precisely where a plausible suggestion becomes a
stated cause in somebody's retelling. So four deterministic gates run before a
reader sees it, and the template stands if any fails:

| The gate | Why |
|---|---|
| It may not assert a cause | `caused by`, `due to`, `is the cause` and nine more. The sentence proposes an action or it is dropped |
| It may name only what the run contains | An invention is a *name* and looks like one — capitalised, or carrying an underscore or a digit. Ordinary English is not checked, because it cannot name a system |
| Figures must appear in the facts, character for character | The same rule the narrative validator enforces |
| One sentence, under 30 words, imperative | A next check nobody reads is not one |

The first version of the second gate checked every word against the run's own
vocabulary and rejected "shipped", "request" and "re-running" — almost nothing
could pass, and widening the list until they did would have left the check doing
nothing. `tests/test_nextcheck.py` pins all four.

**The verification is what makes a small open-weight model safe here.** When the
model quotes a ticket, the code locates that sentence in the source to derive
the character span. A paraphrase is not in the document, the span does not
resolve, and the extraction is dropped with a reason. Taking offsets from the
model would let a hallucinated citation point at real text.

**The model layer is a protocol, not a vendor.** Three obligations: take a
system prompt and a user message, return text matching a JSON schema, report
what it cost. No LLM SDK is in `requirements.txt`. The default is Mistral 7B
Instruct on Ollama — Apache 2.0, no account, no egress, inference inside the
boundary. Qwen2.5 at 7B, 14B or 32B is the same licence and a drop-in
alternative — not the 3B or the 72B, which Alibaba ships under its own licences
rather than Apache 2.0, a distinction worth making because "the small ones are
Apache" is the version of this fact that circulates. Llama
is deliberately not the default: its community licence caps free commercial use
at 700M monthly active users and fails the Open Source Definition.

**The clearest thing the model does here is translate between registers.** An
operational note and the complaint it produces share almost no vocabulary. A
terminal writes *"turnaround extended by nine days; downstream allocation
reduced to 55 per cent of indent"*; the dealer writes *"no stock at the depot
since Monday, allocation cut to half"*. Term-frequency retrieval bridges that
only by accident, and the alternative is a synonym table written by hand for
each new industry — which is exactly the part of onboarding that does not scale.
Given the note above, the model returns `no stock dry out allocation cut supply
delayed`, and the twelve dealer complaints that describe the event are found.

It is used **on the margin, not by default**: only where the deterministic
query's best match falls below a floor, which is what a register mismatch looks
like from inside retrieval. Retail's release notes already share vocabulary with
retail's tickets and spend nothing.

**And on this dataset that margin is never reached, which is worth stating
plainly.** The mechanism works — given the terminal note above, the model does
return `stock supply delivery delay stockout` — but the deterministic query
clears the retrieval floor on every case in all three verticals, so expansion
does not fire in a normal run and the documents found are the same either way.
`make capture-ai` measures it: 28 documents read with the model against 31
without, every computed figure identical. The register-mismatch claim is
therefore **demonstrated as a capability and not exercised by the planted data**,
and closing that gap means generating a case where operational and complaint
vocabulary genuinely do not overlap, which is a change to the generator rather
than to the engine. It is not made here.

Each task is routed to the model it needs — expansion and extraction are
classification-shaped and run on a small tier, narration is harder and runs on a
standard one — and each is overridable per stage. **Routing is real and the
default configuration does not use it**: `WHYCHAIN_INTENT_MODEL`,
`WHYCHAIN_EXPANSION_MODEL`, `WHYCHAIN_EXTRACTION_MODEL` and
`WHYCHAIN_NARRATIVE_MODEL` each override their stage, and with none of them set
all four stages show the same model on the receipt. A genuine tier split needs
two model ids configured, and which two is a licence decision rather than a
performance one.

**The economics are part of the design, not an afterthought.** Every call is
content-addressed and cached on disk, keyed on the model, backend, prompt,
schema and token ceiling, so nothing that could change the answer is left out of
the key. Every call is bounded at 45 seconds by default and
`WHYCHAIN_LLM_TIMEOUT` moves it, past which the deterministic path stands in and
the receipt says so. Hits are counted apart from calls, and the
token figures still report what the reading costs uncached — a receipt claiming
free work would be the same dishonesty as an uncalibrated probability.

**A hosted backend is configuration, not a rewrite.** `OpenAICompatibleModel`
speaks the API that Groq, Together, OpenRouter, vLLM and Google's compatibility
endpoint all implement, so running Gemini instead is four environment variables
and no code. The trade is stated rather than hidden: inference leaves the
boundary, which is what the local open-weight default exists to avoid.

**Without any model the engine still runs.** Query expansion falls back to the
deterministic query, extraction to a rule table, the narrative to a template,
and the receipt reports zero model calls rather than the three the design
intends. **The entire benchmark below was produced in that mode** — which is the
point: the accuracy does not come from the model.

**And the console never waits for one.** Every figure is computed
deterministically, so the page renders complete and correct in about a second;
a pinned backend is fetched second and swapped in when it lands, with the page
saying meanwhile that the figures are final and the prose is still being
written. That is also the honest demonstration of the claim this design rests
on — the reader watches the numbers settle first and stay put while the prose
changes around them.

## Measured results

160 labelled cases with planted causes, planted correlation traps, planted noise
and planted unanswerable cases (`make bench`).

| | |
|---|---|
| **Top-1 among movements worth explaining** | **64.4%** (56 of 87) |
| Top-1 over the whole population | 38.9% |
| **False alarms on noise-only cases** | **0.0%** |
| Planted correlation traps rejected | 87.5% |
| **Cases needing an abstention that got one** | **88.2%** (2 missed of 17) |
| Abstentions that were right | 85.7% |
| Expected calibration error | 0.069 raw, **0.042 calibrated** on held out |
| Latency p50 / p95 | 0.07s / 0.18s (Apple M4, 16 GB; `make bench` prints yours) |

The first two rows belong together. The engine explains movements that clear
both a statistical and a rupee materiality test and declines the rest, so top-1
across the whole population is bounded by how many movements are worth
explaining at all rather than by how often the engine is wrong when it speaks.

**Two of these figures moved because the measurement was wrong, and both are
written up in `BUGS.md`.** B-014: benchmark cases were sitting inside each
other's baseline windows, so an earlier run reported 46.4% top-1 and a perfect
conditional rate. The numbers got worse when the measurement got honest. B-016:
abstention recall counted correct silences as failures, reading 20.9% while the
engine was, at that run, abstaining on 16 of the 17 cases that called for it.
It is 15 of 17 now: one case that used to abstain no longer does, and the table
above is the current measurement rather than the one B-016 was fixed against.

**And one moved because the engine got more honest rather than less accurate.**
B-020: three verified causes could contribute 188% of a movement while coverage
scored a perfect 100%, because the over-explanation was detected, clamped, and
the finding thrown away. Pricing that overlap into the score took expected
calibration error from 0.117 to 0.069 raw, and 0.099 to 0.042 on the held-out
half, with every other rate above unchanged. A confidence score that is right
about how uncertain it is was the point of having one.

486 tests, `make audit` runs 33 executable security, logic and design checks.
The suite forces the deterministic backend: a test whose result depends on what
a 7B happened to generate is a sample of one, not a test.

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
git clone https://github.com/AbhiAltElite/Accenture.git && cd Accenture
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
| `WHYCHAIN_OLLAMA_BASE_URL` | a remote Ollama; the local path never reads `WHYCHAIN_LLM_BASE_URL` |
| `WHYCHAIN_OLLAMA_MODEL` | the local model, when `WHYCHAIN_LLM_MODEL` describes a hosted one |
| `WHYCHAIN_INTENT_MODEL` | per-stage override, small tier |
| `WHYCHAIN_EXPANSION_MODEL` | per-stage override, small tier |
| `WHYCHAIN_EXTRACTION_MODEL` | per-stage override, small tier |
| `WHYCHAIN_NARRATIVE_MODEL` | per-stage override, standard tier |
| `WHYCHAIN_LLM_TIMEOUT` | seconds one call may take before the deterministic path stands in; 45 |
| `WHYCHAIN_LLM_CACHE` | where the content-addressed cache lives; `data/llm_cache` |
| `WHYCHAIN_LLM_FREE_ONLY` | refuse a model id carrying no free marker, rather than warn |

That is every variable the engine reads. `.env.example` carries the same list
with the reasoning; `grep -rho 'WHYCHAIN_[A-Z_]*' whychain api` checks it.

The backend is also selectable at runtime from the console, and per request via
`?backend=`, so the choice is demonstrable rather than only configurable.

## Execution

| Command | What it does |
|---|---|
| `make demo` | the console |
| `make test` | 486 tests; `-m invariant` for the 227 correctness ones |
| `make bench` | accuracy, trap rejection, calibration, latency |
| `make audit` | 33 executable security, logic and design checks |
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

**Why is top-1 only 38.9%?** Because it is measured over every case including
those the engine correctly declines. Among movements that clear materiality it
is **64.4%**, and `make bench` prints both lines so neither has to be taken on
trust. Lowering a threshold to raise the headline is trap T-14 in `BUGS.md`.

**Can I run it on my own data?** Not yet. Contracts are hand-authored; inferring
one from an uploaded CSV is on the roadmap.

## Scalability

The brief names scalability twice — once in the prototype criteria and again for
the Grand Finale — and judges mean two different things by the word. They are
answered separately, because one is demonstrated and the other is designed for.

### Scaling across businesses — demonstrated

Three industries run on this engine: an omnichannel retailer whose metrics move
because of things it did to itself, and a fuel marketer and a generator whose
metrics move because of things done to them — excise notifications, refinery
turnarounds, port closures, tariff orders, grid constraints.

**What a new industry costs is the measure.** It supplies five contracts, a
generated warehouse against the same six source names, and four vocabularies:
which words in an operational note name which driver, which complaint codes
corroborate which cause, what its planning extract calls a planned intervention,
and what reversing a cause recovers. It changes **no calculation**. Detection,
the price/volume/mix bridge, both ranking tracks, the causal tests, confidence,
calibration and every threshold are the contract's job in all three.

The claim is checked rather than asserted. The retail warehouse regenerates byte
for byte after the generator was parameterised — 1.8 million order lines,
identical hashes — and the benchmark is identical on every rate. If adding two
industries had cost the first one a single digit, it would be visible.
`tests/test_verticals.py` keeps it true: 69 tests parameterised over all three,
checking every pair of places that has to agree.

### Scaling with data and load — measured, and one wall found

`make scale` replicates the fact tables into synthetic regions and times the same
read underneath them, then drives the running console concurrently. Both halves
were argued from the shape of the code until this existed; the argument turned
out to be half right, and the half that was wrong is the more useful finding.

**With more data.** Retail's 2.5M fact rows, replicated to 40M:

| rows | on disk | one region | same query, no lineage transforms | rows returned |
|---:|---:|---:|---:|---:|
| 2,519,966 | 36 MB | 0.088s | 0.022s | 32,879 |
| 10,079,864 | 135 MB | 0.443s | 0.037s | 32,879 |
| 40,319,456 | 523 MB | 3.151s | 0.038s | 32,879 |

The answer is the same size at every scale, so nothing is being pulled back
proportional to the table — that part of the claim holds. But 16x the rows costs
**36x the time**, and the third column says why. Strip the contract's declared
lineage transforms and the identical aggregation goes from 0.022s to 0.038s:
**1.8x for 16x the rows, effectively flat.** The `GROUP BY` does push down. The
entire cost is `dedupe_order_id`, which is a window partitioned by order id, so
no region predicate can be pushed below it and every read re-derives it across
the whole table.

That is a specific, fixable thing rather than a vague ceiling: **materialise the
deduped source at ingest instead of per query.** Lineage stays executable — the
transform still genuinely runs, once, where it is cheap — and the per-read cost
goes to the flat column. It is not done here, and it is the first thing to do.

Also worth stating: pushing the entitlement predicate below the aggregate was
tried and reverted, because measurement said it bought nothing. DuckDB cannot
push a region filter past the same window function, so the change was 2.543s
against 2.559s at 40M rows — complexity for noise. An optimisation with no
measured win is the same species of claim this section exists to replace.

**With more readers.** 48 diagnoses on the deterministic path, one uvicorn
process:

| concurrent | ok | failed | p50 | p95 | req/s |
|---:|---:|---:|---:|---:|---:|
| 1 | 48 | 0 | 0.584s | 0.612s | 1.85 |
| 4 | 48 | 0 | 2.157s | 2.598s | 1.81 |
| 8 | 48 | 0 | 4.812s | 5.487s | 1.68 |
| 16 | 48 | 0 | 9.310s | 12.645s | 1.61 |

Nothing fails and nothing corrupts, which is worth knowing. Throughput is also
flat at roughly 1.7 requests per second however many readers arrive, and latency
grows linearly with concurrency: the work is serialised behind one process and
one warehouse connection. **So the honest capacity figure for this build is
about two diagnoses per second, and adding readers adds queue, not throughput.**
The route out is ordinary — multiple workers, a connection per worker, and the
in-process series cache moved behind them — and none of it is built.

**The honest summary.** Scaling to another business is demonstrated and costs
configuration. Scaling with data is measured, and the wall is a per-query window
function with a named fix. Scaling with readers is measured, and the number is
low and single-process. What is no longer true is that any of this rests on the
SQL being SQL.

## How this answers the challenge

The four things the prototype is judged on are not the same list as the eight
objectives, and it is worth checking them separately — a build can satisfy every
objective and answer none of these well.

| Judged on | Where to look |
|---|---|
| **How the solution works in practice** | The console, and the six demo scenarios in *What to look at first* |
| **How AI enables or enhances it** | *Where AI is used, and where it is not*; `make capture-ai` runs one case with the model and without and keeps both, so the claim that the numbers do not move is checkable rather than asserted |
| **Potential scalability** | The section above, split into what is demonstrated and what is argued |
| **The impact it can create** | The business proposal, and *Measured results* below for the evidence it rests on |

`docs/REQUIREMENTS.md` maps all eight objectives and all ten minimum
expectations to the module that satisfies each and the command that demonstrates
it, including the rows only partly met.

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
| `whychain/reconcile/` | does a second system agree the movement happened |
| `whychain/feedback/apply.py` | applying a proposal, as an audited contract overlay |
| `whychain/llm/` | the model protocol and its backends |
| `contracts/` | KPI semantic contracts (YAML) — executable governance |
| `datagen/` | synthetic dataset generator and planted causes |
| `data/ground_truth/` | **the engine must never read this.** Enforced by test |
| `bench/run.py` | accuracy, trap rejection, calibration, latency |
| `bench/scale.py` | what happens with more data and more readers (`make scale`) |
| `api/`, `ui/` | service and console |
| `docs/README.md` | index of the working documents, with what each is for |
| `docs/REQUIREMENTS.md` | every objective mapped to code and a command |
| `DECISIONS.md` | architectural decisions and why alternatives were rejected |
| `BUGS.md` | traps identified in advance, and defects found with root cause |

## Maintainers

Team CtrlAltReinvent — Accenture Innovation Challenge 2026, problem statement
BusinessIntelligence.ai.
