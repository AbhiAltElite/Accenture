# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

## [Unreleased]

### Added, the stages the handoff listed as empty

- **`whychain/signalgap/`, Answer 2.** Reads `ext_signals` against the
  contract's `signals_consumed`, gated on public availability, actionable
  severity and lead time. All four verdicts are reachable from the generated
  warehouse: `gap_found`, `no_gap`, `not_foreseeable`, `coverage_unknown`.
  Recurrence is counted as episodes rather than rows, so a five-day cyclone is
  one precedent
- **`whychain/rank/`, two tracks that are never merged.** Track A is exact
  from the price/volume/mix identity and its rows are stateable; track B is a
  standardised ridge over the driver series and every row is `HYPOTHESIS`,
  labelled `CORRELATIONAL`, and barred from becoming a cause. Rejected
  candidates cannot re-enter through it (T-12)
- **`whychain/narrate/`, brief, writer, validator.** A constrained
  `claude-opus-5` call and a deterministic template implement one protocol and
  pass through one validator: binding, numerals, entities, rejected-as-cause.
  Rejected sentences are dropped and counted, never repaired; a failed call
  falls back to the template and the receipt says so
- **`whychain/feedback/`, a bounded learning loop.** Corrections never edit a
  run and never move a computed value. They propose changes to business-owned
  inputs, require two independent submitters, and go contested rather than
  averaged when readers disagree. Named misses become labelled regression cases
- **`on_time_delivery` registers the S&OP document**, which is what makes the
  flagship gap case resolve rather than returning `coverage_unknown`
- **`emit_ext_signals` emits scenario-declared warnings**, so `not_foreseeable`
  is producible from the feed rather than only from a fixture; a verdict the
  data can never reach is a verdict the demo does not have

### Fixed, correctness

- **The hourly KPI was detected on a daily seasonal cycle.** `decompose`
  defaulted to `periods=(7,)`, which means "day of week" on the four daily
  contracts and "seven hours" on `checkout_conversion`, a cycle nothing has.
  Periods now come from `SEASONAL_PERIODS[contract.grain.time]` and the
  minimum-history guard is four cycles in the series' own units, not sixty rows
  (B-018)
- **A rate was judged at one volume across a twentyfold swing in volume.** A
  single MAD scale held a conversion read off 49 midnight sessions to the spread
  of one read off 925 evening sessions. The scale is now per observation — the
  standard error of the rate, binomial for a proportion and `1/sqrt(n)` for an
  average — normalised so the median observation keeps the scale the MAD already
  fitted, so the calibration is corrected rather than loosened. Together with
  the period fix this took West `checkout_conversion` from 1,393 flags at
  z >= 3 to 62, a rate of 0.30% against a nominal 0.27%, without moving the
  benchmark by a digit (B-018)
- **An empty hour was a guaranteed anomaly.** Flooring a zero rate to take its
  logarithm flagged all 226 hours in which West took no conversions, though at
  4.3% over ~50 sessions an empty hour happens about one time in nine. A
  half-count correction gives it a finite logarithm without moving a populated
  one; 226 flags became 1
- **The rate charts were quantised to two decimal places.** `/api/series`
  rounded rupees and ratios alike, so three months of hourly conversion reached
  the browser as seven distinct levels between 0.01 and 0.07 and the lower band
  sat flat on zero. Precision comes off the contract's unit; the same window now
  arrives as 56 distinct levels across 57 points (B-018)
- **`decompose_for(series, contract)` is the entry point.** Grain, denominator
  and noise model are read off the contract rather than passed by hand, because
  the defect above was every caller taking a default that was right for the
  metric they had in mind
- **The signal gap is scoped to the verified cause, not to the window.** Weather
  warnings are in the feed most weeks of the monsoon, so assessing the window
  alone reported a gap on an internal release regression: a real warning, real
  lead time, and no relationship to what happened. Superficially the
  best-evidenced output this stage can produce, and entirely false
- **The persona projection dropped `decisions`, `signal_gap` and `narrative`**,
  so the CFO, the reader for whom "the warning existed and no function owns
  it" *is* the finding, saw neither Answer 2 nor the decision they were being
  asked to back
- **`FeedbackStore.record` counted every entry twice.** It wrote to disk before
  warming its cache, so the reload picked up the new line and the append added
  it again, inflating precisely the number the quorum rule depends on
- **Track A was sorted backwards.** Slices that moved *against* the total headed
  the list of reasons the metric fell
- **The scoping dimension is excluded from Track A.** With a region selected,
  `region = West` was the top contributor at a 100% share: true, useless, and
  displacing a real contributor out of the list
- **The narrative validator rejected its own correct output.** ISO dates parsed
  as numerals and `4.05` quoted from inside a cited claim read as a fabricated
  figure. A validator with false positives is one somebody switches off

### Fixed, benchmark

- **Planted effects now clear regional materiality.** The old table planted
  10–40% moves on slices worth 6–20% of a region, landing at 1–5% of regional
  revenue, below the materiality floor by construction, so 152 of 160 cases
  produced nothing to explain and top-1 read 2.9%. The benchmark was measuring
  a generator bug. Each profile now plants on a slice wide enough that an
  incident-sized effect is worth reporting, with the arithmetic recorded beside
  the table. **Top-1 2.9% → 46.4%**, and of the 64 cases that clear materiality
  the true cause is ranked first in 100%. The floor itself was not touched
  (T-14)

### Changed, interface

- **Complete console overhaul.** A masthead carrying the live run context, a
  rail, a document column and a margin for run metadata and cost. Report
  sections are numbered so the page has a spine. The overview is a watchlist
  table with shared right edges rather than a stack of tiles. Answer 2 renders
  all four verdicts with the reached one marked, so a reader can see the engine
  chose. States are words with a hairline, not coloured discs


### Fixed, correctness

- **Every diagnosis endpoint now executes the KPI contract it was asked for.**
  `/api/diagnose`, `/api/decomposition` and `/api/candidates` resolved the
  contract only to reject an unknown name, then read `_panel`, the generator's
  own working frame, which carries revenue. A decomposition labelled
  `checkout_conversion` was arithmetic over revenue. `Warehouse.bridge_facts`
  reads each contract's own source with its own transforms, and `_panel` is no
  longer readable through `Warehouse.table` at all
- **The price/volume/mix bridge is declared per contract rather than assumed.**
  It is an identity over priced units, so it applies to `net_revenue` and to
  nothing else currently modelled. The four other KPIs decline with a reason
  instead of returning a price effect on a percentage (T-03 in a second form)
- **Ratios roll up as ratio-of-sums, not mean-of-means.** `aov`,
  `checkout_conversion` and `on_time_delivery` declared `aggregation: mean`, so
  a slice with three orders weighed as much as one with thirty thousand. On AOV
  this understated the daily figure by 4.6% on average and 17.1% at worst. A
  contract validator now rejects a ratio metric that declares `mean`
- **Verification requires every mandatory gate, not only difference-in-differences.**
  `event_time_isolation` and `placebo` were computed, reported, and then ignored
  when deciding `VERIFIED`, so a candidate could be verified with its placebo
  never run. SECURITY-LOGIC-CHECKLIST §1.1 specified all three
- **`/api/candidates` applies `region`.** It accepted the parameter and dropped
  it. It now filters which candidates are reported while still testing them
  against the full panel, because difference-in-differences needs the unexposed
  regions as a comparison group
- **The retriever cache key is content-addressed.** It was the ticket row count:
  a key that collides whenever one document replaces another and carries no
  entitlement context, which is precisely the cache key T-06 warns is a P0
- **Entitlement SQL is parameterised** and `Warehouse.table` takes an allowlist
- **`ext_signals` exists.** All three contracts declared a `severe_weather`
  driver sourced from it and a 36h SLA, and `source_freshness` reported a row
  for it, but the generator never emitted the table, B-003 recurring
- **The chart names its points by grain.** Hourly checkout conversion reported
  "1,729 days", overstating the history twenty-four-fold

### Added

- `whychain/telemetry/`, per-stage latency, method class, model calls, tokens
  and cost, rendered as a run receipt. It reports the model-call count it
  observed rather than asserting one: with no narrate stage yet that count is
  zero, and the receipt says the narrative came from a deterministic template
- `whychain/actions/`, decision cards carrying the brief's chain: driver, lever,
  action, expected impact, owner, confidence, monitoring rule. Impact is a
  declared share of the movement the causal test already measured, never an
  estimate. Causes with no controllable lever return `controllable: false` with
  no action and no recovery figure, which is what weather does
- Approval drafts. Nothing executes; a card produces a request for a named human
- `ext_signals`, public weather warnings per city with issue time, validity,
  severity, lead time and publisher: the fields foreseeability is decided on.
  Generated, and every row says so in `source`

### Changed

- A diagnosis takes 449ms rather than 2,317ms. Scans are bounded to the history
  a diagnosis actually reads instead of the whole table, and the document corpus
  is no longer rebuilt per candidate through `iterrows` to look up twelve rows
- Interface: IBM Plex throughout, one superfamily rather than two chosen fonts;
  a 17px base with the headline brought down from 40px; larger navigation and
  controls; a second accent so a clickable claim and a verified one are no
  longer the same colour. An hourly series opens on a readable window instead of
  drawing two points per pixel
- `whychain/evidence/`, `Evidence`, `Provenance`, `Freshness`, `EvidenceStore`.
  Append-only store, immutable records, unit/method agreement enforced at
  construction, acyclicity check on the support graph
- `whychain/corroborate/`, `Retriever` protocol with `NumpyRetriever` (default)
  and `PgVectorRetriever`; offline deterministic `TfidfSvdEmbedder`; sentence-level
  span citation
- `whychain/contracts/`, contract model and registry. Cross-contract validation
  covers KPI graph consistency, cycles, duplicate ids, missing freshness SLAs and
  unowned controllable levers
- `contracts/*.yml`, all five KPIs: net revenue, orders, AOV, checkout conversion
  (hourly, digital only), on-time delivery (T+1, no SOP registered)
- `data/docs/sop/`, the demand planning SOP that Answer 2 reads
- `datagen/`, retail calendar with real festival dates, catalog with real city
  coordinates, scenario and planted-event types, six demo cases
- `whychain/decompose/`, price/volume/mix bridge and dimensional contribution,
  both reconciling exactly and refusing to report if they do not
- `/api/decomposition`; console sections for the bridge and contributions
- `whychain/verify/`, event-time isolation, difference-in-differences,
  exposure consistency and placebo, with `CANNOT_VERIFY` held distinct from
  `REJECTED`. Candidates are read from the operational record with nothing
  marking which are real
- `/api/candidates`; console section showing verified, rejected and untestable
  candidates with the outcome of every test
- `whychain/corroborate/quarantine.py`, the boundary for untrusted text:
  fence neutralisation, control-character stripping, truncation, and detection
  of eleven classes of instruction injection
- `whychain/corroborate/extract.py`, structured extraction with span citations,
  behind a protocol so a model-based extractor drops in
- `whychain/corroborate/pipeline.py`, retrieval and extraction per candidate
- Placebo is now a distribution over six quiet windows rather than one
- `whychain/confidence/`, deterministic score over coverage, causal strength,
  corroboration and freshness, with contradiction detection and structured
  abstention. Not presented as a probability until there are held-out cases to
  calibrate against
- `/api/diagnose` ties the pipeline together and returns either a diagnosis or
  an abstention, never both
- `datagen/bulk.py`, 160 labelled cases across ten independently generated
  panels, spaced so their lookback windows do not contaminate each other
- `bench/run.py` and `make bench`, top-1 and top-k accuracy, false alarm rate,
  negative-control rejection, abstention precision and recall, calibration
  buckets with ECE, and latency
- Interface: sentence case throughout, warmer palette, tabbed panels so the
  answer is visible without scrolling past the working
- `tests/test_dependencies.py`, asserts every third-party import is pinned
- 142 tests, 40 marked `invariant`

### Fixed
- `holidays` was imported by the calendar modules but missing from
  `requirements.txt`, so CI failed on a clean runner while everything passed
  locally (B-007)
- GitHub Actions CI: lint, tests on Python 3.12 and 3.14, invariants as a
  separate check, and a job that fails the build on AI attribution in history
- Pull request template
- Repository scaffolding: one package per pipeline stage, Makefile, pinned requirements, `.env.example`
- Specifications: prototype design, product outline, design checklist, security & logic checklist, concepts reference
- Collaboration docs: context, handoff, decisions, bugs & traps, contributing

- `scripts/audit.py` / `make audit`, 30 executable checks across security,
  logic and design. Each one runs something rather than reading the code
- `sessions` and `shipments` sources; all five KPIs now compute
- Materiality converts to business impact via `value_per_unit_inr`

### Verified
- Full scientific stack installs on Python 3.14.6, numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1
- `MSTL`, `IsotonicRegression` and `Ridge` importable; no wheel gaps on 3.14

### Decided
- DuckDB replaces Postgres + pgvector; no external service required (D-002)
- Two-track hypothesis ranking; GBM and SHAP dropped (D-003)

### Fixed
- Three dependency pins were wrong (`pytest-cov`, `ruff`, `uvicorn`), written
  from memory rather than from the working environment, which would have broken
  `make setup` on a teammate's machine. Now taken from `pip freeze` and verified
  by a clean install in a throwaway venv

### Changed
- D-002 revised: retrieval is pluggable rather than DuckDB-only. The original
  entry's justification was partly wrong and is corrected in place
