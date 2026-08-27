# Handoff

**Update this whenever you stop work.** It is the first thing the next person reads after `CONTEXT.md`.

---

## Status as of 2026-08-28

**Phase:** scaffolding complete — engine implementation not started.

### Done
- Repo structure created, one package per pipeline stage
- Python 3.14.6 venv verified; full scientific stack installs cleanly (numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1)
- `MSTL`, `IsotonicRegression`, `Ridge` confirmed importable — no wheel gaps on 3.14
- Makefile, requirements, pyproject, .gitignore, .env.example
- Specs written: prototype, product outline, design checklist, security/logic checklist, concepts

### Next — in dependency order
1. **`whychain/evidence/`** — the `Evidence` and `Provenance` types. **Freeze this first and do not renegotiate it**; every other stage depends on the shape
2. **`whychain/contracts/`** — contract loader + validation; one real contract in `contracts/net_revenue.yml`
3. **`datagen/`** — generator with planted causes, correlation traps, and held-out labels. Must emit 150+ labelled cases, not just the demo scenarios
4. **`whychain/ingest/`** — reconciliation + freshness scorecard
5. **`whychain/detect/`** — MSTL + robust z
6. Then decompose → rank → verify, at which point `bench/` can produce real numbers

### Blocked / undecided
- Nothing blocked.
- Open question: embedding model for corroboration retrieval. Brute-force cosine over a few thousand documents is fine at demo scale; decide when reaching stage 7.

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
