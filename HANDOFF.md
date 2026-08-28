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

## Template, copy this block when you stop work

```markdown
## Status as of YYYY-MM-DD, <name>

### Done this session

### In progress (and exactly where it stopped)

### Next

### Blocked / needs a decision

### Anything the next person will trip on
```
