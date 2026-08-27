# Handoff

**Update this whenever you stop work.** It is the first thing the next person reads after `CONTEXT.md`.

---

## Status as of 2026-08-28

**Phase:** evidence model and retrieval layer built. Detection pipeline not started.

### Done
- **`whychain/evidence/` — the spine, and it is now frozen.** `Evidence`,
  `Provenance`, `Freshness`, `EvidenceStore`. Records are immutable, the store is
  append-only, references must resolve at insert time, and unit/method agreement
  is enforced at construction so a bridge cannot report order counts
- **`whychain/corroborate/` — retrieval.** `Retriever` protocol,
  `NumpyRetriever` (default), `PgVectorRetriever`, offline `TfidfSvdEmbedder`.
  Search is windowed to the anomaly period and returns sentence-level spans, so a
  citation points at the words rather than the file
- 30 tests passing, 6 marked `invariant`
- Repo structure created, one package per pipeline stage
- Python 3.14.6 venv verified; full scientific stack installs cleanly (numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1)
- `MSTL`, `IsotonicRegression`, `Ridge` confirmed importable — no wheel gaps on 3.14
- Makefile, requirements, pyproject, .gitignore, .env.example
- Specs written: prototype, product outline, design checklist, security/logic checklist, concepts

### Next — in dependency order
1. **`whychain/contracts/`** — contract loader and validation, plus one real
   contract at `contracts/net_revenue.yml`. Everything downstream reads it
2. **`datagen/`** — generator with planted causes, **correlation traps**, and
   held-out labels. Must emit 150+ labelled cases, not only the demo scenarios,
   or calibration has nothing to fit against later
3. **`whychain/ingest/`** — reconciliation and the freshness scorecard
4. **`whychain/detect/`** — MSTL then robust z on the residual
5. Then decompose → rank → verify, at which point `bench/` produces real numbers

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
