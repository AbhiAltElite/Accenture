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
- 30 tests, 6 marked `invariant`
- GitHub Actions CI: lint, tests on Python 3.12 and 3.14, invariants as a
  separate check, and a job that fails the build on AI attribution in history
- Pull request template
- Repository scaffolding: one package per pipeline stage, Makefile, pinned requirements, `.env.example`
- Specifications: prototype design, product outline, design checklist, security & logic checklist, concepts reference
- Collaboration docs: context, handoff, decisions, bugs & traps, contributing

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
