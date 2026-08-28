# Bugs & traps

Two sections. **Traps** are failure modes identified in advance — read before writing the relevant stage, so they are never made. **Defects** are bugs actually found, with root cause, so they are not remade.

---

## Traps — known in advance, do not walk into these

| # | Trap | Where | Correct behaviour |
|---|---|---|---|
| T-01 | Asserting `model_calls <= 2` | telemetry test | Assert `== 2`. `<=` passes silently when a call fails — defeating the check we invite judges to make |
| T-02 | Percentage vs percentage point | narrate, validate | 10% → 15% is **+5 percentage points**, not "+5%" and not "+50%". Validator must treat these as different claims |
| T-03 | Method and unit disagreeing | evidence | A price/volume/mix bridge produces **currency**, never order counts. Assert unit compatibility per method |
| T-04 | Engine reading ground truth | datagen, bench | No import path from `whychain/` to `data/ground_truth/`. Enforced by `test_no_label_leakage` |
| T-05 | `CANNOT_VERIFY` collapsed into `REJECTED` | verify | Distinct states — see D-006. Corrupts abstention metrics if merged |
| T-06 | Cache key omitting entitlement | any caching | Key must include entitlement context, contract version and data snapshot. A cross-permission cache hit is a P0 |
| T-07 | Contributions that align but don't reconcile | decompose, UI | Dimensional contributions must sum to the same total as the bridge. Alignment is cosmetic; reconciliation is the claim |
| T-08 | Retrieved text treated as instruction | corroborate | Support tickets are untrusted third-party input. A ticket saying "ignore previous instructions" must change nothing |
| T-09 | Freshness rendered as a percentage | UI, confidence | Freshness is a timestamp, a lag and an SLA verdict — not `97%` |
| T-10 | Prompt instructions used as access control | narrate | Entitlement filtering happens at projection, before assembly. Never "please don't mention region X" |
| T-11 | Placebo failure overridden by other passes | verify | A failed placebo is fatal regardless of what else passed |
| T-12 | Rejected candidate silently re-promoted | rank, narrate | Once rejected, a candidate cannot reappear as a verified cause later in the same run |
| T-13 | Tuning on the held-out set | bench | Calibration is fitted on a held-out split and never re-fitted after seeing test results |
| T-14 | Fixing a failure by weakening its test | everywhere | If a test fails, fix the code or record the limitation. Never relax the assertion |
| T-15 | Naive datetimes in freshness arithmetic | ingest, evidence | All timestamps are timezone-aware UTC. `Freshness` rejects naive input, and ruff `DTZ` enforces it at the source. Sources sit in different zones; a naive/aware mix raises mid-diagnosis |
| T-16 | Writing a version, path or command from memory | everywhere | Read it from the environment. Pins come from `pip freeze`, not recollection — see B-001 |
| T-17 | A verification command that passes on empty output | scripts, CI | `cmd \| tail && echo OK` reports success when `cmd` never ran. Check the exit status of the command itself, and confirm the check can actually fail |

---

## Defects

### B-001 · Dependency pins invented rather than read from the environment
**Found:** 2026-08-28 · **Severity:** P2 · **Status:** fixed

**Symptom:** `requirements.txt` pinned `pytest-cov==8.0.0`, `ruff==0.15.5`,
`uvicorn==0.41.0`. None of those versions was what the working venv actually had.
`make setup` would have failed on a fresh machine.

**Root cause:** pins were written from memory instead of from `pip freeze`.

**Fix:** regenerated from the working environment, then verified by installing
into a throwaway venv and running the suite there.

**Regression test:** the CI matrix installs from `requirements.txt` on a clean
runner, so a bad pin now fails the build.

**Lesson — promoted to a trap below (T-16).**

### B-002 · Rupee materiality floor applied to counts and ratios
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** `orders` and `aov` reported zero material movements over three
years. A KPI that never flags anything looks calm; it is actually broken.

**Root cause:** `min_abs_delta_inr` was compared directly against the movement in
the metric's own unit. Orders is a count of roughly 1,500/day and the floor was
15,000, so no movement could ever pass. Same class of error as T-03.

**Fix:** contracts declare `value_per_unit_inr`, and materiality converts the
movement to business impact before applying the rupee test.

**Regression test:** `audit.py` asserts a count metric carries a conversion
factor and that revenue's is exactly 1.0.

### B-003 · Two contracts referenced tables the generator never emitted
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** `checkout_conversion` and `on_time_delivery` failed at query time.
Nothing caught it, because contracts validate their own shape and the registry
validates the graph — neither executes the SQL.

**Fix:** generator emits `sessions` and `shipments`. `on_time_delivery` also
declared `tz_normalise`, a transform that rewrites `order_ts`, which shipments
does not have; a contract must not claim lineage its table cannot support.

**Regression test:** `audit.py` executes every contract in the registry.

### B-004 · Sessions materialised one row per session
**Found:** 2026-08-28 · **Severity:** P2 · **Status:** fixed

**Symptom:** 30 million rows generated for a metric that only ever consumes
counts. Build time and file size for no analytical gain.

**Root cause:** modelled sessions as events out of habit. Web analytics arrives
pre-aggregated in practice.

**Fix:** emit hourly session counts — 416k rows for the same information.

### B-005 · A real cause rejected because its scope was not extracted
**Found:** 2026-08-28 · **Severity:** P2 · **Status:** resolved, differently than expected

**Symptom:** `comp-pricecut-aug` is a genuine planted cause, a competitor price
cut confined to personal care in the West. Verification rejects it on the placebo
test.

**Root cause:** candidate scope is extracted from note text by keyword match, and
the note says "personal care prices" in prose the matcher does not read. Without
`category=personal_care` the effect is measured across all of the West, where it
is swamped by the checkout regression, and the placebo window is correspondingly
noisy.

**Why it is left open:** this is precisely the work the corroboration stage does.
A model reading the note properly will extract the category, and the candidate
will be scoped correctly before it reaches verification. Tuning the placebo
threshold to let it through would hide the real problem and weaken a test that
correctly rejects the planted trap.

**Resolution:** scope extraction now shares the corroboration vocabulary, so the
note yields `category=personal_care` and the candidate is tested against personal
care alone. It is still rejected, but the reason changed and the new one is
defensible: across six quiet windows the same comparison ranges to -21.0%, and
the measured effect is -20.7%. A planted -9% on one category in one region is not
distinguishable from what the method produces on data where nothing happened.

**What this actually says:** the effect is real and too small for this method to
resolve on that slice. The benchmark should count it as a false negative and
report it. One real cause missed is a better outcome than a coincidence promoted,
and the placebo distribution is what makes the difference legible rather than a
matter of threshold taste.

### B-006 · SVD dimension bounded by corpus size instead of vocabulary
**Found:** 2026-08-28 · **Severity:** P2 · **Status:** fixed

**Symptom:** indexing seven thousand tickets raised
`n_components(128) must be <= n_features(85)`.

**Root cause:** the guard used corpus length. The constraint is on the term
matrix width, and templated tickets have far fewer distinct terms than documents.

**Fix:** fit the vectorizer first and take the dimension from the vocabulary it
found.

### B-007 · `holidays` imported but never pinned
**Found:** 2026-08-28 (by CI) · **Severity:** P1 · **Status:** fixed

**Symptom:** every test passed locally; CI failed on a clean runner.

**Root cause:** the package was installed by hand while building the festival
calendar and never added to `requirements.txt`. The local venv had it, so nothing
locally could detect the gap. This is T-16 again, in a form the earlier fix did
not cover: that one checked pins were *correct*, not that they were *complete*.

**Fix:** pinned `holidays==0.103`.

**Regression test:** `tests/test_dependencies.py` walks the AST of every module,
collects top-level imports, and asserts each third-party name is declared. It
fails the same way locally that CI would.

**Lesson:** a green local suite says nothing about a clean machine when the
local environment has drifted from the manifest.

### B-008 · Every diagnosis was computed from revenue, whatever KPI was asked for
**Found:** 2026-08-28 · **Severity:** P0 · **Status:** fixed

**Symptom:** `/api/diagnose?kpi=checkout_conversion` returned a decomposition,
causal tests and a confidence score, all correct-looking, all computed from
revenue. Every endpoint returned 200 for all five KPIs.

**Root cause:** the endpoints called `_contract(kpi)` only to 404 on an unknown
name, then read `wh.table("_panel")`. `_panel` is the generator's convenience
frame and carries `units` and `revenue`. Its own comment in `datagen/build.py`
says the engine reads the source tables instead, which is what made the call
look harmless.

**Fix:** `Warehouse.bridge_facts` reads the contract's own source through its own
declared transforms and expressions. `_panel` is off the `READABLE_TABLES`
allowlist, so the old call now raises rather than returning the wrong number.

**Regression test:** a decomposition of a non-currency KPI returns 422 with a
reason; two KPIs over one window return different values.

**Lesson:** a table kept "for inspection" beside the real ones will be read by
something. The audit executed every contract's SQL and passed throughout,
because the endpoints were not executing that SQL at all. Test the path the
product takes, not the path the design describes.

### B-009 · Ratios rolled up as the mean of slice rates
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** daily AOV read about 4.6% low on average and 17.1% low on the worst
day. Conversion and on-time delivery had the same error, unquantified.

**Root cause:** the contracts declared `aggregation: mean` with a comment saying
a ratio is averaged rather than summed. Half right: it is not summed, and it is
not averaged either. The mean of slice rates weights a device with two hundred
sessions like one with two hundred thousand.

**Fix:** `ratio_of_sums`, with the numerator and denominator declared in the
contract and emitted by its SQL, so a roll-up re-divides the summed parts.

**Regression test:** a contract whose unit is a ratio and whose aggregation is
`mean` is rejected at load.

**Lesson:** the error was in a line of prose that sounded like a correctness
note. A comment asserting the safe-looking half of a rule is worse than none.

### B-010 · A candidate could be VERIFIED with its placebo never run
**Found:** 2026-08-28 · **Severity:** P0 · **Status:** fixed

**Symptom:** `_decide` treated only `difference_in_differences` as mandatory.
Event-time isolation and placebo were computed, displayed with their outcomes,
and then not consulted. A candidate whose placebo returned UNAVAILABLE reached
VERIFIED.

**Root cause:** the mandatory set was written as a single-element literal and
never revisited as gates were added.

**Fix:** `MANDATORY_GATES` requires event-time isolation, difference-in-differences
and placebo to have actually passed. Exposure consistency stays optional: it is
only meaningful where a cause touched more than one region.

**Lesson:** this is T-11 and D-006 in the one place they both had to hold, and
the narrative was already telling readers all three tests had run. Displaying a
gate is not enforcing it.

### B-011 · Every chart figure was formatted as rupees
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** hovering the checkout conversion chart read
`observed ₹1, expected ₹1, −₹0`. On-time delivery did the same.

**Root cause:** `const money = v => STATE.overview && false ? v : inr(v)`. The
`&& false` made the branch unreachable, so every value went through the rupee
formatter regardless of the metric, and `inr` rounds to whole rupees. A rate
around 0.06 became ₹0.

**Fix:** the unit travels with the series and is used. Values render as currency,
per cent or a count according to the contract, and the difference between two
rates is reported in percentage points rather than per cent (T-02).

**Why nobody saw it:** it was not reachable. Until B-008 was fixed every endpoint
answered with revenue whatever KPI was requested, so a rate was never actually
drawn. Fixing one bug made three others visible in the same afternoon.

**Lesson:** a dead branch that silences a whole class of formatting is invisible
to tests that never exercise the other class. This is the failure
DESIGN-CHECKLIST §3 names in as many words, "freshness is not a percentage" and
its sibling, a rate reading as one rupee.

### Template

```markdown
### B-001 · <one-line summary>
**Found:** YYYY-MM-DD · **Severity:** P0/P1/P2/P3 · **Status:** open / fixed

**Symptom:**
**Root cause:**
**Fix:**
**Regression test:**
**Lesson (if it generalises — promote to a Trap above):**
```
