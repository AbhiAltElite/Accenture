# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

## [Unreleased]

### Added
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
- 141 tests, 39 marked `invariant`
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
