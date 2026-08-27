# Decisions

Architectural decisions and **why**, so they are not re-litigated. Read before proposing a structural change.

Format: one entry per decision. Never delete an entry — supersede it with a new one and mark the old `Superseded by D-0NN`.

---

### D-001 · Deterministic quantitative layer; LLM confined to two calls
**Status:** accepted · 2026-08-28

The model reads unstructured text (call 1) and writes the narrative (call 2). It never computes a number, decides a causal status, sets a confidence, names an owner, or makes an authorisation decision.

**Why:** it is the product's core claim and the brief's explicit instruction. It also makes output auditable and reproducible, and keeps cost per diagnosis metered and small.

**Consequence:** any feature requiring the model to calculate is rejected by default. SOP parsing runs offline at contract registration so the per-diagnosis count stays exactly two.

---

### D-002 · DuckDB for everything; no Postgres, no pgvector, no Docker
**Status:** accepted · 2026-08-28 · *supersedes the Postgres+pgvector design in the original spec*

**Why:** pgvector was not installed and would need building; Docker is unavailable on the dev machine. At demo corpus size (a few thousand documents) brute-force cosine similarity in numpy is instant, and DuckDB is embedded.

**Consequence:** `git clone && make setup && make demo` works with no external service. That claim is load-bearing for the demo, and a service dependency failing 20 minutes before a pitch is an avoidable risk. Revisit only if the corpus exceeds ~100k documents.

---

### D-003 · No GBM, no SHAP; two-track hypothesis ranking
**Status:** accepted · 2026-08-28

Track A ranks internal structural drivers from the exact price/volume/mix bridge. Track B ranks external and operational drivers via regularised linear regression (ridge/lasso) with lag alignment, coefficients read directly.

**Why:** the bridge is an identity that sums exactly, which is a stronger basis than a model estimate. SHAP explains the model, not reality, and a SHAP waterfall is what every competing submission will show. Dropping GBM also removes training and feature-engineering work.

**Rejected alternative:** cutting the model layer entirely. The brief names marketing, supply and competition as drivers, and none is derivable from the bridge — removing track B would lose three of the eight named driver types.

---

### D-004 · Synthetic dataset with real external feeds
**Status:** accepted · 2026-08-28

Indian retail/CPG spine is generated; weather (Open-Meteo) and the festival calendar are real.

**Why:** no public dataset carries both the true cause of each movement and a record of which signals were available at the time. The second is required for Answer 2 to be measurable at all.

**Guards, all four required:** ground-truth labels held out and unreadable by the engine (enforced by test); noise-only cases included and the over-explanation rate reported; real external feeds; one documented run on an unseen public CSV.

---

### D-005 · `signals_consumed` is derived, never hand-written
**Status:** accepted · 2026-08-28

Extracted at contract registration from a real SOP document, stored with character spans back to the source.

**Why:** if we type the field, the fatal objection is "you declared the gap you then discovered." Deriving it from a **published third-party S&OP process description** — which documents itself as consuming historical sales, inventory, capacity and financials, and conspicuously no external risk signal — means the gap is found in a document nobody on the team wrote.

**Consequence:** where no SOP exists, report `coverage: unknown`. Never assert a gap from absence of evidence.

---

### D-006 · Verification gates: unavailable ≠ failed
**Status:** accepted · 2026-08-28

`CANNOT_VERIFY` (no comparison group, insufficient history) and `REJECTED` (test ran and failed) are distinct terminal states.

**Why:** collapsing them causes the engine to reject candidates it should abstain on, which corrupts abstention precision/recall and the calibration curve — two of the metrics we publish.

---

### D-007 · Hand-rolled front end, not Streamlit
**Status:** accepted · 2026-08-28

**Why:** click-to-evidence is the product's signature interaction and the moment judges remember. Streamlit is the median submission's signature and its expander widget is instantly recognisable. Cost is roughly a day and a half; accepted.
