# Bugs & traps

Two sections. **Traps** are failure modes identified in advance, read before writing the relevant stage, so they are never made. **Defects** are bugs actually found, with root cause, so they are not remade.

---

## Traps, known in advance, do not walk into these

| # | Trap | Where | Correct behaviour |
|---|---|---|---|
| T-01 | Asserting `model_calls <= 2` | telemetry test | Assert `== 2`. `<=` passes silently when a call fails, defeating the check we invite judges to make |
| T-02 | Percentage vs percentage point | narrate, validate | 10% → 15% is **+5 percentage points**, not "+5%" and not "+50%". Validator must treat these as different claims |
| T-03 | Method and unit disagreeing | evidence | A price/volume/mix bridge produces **currency**, never order counts. Assert unit compatibility per method |
| T-04 | Engine reading ground truth | datagen, bench | No import path from `whychain/` to `data/ground_truth/`. Enforced by `test_no_label_leakage` |
| T-05 | `CANNOT_VERIFY` collapsed into `REJECTED` | verify | Distinct states, see D-006. Corrupts abstention metrics if merged |
| T-06 | Cache key omitting entitlement | any caching | Key must include entitlement context, contract version and data snapshot. A cross-permission cache hit is a P0 |
| T-07 | Contributions that align but don't reconcile | decompose, UI | Dimensional contributions must sum to the same total as the bridge. Alignment is cosmetic; reconciliation is the claim |
| T-08 | Retrieved text treated as instruction | corroborate | Support tickets are untrusted third-party input. A ticket saying "ignore previous instructions" must change nothing |
| T-09 | Freshness rendered as a percentage | UI, confidence | Freshness is a timestamp, a lag and an SLA verdict, not `97%` |
| T-10 | Prompt instructions used as access control | narrate | Entitlement filtering happens at projection, before assembly. Never "please don't mention region X" |
| T-11 | Placebo failure overridden by other passes | verify | A failed placebo is fatal regardless of what else passed |
| T-12 | Rejected candidate silently re-promoted | rank, narrate | Once rejected, a candidate cannot reappear as a verified cause later in the same run |
| T-13 | Tuning on the held-out set | bench | Calibration is fitted on a held-out split and never re-fitted after seeing test results |
| T-14 | Fixing a failure by weakening its test | everywhere | If a test fails, fix the code or record the limitation. Never relax the assertion |
| T-15 | Naive datetimes in freshness arithmetic | ingest, evidence | All timestamps are timezone-aware UTC. `Freshness` rejects naive input, and ruff `DTZ` enforces it at the source. Sources sit in different zones; a naive/aware mix raises mid-diagnosis |
| T-16 | Writing a version, path or command from memory | everywhere | Read it from the environment. Pins come from `pip freeze`, not recollection, see B-001 |
| T-17 | A verification command that passes on empty output | scripts, CI | `cmd \| tail && echo OK` reports success when `cmd` never ran. Check the exit status of the command itself, and confirm the check can actually fail |
| T-19 | A threshold or conversion that ignores the metric's grain | contracts | `value_per_unit_inr` must be what one unit is worth *at the grain anomalies are detected on*, and `min_abs_delta_inr` is compared per observation. A daily figure applied to hourly data is twenty-four times wrong, and a national figure applied to regional detection is wrong by the number of regions. Check that the floor is reachable given the metric's range: conversion runs at 6%, so a floor needing 11.9 points can never be met (see B-017) |
| T-18 | A benchmark result that improved for a reason nobody checked | bench, datagen | Numbers that move the flattering way get accepted; numbers that move the other way get investigated. A harness defect usually shows up as the former. Any invariant the generator depends on is executed by a test, never only stated in a docstring (see B-014) |

---

## Defects

### B-017 · Rupee conversions costed at the wrong grain, four times over
**Found:** 2026-08-29 · **Severity:** P1 · **Status:** fixed

**Symptom:** the triage queue, which ranks findings across metrics by rupee
impact, was topped entirely by movements the engine cannot diagnose. Then, after
a first correction, entirely by `checkout_conversion`. Then `checkout_conversion`
could not be material at all.

**Root cause:** `value_per_unit_inr` says what one whole unit of a metric is
worth, and it has to be worth that *at the grain anomalies are detected on*.
Four contracts got that wrong in three different ways:

- `aov` was costed at the national daily order count while detection runs per
  region: a threefold overstatement.
- `checkout_conversion` was costed against a whole day's sessions while its
  grain is hourly: a twenty-fourfold overstatement, which flooded the ranking.
- `on_time_delivery` was costed at 450,000, which made a twenty-five point fall
  worth 61% of a region-day. Late delivery costs cancellations, credits and
  retention, not most of the day's revenue.
- `min_abs_delta_inr` is compared per observation, and `checkout_conversion`
  inherited the daily KPIs' 15,000. Conversion runs at about 6%, so 15,000
  demanded a fall of 11.9 points. The ceiling of what the metric can physically
  do sat below the floor of what counts, and nothing could ever be material.

**Why it stayed hidden:** nothing consumed these numbers comparatively.
Materiality uses each contract's conversion only against its own threshold, so
an error in one never contradicted another. The triage queue is the first thing
to rank metrics against each other in a shared unit, and it exposed all four
within minutes of existing.

**Fix:** every conversion re-derived from the generated panel at the grain its
contract declares, and each now carries the derivation as a comment, because a
number that ranks the whole queue should not be unexplained. The hourly floor is
a daily floor divided across a day's hours.

**Lesson — promoted to a trap below (T-19).**

**Regression test:** none directly. The honest note is that this needs one: an
assertion that each contract's floor is reachable given the metric's plausible
range, and that a realistic movement of each converts to a comparable share of a
region-day. Recorded in `HANDOFF.md`.

### B-016 · Abstention recall measured a quantity nobody wanted
**Found:** 2026-08-28 · **Severity:** P2 · **Status:** fixed

**Symptom:** the benchmark reported abstention recall of 20.9% and the engine
was written up as under-abstaining, "preferring no material movement to
unknown". It was not. It abstained on 16 of the 17 cases that called for it.

**Root cause:** the denominator was every case where the true cause was not
found. That set is dominated by cases the engine handled *correctly*: 71
sub-threshold movements reported as "no material movement" and 16 noise cases
reported as nothing at all. Neither is an abstention the engine failed to make.
87 correct silences sat in the denominator of a metric about missed
abstentions.

**Why it was defensible when written and wrong now:** the population had no
labelled unanswerable cases, so "the true cause was not found" was the only
proxy available. Adding those cases gave the metric a real denominator and made
the proxy obsolete in the same change. The proxy was not re-examined.

**Fix:** the denominator is the cases whose *correct answer is abstention*
(`expected in {unknown, cannot_verify}`). A companion count,
`missed_abstentions`, reports the cases that needed one and did not get one,
because a rate near 1.0 hides the individual failures that matter.

**Effect on published numbers:** abstention recall 20.9% to 94.1%, one missed
abstention out of seventeen.

**This is not T-14.** T-14 is weakening an assertion so failing code passes.
Here the code was correct and the measurement was of the wrong quantity; the
figure moved because the metric started measuring what its own label claimed.
The old number and the reason are recorded above so the change can be audited
rather than taken on trust.

**Regression test:** the metric is asserted end to end by the benchmark itself;
`tests/test_bulk.py::test_the_population_can_score_abstention` guarantees the
denominator is never empty again.

### B-015 · `make bench` reported numbers it never wrote
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** the benchmark printed a full report, exited, and left
`bench/report.json` holding the *previous* run's numbers. Any document written
from the file disagreed with the run that produced it, and the terminal output
looked correct throughout.

**Root cause:** comparisons on pandas and numpy values return `np.bool_`, which
`json.dumps` refuses. The write raised after `print_report` had already run. The
exit code was non-zero, but every invocation was piped through `tail`, so the
shell reported `tail`'s status instead and the failure was invisible.

**Fix:** a `default=` hook that coerces numpy scalars on the way out.

**Lesson:** two failures stacked. A serialisation bug is ordinary; a pipeline
that hides the exit code is what turned it into published numbers that were
never computed. This is T-17 in a second form, and the reason the benchmark
figures in every document were re-derived from a clean run rather than trusted.

**Regression test:** `tests/test_bench_report.py`, which covers the numpy
scalar types that arise from pandas comparisons and asserts that a type the
hook cannot convert raises rather than being dropped from the report.

### B-014 · Benchmark cases contaminated each other's baselines
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** none visible. The benchmark ran clean, produced plausible numbers,
and reported 46.4% top-1 with a perfect rate conditional on materiality.

**Root cause:** `datagen/bulk.py` spaced events across a 560-day panel, which
worked out to 109 days between them, then applied a jitter capped at
`spacing - 20` that could close the gap to 20 days. Verification looks back
`LOOKBACK_DAYS = 110` for its baseline and its six placebo windows, so
neighbouring cases sat inside each other's control periods. Each was partly a
measurement of the other. The module docstring had asserted this must never
happen since the file was written; nothing checked it.

**Why it went unnoticed:** contamination did not make the harness fail, it made
it *flatter*. A neighbouring event in the control window depresses the
counterfactual, so the measured effect of the case under test looks cleaner
than it is. The result was numbers that were too good, which is the direction
nobody investigates.

**Fix:** `PANEL_DAYS` raised to 700 so the spacing exceeds the clearance, the
jitter cap derived from `LOOKBACK_DAYS + max(EVENT_LENGTH)` rather than a
literal, and `_slots` raises rather than returning a contaminated layout.

**Effect on published numbers:** top-1 46.4% -> 36.6%, conditional 100% -> 75.4%,
trap rejection 94.3% -> 86.7%, ECE 0.054 -> 0.103. Every document carrying the
old figures was corrected rather than left to stand.

**Lesson:** an invariant stated in a docstring is a comment. This one had been
written down, believed, and never executed. Promoted to a trap below (T-18).

**Regression test:** `tests/test_bulk.py::TestThePopulationIsBalanced::test_events_do_not_contaminate_each_others_baselines`.

### B-011 · Signal gap assessed against the window rather than the cause
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** a diagnosis whose only verified cause was an internal release
regression reported `gap_found`, citing nine public severe-weather warnings with
up to 67 hours of lead time.

**Root cause:** `find_gap` read every signal overlapping the anomaly window and
never asked whether the cause was the kind of thing an external body warns
about. Weather warnings are in the feed most weeks of the monsoon, so the
coincidence is near-certain rather than rare.

**Why it matters more than an ordinary false positive:** the output is
*well-evidenced*. Every fact in it is true; the warning was published, it was
public, the lead time was real, and the conclusion drawn from them is false.
That is harder to catch by reading the output than an obviously wrong number.

**Fix:** `find_gap` takes the verified causes. Causes that match an internal
marker consult no external feed at all; otherwise the relevant signal type is
selected from the cause's own description using the vocabulary `whychain.actions`
already uses to route drivers, so the two stages cannot disagree about what kind
of thing a cause is.

**Regression test:** `tests/test_signalgap.py::TestScopedToTheCause`.

### B-012 · Feedback counted every entry twice
**Found:** 2026-08-28 · **Severity:** P2 · **Status:** fixed

**Symptom:** three submissions from two people reported a total of four, and a
proposal reached quorum on one person's opinion.

**Root cause:** `FeedbackStore.record` appended to the file first, then called
`_all()`, which lazily read the file, including the line just written, and
then appended the in-memory object on top of it.

**Fix:** warm the cache before writing.

**Lesson:** a lazy cache and a side-effecting write in the same method need an
explicit order, and the order is not obvious from either line on its own. Worth
noticing that the inflated number was the one the quorum rule reads.

**Regression test:** `tests/test_rank_feedback.py::TestFeedbackIsBounded::test_recording_is_append_only_and_counts_once`.

### B-013 · Persona projection dropped the finding it was projecting
**Found:** 2026-08-28 · **Severity:** P1 · **Status:** fixed

**Symptom:** the CFO and ops views rendered no decision card and no Answer 2.

**Root cause:** `project` builds a fresh dict per persona rather than filtering
the analyst result, so any key not explicitly carried is silently absent.
`decisions`, `signal_gap` and `narrative` were never added when those stages
landed.

**Fix:** carry all three to every reader. Answer 2 is not method detail; it is
the finding a decision-maker is being asked to act on, and withholding it from
them while showing it to the analyst inverts who the product is for.

**Lesson:** a projection that whitelists keys fails *silently* when the source
grows. The `withheld` list on each persona should be the only thing that removes
information, and it should be tested against the analyst result's key set.

**Regression test:** covered by the API contract tests; the deeper fix, an
assertion that every analyst key is either projected or explicitly withheld, is
recorded in `HANDOFF.md` as work not yet done.

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

**Lesson, promoted to a trap below (T-16).**

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
validates the graph, neither executes the SQL.

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

**Fix:** emit hourly session counts, 416k rows for the same information.

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

### Template

```markdown
### B-001 · <one-line summary>
**Found:** YYYY-MM-DD · **Severity:** P0/P1/P2/P3 · **Status:** open / fixed

**Symptom:**
**Root cause:**
**Fix:**
**Regression test:**
**Lesson (if it generalises, promote to a Trap above):**
```
