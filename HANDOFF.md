# Handoff

**Update this whenever you stop work.** It is the first thing the next person reads after `CONTEXT.md`.

---

## Status as of 2026-08-28

**Phase:** evidence model, retrieval and contracts built. Data generation not started.

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
- 52 tests passing, 10 marked `invariant`
- Repo structure created, one package per pipeline stage
- Python 3.14.6 venv verified; full scientific stack installs cleanly (numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1)
- `MSTL`, `IsotonicRegression`, `Ridge` confirmed importable — no wheel gaps on 3.14
- Makefile, requirements, pyproject, .gitignore, .env.example
- Specs written: prototype, product outline, design checklist, security/logic checklist, concepts

### Next — in dependency order
1. **`datagen/`** — generator with planted causes, **correlation traps**, and
   held-out labels. Must emit 150+ labelled cases, not only the demo scenarios,
   or calibration has nothing to fit against later
2. **`whychain/ingest/`** — reconciliation and the freshness scorecard
3. **`whychain/detect/`** — MSTL then robust z on the residual
4. Then decompose → rank → verify, at which point `bench/` produces real numbers

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
