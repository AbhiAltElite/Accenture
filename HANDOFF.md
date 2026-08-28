# Handoff

**Update this whenever you stop work.** It is the first thing the next person reads after `CONTEXT.md`.

---

## Status as of 2026-08-28

**Phase:** measured, and then corrected. The first benchmark numbers exposed a
set of correctness bugs that a green test suite had not; those are fixed and the
list below says what is genuinely built versus what the specs still only
describe.

**Read this before trusting an earlier version of this file.** It previously
said the system "runs end to end". It does not: `whychain/signalgap/`,
`whychain/rank/` and `whychain/narrate/` are empty files, so Answer 2, the
two-track ranking and the model-written narrative do not exist in code. The
pipeline from detect through decompose, verify, corroborate, confidence,
actions and personas does run, and the console shows it.

### Where to look first

```bash
make setup && make gen && make demo
```

Then open **http://localhost:8000/kpi/net_revenue**. The decision card and the
scenarios are the two newest things and they sit directly under the narrative.
The persona switch is in the rail under "Reading as".

**Only `net_revenue` produces a full diagnosis.** The other four decline, with a
reason, because the price/volume/mix bridge is an identity over priced units and
does not apply to a rate or a count (D-008). That is the honest scope of what is
built, not a defect to chase.

To see entitlement working, add `&entitled=East` to an `/api/diagnose` call for
the West: every cause disappears and the response says how much movement is out
of scope and who to escalate to.

| Check | Current |
|---|---|
| `make test` | 160 passing, 80 marked `invariant` |
| `make audit` | 30/30 (needs `make gen` first, or ten checks fail on the missing warehouse) |
| `make bench` | runs clean, and the numbers are the problem (see below) |
| `make lint` | clean |

### Done
- **`whychain/evidence/` — the spine, and it is now frozen.** `Evidence`,
  `Provenance`, `Freshness`, `EvidenceStore`. Records are immutable, the store is
  append-only, references must resolve at insert time, and unit/method agreement
  is enforced at construction so a bridge cannot report order counts
- **`whychain/corroborate/` — retrieval.** `Retriever` protocol,
  `NumpyRetriever` (default), `PgVectorRetriever`, offline `TfidfSvdEmbedder`.
  Search is windowed to the anomaly period and returns sentence-level spans, so a
  citation points at the words rather than the file
- **`whychain/contracts/` + `contracts/*.yml` — the governance layer.** All five
  KPIs of the graph, loading and cross-validating. The registry rejects one-sided
  parent/child edges, cycles, unknown references, duplicate `kpi_id`, drivers whose
  source has no freshness SLA, and controllable levers with no owner
- **`data/docs/sop/sop_demand_planning_v2.md`** — the process document Answer 2
  reads. `net_revenue`'s `signals_consumed` spans were computed from the file, and
  a test asserts each span actually contains the signal it names
- **`datagen/calendar.py`** — real Indian festival dates via the `holidays`
  package, with a build-up and hangover curve. Diwali peaks at +85% then falls
  18% overnight, which is the seasonal decoy
- **`datagen/catalog.py`**: 11 cities with real coordinates, 12 SKUs, one
  launched late for the sparse-history case. The coordinates are real so a
  weather feed can point at somewhere that exists; the warnings themselves are
  generated and say so (D-004)
- **`datagen/scenarios.py`** — `PlantedEvent`, `Slice`, `AvailableSignal`,
  `Scenario`. Decoys carry zero effect but are emitted identically to causes
- **`datagen/demo_cases.py`** — six scenarios covering all four expected verdicts
- **`datagen/` complete** plus `whychain/ingest/`, `whychain/detect/`,
  `whychain/decompose/`, `api/`, `ui/`
- **`ext_signals`**: public weather warnings per city with issue time, validity,
  severity, lead time and publisher: the fields foreseeability is decided on.
  Generated, and every row says so in `source`
- **The bridge reconciles exactly.** Volume, mix and price sum to the movement
  with zero residual, checked by a property test over a hundred random period
  pairs and asserted before anything is reported
- **`make audit`** runs 30 executable security, logic and design checks
- **`whychain/verify/` — the planted correlation trap is rejected.** Four tests;
  the one that catches the trap is exposure consistency, since
  difference-in-differences passes it unaided. That is worth understanding before
  changing anything here
- **`whychain/actions/`, the decision card.** Driver, lever, action, expected
  impact, owner, confidence, monitoring rule. Every field derived: the lever and
  owner from the contract, the impact from the movement DiD already measured. A
  cause with no lever returns `controllable: false` with no action and no
  invented recovery figure, which is what weather does. Nothing executes; a card
  drafts an approval request for a named human
- **`whychain/actions/simulate.py`, impact scenarios.** Rollback, a price move
  against the contract's declared elasticity, and a verified external effect
  carried forward. Each carries its assumptions as data and is labelled
  `scenario_estimate`. A scenario with no measured quantity behind it, or whose
  coefficient the contract does not declare, returns unavailable with a reason
  rather than a zero
- **`whychain/personas/`, the CFO, ops and analyst projections.** The evidence is
  identical across all three and only the projection differs, asserted by test.
  They differ structurally, not in tone. Entitlement is enforced here, before
  assembly, and a withheld cause is announced with the movement it accounts for
  and the role to escalate to
- **`whychain/telemetry/`, the run receipt.** Per-stage latency, method class,
  model calls, tokens, cost. It reports the model-call count it observed rather
  than asserting one: with no narrate stage that count is zero, and the receipt
  says the narrative came from a template
- 160 tests passing, 80 marked `invariant`
- Repo structure created, one package per pipeline stage
- Python 3.14.6 venv verified; full scientific stack installs cleanly (numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1)
- `MSTL`, `IsotonicRegression`, `Ridge` confirmed importable — no wheel gaps on 3.14
- Makefile, requirements, pyproject, .gitignore, .env.example
- Specs written: prototype, product outline, design checklist, security/logic checklist, concepts

### Next, in dependency order

**1. Fix the benchmark scale. Do this first.**
152 of 160 cases produce no material movement, so top-1 accuracy reads 2.9% and
the calibration table is fitted on five non-zero cases. This is the number a
judge will press hardest on, and everything else is cosmetic beside it.

The cause is not the detector: it sees 63.8% of planted movements. It is that
`datagen/bulk.py` plants effects on one channel or category and the benchmark
measures at region level, where they are swamped and fall under
`min_abs_delta_inr`. Either raise the planted effect sizes or evaluate at the
slice the event was planted on.

**Fix the scale, not the threshold.** Lowering the materiality floor so cases
pass is T-14, and it would also undo B-002.

What already holds and should be reported as-is: trap rejection 98.1%, false
alarm rate 0.0%, ECE 0.012. The anti-circularity claim, which is the actual
thesis, survives.

**2. `whychain/signalgap/`, still an empty file.**
Answer 2 is the differentiator and it does not exist in code. `ext_signals` now
carries everything it needs: `signals_available ∖ signals_consumed`, gated on
public availability, lead time and slice coverage. All four verdicts must be
reachable in the demo: `gap_found`, `no_gap`, `not_foreseeable`,
`coverage_unknown`. A system that always finds a gap has found nothing.

**3. `whychain/narrate/` and the validator.**
A constrained call over the evidence table, with binding, numeral and entity
checks, one retry, then a deterministic template fallback. Until it exists the
receipt honestly reports zero model calls, which is worth saying out loud rather
than quietly leaving a "two model calls" claim in the specs.

**4. One cached real weather snapshot.**
`ext_signals` has the right schema and marks every row `source: generated`. One
dated IMD or Open-Meteo snapshot drops into it unchanged, and only then may any
document claim a real external feed. Until then D-004's third guard is unmet and
says so.

### Dataset: where the remaining scope is

The structure is good: three grains, planted duplicate order ids, timezone
drift, decoys, and a correlation trap that verification genuinely rejects. The
gaps, ranked by what they buy:

1. **Effect sizes against the materiality floor.** Item 1 above. Not cosmetic:
   it is the whole benchmark headline.
2. **Candidate extraction is too easy.** Ops notes name their scope in clean
   prose a keyword matcher reads. Real incident logs are late, vague and
   sometimes wrong. Add an ambiguous note, one logged two days after the fact,
   and one irrelevant but plausible note, and corroboration starts earning its
   place instead of confirming what extraction already knew.
3. **No inventory or supplier mechanics.** There is `planned_stock` in the weekly
   plan and nothing daily: no inventory position, no supplier ETA, no stockout
   flag. This is the prerequisite for any supply-lane or geopolitical scenario,
   and without it such a feed has nothing to connect to.
4. **Returns are netted upstream.** `net_returns` is a no-op transform. Real
   returns arrive days later with reason codes, which is a genuine reconciliation
   problem and currently invisible.
5. **No contradictory-source case.** SECURITY-LOGIC-CHECKLIST asks for one
   (warehouse says volume down, tickets say stable) and `confidence` has
   contradiction detection that nothing exercises.
6. **The weather is generated.** Item 4 above.

### On external feeds, decided

Weather is the right and sufficient external signal for this dataset, and it has
a defensible route to the KPIs: warning, then fulfilment and footfall, then
delivery and revenue.

**Do not add stock-market data.** There is no mechanism from an index to this
retailer's revenue, conversion or delivery, and an analytically literate judge
will say so.

**FX only after a margin pathway exists**: imported-SKU metadata, a supplier cost
or COGS source, and a gross-margin KPI. Without those it is decorative finance
data.

**Geopolitical risk only as one typed, cached supply-lane event**, and only after
item 3 above. The mechanism must be modelled rather than inferred by a model, and
the event stays `CONTEXTUAL` until internal inventory or fulfilment evidence
corroborates it.

### Open question for the team
`data/docs/sop/sop_demand_planning_v2.md` is a representative process document
written for the repo, not a third-party one — we cannot redistribute someone
else's SOP in a public repository. The Answer 2 claim that the standard S&OP
cycle consumes no external risk signal should therefore be **cited** to public
sources in the README rather than rested on this file alone. Worth 20 minutes
before the submission.

### If you are picking this up cold
Read `CONTEXT.md`, then `whychain/evidence/types.py`. That file is the contract
between all three workstreams — every stage returns these objects and the UI
renders them. Understand it before writing a stage.

### Blocked / undecided
- Nothing blocked.
- Retrieval backend question is settled — see D-002. `TfidfSvdEmbedder` is the
  offline default; swapping in a hosted embedder means implementing the `Embedder`
  protocol and nothing else.

### Environment notes
- **No Postgres, no Docker required.** DuckDB is embedded; the whole system runs from a clone (see `DECISIONS.md` D-002)
- `.env` is required for LLM stages only. Stages 0–6 and the entire benchmark run without an API key

---

## Template — copy this block when you stop work

```markdown
## Status as of YYYY-MM-DD — <name>

### Done this session

### In progress (and exactly where it stopped)

### Next

### Blocked / needs a decision

### Anything the next person will trip on
```
