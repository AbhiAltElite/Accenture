# Handoff

**Update this whenever you stop work.** It is the first thing the next person reads after `CONTEXT.md`.

---

## Status as of 2026-08-28 (later session)

**Phase:** feature-complete against the Round 2 brief. Every stage named in the
`CONTEXT.md` architecture diagram now exists in code and runs; the previous
version of this file listed three empty packages, and they are written.

### Done this session
- **`whychain/signalgap/`, Answer 2 exists.** `read_signals`, `find_precedents`,
  `assess`, `find_gap`. All four verdicts are reachable *from the generated
  warehouse*, not just from hand-built fixtures: `gap_found` (demo-05, 86h of
  lead time, 3 prior episodes), `not_foreseeable` (demo-06, a 40-minute carrier
  warning), `no_gap` (an internal release regression), `coverage_unknown` (a KPI
  with no registered process document)
- **The gap is scoped to the verified cause, not to the window.** Weather
  warnings are in the feed most weeks of the monsoon, so an engine that checks
  the window alone reports a signal gap on a release bug, real warning, real
  lead time, no relationship whatever. That was the first thing the new stage
  did, and `TestScopedToTheCause` exists so it cannot come back
- **`whychain/rank/`, two tracks that never merge.** Track A exact from the
  identity; track B a standardised ridge over the driver series, every row
  `HYPOTHESIS` and `CORRELATIONAL`, rejected candidates barred from re-entering
- **`whychain/narrate/`, brief, writer, validator.** `ModelWriter` (constrained
  `claude-opus-5` call, JSON schema, adaptive thinking) and `TemplateWriter`
  implement one protocol and pass through one validator. Four checks: binding,
  numerals, entities, rejected-as-cause. A failed call or a wholly-rejected
  narrative falls back to the template and *says so*
- **`whychain/feedback/`, the loop the brief asks for, bounded.** Corrections
  never edit a run and never move a computed value. They propose changes to
  business-owned inputs, need two independent submitters, and go contested
  rather than averaged when readers disagree. Named misses become labelled
  regression cases
- **Benchmark scale fixed, and then the harness itself.** Planted effects were
  too small to clear regional materiality, which took top-1 from 2.9% to 46.4%.
  Measuring that fix exposed a second, older defect: events were planted 20 to
  109 days apart in the same region while verification looks back 110 days, so
  cases were partly measuring each other. With the clearance guaranteed by
  construction the honest figures are **top-1 36.6%**,
  75.4% among the 69 cases that clear materiality, false alarms
  0.0%, trap rejection 86.7%,
  ECE 0.103, p95 0.175s. The numbers fell because the
  measurement got honest
- **Complete UI overhaul.** Masthead with live run context, a rail, a document
  column and a margin for run metadata; numbered report sections; the overview
  as a watchlist table rather than tiles; Answer 2 rendered as all four verdicts
  with the reached one marked. No status dots, no accent-striped cards
- 222 tests (91 invariant), `ruff` clean, `make audit` 30/30

### Fixed along the way, all found by running the thing
- The persona projection dropped `decisions`, `signal_gap` and `narrative`, so
  the CFO; the reader who most needs Answer 2, saw neither it nor the decision
- `FeedbackStore.record` wrote to disk before warming its cache, counting every
  entry twice and inflating the number the quorum rule depends on
- Track A was sorted so that slices moving *against* the total headed a list of
  reasons the metric fell
- With a region selected, `region = West` topped Track A at a 100% share, which
  is true, useless, and displaced a real contributor
- The narrative validator rejected its own correct output: ISO dates parsed as
  numerals, and `4.05` quoted from inside a cited claim read as fabricated

### Next
1. **Abstention cannot be scored, and it is a brief requirement.** Every case in
   `datagen/bulk.py` is either `verified` or `no_anomaly`, so nothing in the
   population has "the evidence is insufficient" as its correct answer and both
   abstention rates report zero for want of a denominator. The behaviour is real
   and fires in the console on `demo-02-low-confidence`. `ExpectedVerdict`
   already has `UNKNOWN` and `CANNOT_VERIFY`; the population needs a share of
   each. Two that generate naturally: a shallow movement planted in every region
   at once, which leaves difference-in-differences no control group, and a slice
   with too little history to test
2. **Confidence is overconfident at the top of its range.** Scores in 0.8-1.0
   average 0.917 and are right 71.2% of the time. The isotonic calibration the
   design calls for is not fitted; fit it on a held-out split and never re-fit
   after seeing test results (T-13)
3. **A real weather snapshot.** `ext_signals` still says `source: generated` on
   every row. One cached IMD or Open-Meteo file drops into the schema unchanged,
   and only then may any document claim a live external feed
2. **Make the corroboration extractor model-backed**, so an API-keyed run
   genuinely reports two model calls. The protocol is already in place; only the
   extractor changes, and T-01 then becomes assertable as `== 2`
5. **The residual benchmark gap is a detector question, not a data question.**
   96 of 160 cases produce no material movement because a ~10% regional move sits
   at z ≈ 2.2 against 4.5% daily noise, under the z ≥ 3 gate. Pooling the event
   window rather than testing single days would recover most of them, a real
   improvement, and a change to `detect/`, not to a threshold (BUGS.md T-14)
6. **Apply-a-proposal is not wired.** Feedback reaches quorum and the console
   says so, but a human applying a proposal to a contract is still manual

### Blocked / undecided
- Nothing blocked.
- The SOP redistribution question is settled: `README.md` now cites public
  sources for the claim that a standard S&OP cycle consumes no external risk
  signal, and the repo's own document is labelled as representative.

### Anything the next person will trip on
- **Restart the server after pulling.** A stale `uvicorn` from before the
  persona work cost an hour of debugging a UI that was fine; check
  `/openapi.json` carries the `persona` parameter before believing a bug.
- `make gen` must be re-run: `ext_signals` did not exist in warehouses built
  before this session, and `find_gap` needs it.

---

## Status as of 2026-08-28 (third session)

**Phase:** every objective and every minimum expectation in the brief is mapped
to code and a command in `docs/REQUIREMENTS.md`, including the rows only partly
met.

### Done this session
- **`docs/REQUIREMENTS.md`.** The requirement to implementation matrix
  `STRATEGY.md` called insurance against a literal scorer, and which did not
  exist. All 8 objectives, all 10 minimum expectations, plus the
  native/configured/custom/integrated classification the brief asks for
- **Entitlement is demonstrable.** The API took `entitled`; the console never
  sent it, so the role-based security expectation could only be shown with
  curl. There is now a rail control, and selecting "South only" while viewing
  West produces the honest redaction notice naming the escalation role
- **Abstention is measurable.** The population had only `verified` and
  `no_anomaly` in it, so nothing had "the evidence is insufficient" as its right
  answer and both abstention rates reported zero. `datagen/bulk.py` now plants a
  share of nationwide shocks, which are material and leave
  difference-in-differences no control group. Abstention precision
  **86.4%**, recall **94.1%**, with 1 missed abstention of 17
- **Confidence is calibrated.** `whychain/confidence/calibrate.py` fits an
  isotonic curve on a held-out half and never refits after the test half is
  scored (T-13). Held-out ECE 0.1171 to 0.1043. The raw score is never
  overwritten, banding still runs on it, and with no curve on disk the console
  says "score" rather than "probability"
- **The precedent count no longer overreaches.** It said "2 prior episodes",
  which a reader takes as "this cost us money twice". It now measures each
  episode against the metric's own history and reports "2 prior episodes, 1 of
  which coincided with a material movement"

### Current figures
Top-1 38.2%, 78.6% among the 70 cases that clear materiality, verified at
all 47.9%, false alarms 0.0%, traps rejected 87.5%, abstention
precision 86.4% recall 94.1%, ECE 0.1171 raw and 0.1043 calibrated,
p95 0.180s. 252 tests, 105 invariant.

### Next
1. **One missed abstention.** Recall is 94.1%: of the 17 cases whose correct
   answer is "the evidence is insufficient", one was answered anyway. It is a
   single case rather than a rate to chase, so read it rather than tune against
   it. (The 20.9% previously recorded here was a metric defect, not engine
   behaviour: see B-016)
2. **Calibration is fitted on 73 cases.** Real, and thin. More panels, or a
   larger `per_region`, would make the curve worth more than it currently is
3. **Make the corroboration extractor model-backed**, so an API-keyed run
   reports two model calls and T-01 becomes assertable as `== 2`
4. **A real weather snapshot** into `ext_signals`
5. **Pool the event window in detection.** 71 of 160 cases still produce no
   material movement because a sustained multi-day drop is tested a day at a
   time. This is the largest single accuracy gain available
6. **Apply-a-proposal is still manual**

### Anything the next person will trip on
- **`make bench` used to crash silently after printing.** A numpy bool reached
  `json.dumps`, the write raised, and `bench/report.json` kept the previous
  run's numbers while the terminal showed the new ones. Fixed (B-015), but if
  you ever see the report disagree with the terminal, check the exit code
  rather than the output.
- Restart the server after pulling; check `/openapi.json` carries the params
  you expect before believing a UI bug.

---

## Scalability, which the brief names twice

`docs/BRIEF.md` lists "the potential scalability of the idea" as one of four
things the prototype is judged on, and the Grand Finale asks for "a
production-ready, scalable version". It used to point here at nothing. Judges
mean two different things by the word, and they are answered separately.

### Scaling across businesses

This is the one that is demonstrated rather than argued. Three industries run on
this engine: an omnichannel retailer whose metrics move because of things it did
to itself, and a fuel marketer and a generator whose metrics move because of
things done to them -- excise notifications, refinery turnarounds, port
closures, tariff orders, fuel supply, grid constraints.

What a new industry costs is the measure. It supplies five contracts, a
generated warehouse against the same six source names, and four vocabularies:
which words in an operational note name which driver, which complaint codes
corroborate which cause, what its planning extract calls a planned intervention,
and what reversing a cause recovers. It changes **no** calculation. Detection,
the price/volume/mix bridge, both ranking tracks, the causal tests, confidence,
calibration and every threshold are the contract's job in all three.

The claim is checked rather than asserted: the retail warehouse regenerates byte
for byte after the generator was parameterised -- 1.8 million order lines,
identical hashes -- and the benchmark is identical on every rate. If adding two
industries had cost the first one a single digit, that would be visible.

`tests/test_verticals.py` is what keeps it true: 60 tests parameterised over all
three, checking every pair of places that has to agree.

### Scaling with data and load

Less finished, and worth being straight about which parts are built and which
are argued.

**Built.** Every contract declares `dialect_targets: [duckdb, databricks,
snowflake]`, and the KPI is expressed as canonical SQL rather than as pandas, so
the aggregation runs in the warehouse and only the series comes back. Reading a
region-day series is a `GROUP BY` over the source, not a scan into memory.
`bridge_facts` bounds itself to the window plus its baseline instead of three
years, because aggregating the whole history to answer a question about a
fortnight was most of what a diagnosis cost. The series and decomposition cache
is keyed on a snapshot of the warehouse mtime, the contract contents and the
industry, so it drops rather than serves a stale or cross-industry answer.
Measured: p95 0.18s per diagnosis, and the whole console composes in about a
second on a cold cache.

**Argued, not built.** Concurrency is single-process; the cache is in-process
and would need to be shared or externalised behind more than one worker. The
retriever indexes the ticket corpus in memory, which is fine at seven thousand
documents and is the first thing that would need a real vector store -- the
`PgVectorRetriever` seam exists for exactly that and is unexercised. Nothing
here has been run against a warehouse large enough to test the pushdown claim,
so it rests on the SQL being SQL rather than on a measurement.

**The honest summary for a jury.** Scaling to another business is demonstrated
and costs configuration. Scaling to another two orders of magnitude of data is
designed for and not yet proven, and the specific unproven claim is that the
aggregation stays in the warehouse.

---

## Template, copy this block when you stop work

```markdown
## Status as of YYYY-MM-DD, <name>

### Done this session

### In progress (and exactly where it stopped)

### Next

### Blocked / needs a decision

### Anything the next person will trip on
```
