# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

## [Unreleased]

### Fixed — correctness

- **Every diagnosis endpoint now executes the KPI contract it was asked for.**
  `/api/diagnose`, `/api/decomposition` and `/api/candidates` resolved the
  contract only to reject an unknown name, then read `_panel` — the generator's
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
  for it, but the generator never emitted the table — B-003 recurring
- **The chart names its points by grain.** Hourly checkout conversion reported
  "1,729 days", overstating the history twenty-four-fold

### Added

- `whychain/telemetry/` — per-stage latency, method class, model calls, tokens
  and cost, rendered as a run receipt. It reports the model-call count it
  observed rather than asserting one: with no narrate stage yet that count is
  zero, and the receipt says the narrative came from a deterministic template
- `whychain/actions/` — decision cards carrying the brief's chain: driver, lever,
  action, expected impact, owner, confidence, monitoring rule. Impact is a
  declared share of the movement the causal test already measured, never an
  estimate. Causes with no controllable lever return `controllable: false` with
  no action and no recovery figure, which is what weather does
- Approval drafts. Nothing executes; a card produces a request for a named human
- `ext_signals` — public weather warnings per city with issue time, validity,
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
- `whychain/evidence/` — `Evidence`, `Provenance`, `Freshness`, `EvidenceStore`.
  Append-only store, immutable records, unit/method agreement enforced at
  construction, acyclicity check on the support graph
- `whychain/corroborate/` — `Retriever` protocol with `NumpyRetriever` (default)
  and `PgVectorRetriever`; offline deterministic `TfidfSvdEmbedder`; sentence-level
  span citation
- `whychain/contracts/` — contract model and registry. Cross-contract validation
  covers KPI graph consistency, cycles, duplicate ids, missing freshness SLAs and
  unowned controllable levers
- `contracts/*.yml` — all five KPIs: net revenue, orders, AOV, checkout conversion
  (hourly, digital only), on-time delivery (T+1, no SOP registered)
- `data/docs/sop/` — the demand planning SOP that Answer 2 reads
- `datagen/` — retail calendar with real festival dates, catalog with real city
  coordinates, scenario and planted-event types, six demo cases
- `whychain/decompose/` — price/volume/mix bridge and dimensional contribution,
  both reconciling exactly and refusing to report if they do not
- `/api/decomposition`; console sections for the bridge and contributions
- `whychain/verify/` — event-time isolation, difference-in-differences,
  exposure consistency and placebo, with `CANNOT_VERIFY` held distinct from
  `REJECTED`. Candidates are read from the operational record with nothing
  marking which are real
- `/api/candidates`; console section showing verified, rejected and untestable
  candidates with the outcome of every test
- `whychain/corroborate/quarantine.py` — the boundary for untrusted text:
  fence neutralisation, control-character stripping, truncation, and detection
  of eleven classes of instruction injection
- `whychain/corroborate/extract.py` — structured extraction with span citations,
  behind a protocol so a model-based extractor drops in
- `whychain/corroborate/pipeline.py` — retrieval and extraction per candidate
- Placebo is now a distribution over six quiet windows rather than one
- `whychain/confidence/` — deterministic score over coverage, causal strength,
  corroboration and freshness, with contradiction detection and structured
  abstention. Not presented as a probability until there are held-out cases to
  calibrate against
- `/api/diagnose` ties the pipeline together and returns either a diagnosis or
  an abstention, never both
- `datagen/bulk.py` — 160 labelled cases across ten independently generated
  panels, spaced so their lookback windows do not contaminate each other
- `bench/run.py` and `make bench` — top-1 and top-k accuracy, false alarm rate,
  negative-control rejection, abstention precision and recall, calibration
  buckets with ECE, and latency
- Interface: sentence case throughout, warmer palette, tabbed panels so the
  answer is visible without scrolling past the working
- `tests/test_dependencies.py` — asserts every third-party import is pinned
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

- `scripts/audit.py` / `make audit` — 30 executable checks across security,
  logic and design. Each one runs something rather than reading the code
- `sessions` and `shipments` sources; all five KPIs now compute
- Materiality converts to business impact via `value_per_unit_inr`

### Verified
- Full scientific stack installs on Python 3.14.6 — numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1
- `MSTL`, `IsotonicRegression` and `Ridge` importable; no wheel gaps on 3.14

### Decided
- DuckDB replaces Postgres + pgvector; no external service required (D-002)
- Two-track hypothesis ranking; GBM and SHAP dropped (D-003)

### Fixed
- Three dependency pins were wrong (`pytest-cov`, `ruff`, `uvicorn`) — written
  from memory rather than from the working environment, which would have broken
  `make setup` on a teammate's machine. Now taken from `pip freeze` and verified
  by a clean install in a throwaway venv

### Changed
- D-002 revised: retrieval is pluggable rather than DuckDB-only. The original
  entry's justification was partly wrong and is corrected in place
