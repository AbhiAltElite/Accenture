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
| T-20 | An assumption that is true of one industry and taken for a property of the method | everywhere | A conversion rate below one, a numerator drawn from its denominator, a column name, a festival calendar, a weekday shape. Each was correct for retail and wrong elsewhere, and none was visible until a second industry consumed the same code. When two places have to name the same thing, a test asserts it; a comment asking someone to remember is not a mechanism (see B-019) |
| T-19 | A threshold, conversion or seasonal period that ignores the metric's grain | contracts, detect | `value_per_unit_inr` must be what one unit is worth *at the grain anomalies are detected on*, and `min_abs_delta_inr` is compared per observation. A daily figure applied to hourly data is twenty-four times wrong, and a national figure applied to regional detection is wrong by the number of regions. Check that the floor is reachable given the metric's range: conversion runs at 6%, so a floor needing 11.9 points can never be met (see B-017). The same applies to anything else measured in observations: a seasonal period of 7 means "day of week" on a daily series and "seven hours" on an hourly one, and a minimum of 60 rows is sixty days of one and two and a half days of the other (see B-018) |
| T-21 | A capability that exists at the API and is unreachable from the only client | api, UI | Not a shipped capability. Entitlement withholding is built, tested and returned by `/api/diagnose`, and no console path asks the question that produces it (B-028). Any README step describing a behaviour is re-run after a client change, or the step is removed |
| T-22 | An assertion that counts things and never checks the count is reachable | tests, scripts | `len(body["causes"])` on a response whose key is `verified` is zero forever, and every comparison against it passes (B-029). A counting assertion fails when its own baseline is zero. T-17 is the same rule for shell |
| T-26 | A contract field that is declared, documented and never read | contracts, everywhere | `calendar` sat in every contract and in the README while `_calendar()` returned `holidays.India` unconditionally (B-033). A declared field the engine ignores is worse than an absent one: it reads as configuration and behaves as decoration. Any field a contract declares is either consumed by a code path or removed, and a test asserts which |
| T-28 | An identity with an unstated precondition | decompose, contracts | The price/volume/mix bridge derives price as revenue over units, which is undefined when a key's net units are zero or negative. Our generator cannot produce such a key, so the precondition was never written down and never tested (B-037). An identity that is only an identity on some data is a conditional, and the condition belongs in the contract |
| T-27 | Assuming a business metric cannot go negative | detect, UI | Two days in a real 604-day retailer series have net revenue below zero because returns exceeded sales (B-034). A generator that never emits one hides the whole class: percentage change against a near-zero or negative baseline is meaningless, and multiplicative seasonal models are not defined there |
| T-25 | A design or docs check that greps for an exact sentence of prose | scripts/audit.py | It breaks the next time the prose improves, and it reports a copy edit as a governance failure (B-032). Assert the *claim* is present by a robust marker, or accept that the sentence is now a fixed asset and say so beside it |
| T-24 | A control offered on one endpoint's parameters and not on its neighbours' | api, UI | `/api/series` took channel and device and silently ignored category; `/api/overview` and `/api/triage` took none of them while the console sent all three. The reader changes a control and the figures do not move (B-031). A filter is applied by one helper that **raises** when a declared dimension is missing from the frame, rather than by a per-endpoint loop that skips what it cannot find |
| T-23 | Comparing two sources at different grains and calling the difference a disagreement | reconcile, api | A channel-sliced revenue series against a ledger that posts by region is a 68% "contradiction" that means only that one side was sliced. Narrow the second source by every dimension it has, and decline the comparison when the reader asked for one it does not (B-030). A false refusal costs more than a false explanation here, because refusal is what this engine asks to be trusted on |
| T-18 | A benchmark result that improved for a reason nobody checked | bench, datagen | Numbers that move the flattering way get accepted; numbers that move the other way get investigated. A harness defect usually shows up as the former. Any invariant the generator depends on is executed by a test, never only stated in a docstring (see B-014) |

---

## Defects

### B-038 · The chart key said every flagged day was a fall
**Found:** 2026-09-21, reported from a click-through · **Severity:** P2 · **Status:** fixed

**Symptom:** "a positive spike out of ordinary is flagged in red colour". The
chart's legend carried one key, `Flagged`, hardcoded to the fall colour.

**Root cause:** the chart draws a flagged day's dot in the colour of the
direction it moved, red for a fall and green for a rise. The legend described
only one of them. On `aov`, whose only two flagged days in the window are rises
of +9.3% and +8.9%, **every dot on the chart was green and the key beside it was
red**, so the key matched nothing in the picture it was explaining.

**Fix:** two keys, `Flagged fall` and `Flagged rise`, each in its own colour and
drawn as a dot rather than a line, because a dot is what the chart draws for
them while observed and expected are lines.

**The third place this surfaced, and it is now closed.** `aov` said "Nothing
moved enough to explain" above a chart plotting two flagged rises, because the
findings view filtered to `direction === "drop"` (B-027). The engine detected
rises, the chart drew them, the legend named them, and the findings list
discarded them. The legend fix made that inconsistency visible rather than
hiding it, which was the right order to fix them in; B-027 was fixed straight
after, in the same session.

### B-037 · The price/volume/mix identity has a precondition nobody wrote down
**Found:** 2026-09-21, running the deterministic layer on real rows · **Severity:** P2 · **Status:** open

**Symptom:** on a real UK retailer, 14 to 20 Dec 2010, the bridge refused:
change −781,137.97, legs summing to −780,872.57, residual −265.40 against a
tolerance of 0.10.

**Root cause:** 49 SKUs in the baseline and one in the event window have
**negative net units**, because returns exceeded sales for that product over the
period. The identity derives realised price as revenue over units, which is not
defined at zero and inverts sign below it, so the three legs stop summing
exactly. The docstring says the decomposition "is arithmetic, not estimation",
and on this data that is conditionally true rather than true.

**The important half: the guard worked.** `assert_reconciles` refused to publish
a bridge that was 265 short rather than reporting one, which is the behaviour
the design promises. Nothing false was emitted. What failed is the claim that
the identity always holds, not the engine's handling of it failing.

**Why our own data could never show this.** `datagen` composes revenue from
priced units with a returns rate far below one, so a SKU with negative net units
is outside the space it can generate. Same blind spot as B-034, one level down.

**Open decision, and it is a real one.** Either the contract declares the
precondition and the engine checks it before attempting a bridge, or the
decomposition handles negative-unit keys explicitly. A third option, widening
the tolerance, would be the wrong fix: 265 on 781,138 is 0.034%, and a tolerance
that scales with the movement would hide a genuine arithmetic failure rather
than reporting it.

**Trap:** T-28.

### B-036 · Reads re-derived the contract's lineage on every query
**Found:** 2026-09-21 by `make scale` · **Severity:** P1 · **Status:** fixed on `perf/materialise-lineage`

**Symptom:** at 16x the fact rows, a one-region read cost **26.6x** the time,
while the same aggregation with the contract's lineage transforms removed stayed
flat at 1.3x. Concurrency topped out around 1.7 requests per second. Scalability
is one of the four criteria the prototype is judged on and was the weakest.

**Root cause:** `dedupe_order_id` is a window partitioned by order id. Nothing
can be pushed below a window, so a region predicate could not narrow it and
every read re-derived the dedupe over the whole table. `_prepared()` built the
chain as a nested subquery on each call. The work was identical every time and
the warehouse does not change between generations.

**Fix:** `materialise()` computes each declared chain once and stores it in a
table whose name hashes the base table, the chain **and the SQL of each
transform in it**. `_prepared()` returns that table when it exists and otherwise
falls back to the subquery it always built.

**The fallback is the safety property, not a convenience.** A warehouse that has
never been prepared behaves exactly as before, so the absence of the build step
costs speed and nothing else. `make gen` and `make gen-all` now run it, `run.sh`
runs it, and `make prepare` is idempotent.

**Measured, same machine, same day:**

| | before | after |
|---|---|---|
| one-region read at 16x rows | 26.6x | **1.5x** |
| one-region read, 40.3M rows, absolute | 2.095s | **0.015s** |
| full diagnosis end to end | 372ms | **229ms** |

Every accuracy figure in `make bench` is unchanged to the decimal: same answers,
computed faster.

**The risk this introduced, and what holds it:** a stored table can drift from
the transforms the contract declares, and nothing would fail. The engine would
serve rows from an older definition while every contract, receipt and
`docs/REQUIREMENTS.md` kept claiming the current one. That is a lineage claim
false while still looking true, which is the shape of the old `row_filter`
defect. `tests/test_materialised_lineage.py` asserts row-for-row equivalence
with `EXCEPT ALL` in both directions, and it was verified to fail by deleting
five rows from a 1.79M-row materialised table. The transform SQL is in the hash
so a redefined transform misses rather than serving the old build, and a test
pins that too.

**Trap:** T-26 is why the equivalence test exists.

*B-033 to B-035 were all found by the same exercise: running the engine on the
UCI Online Retail II dataset, 1,067,371 real invoice lines from a UK gift
retailer, via `make real-data`. None of them was reachable from our own
warehouse, because our warehouse was built by people who already held these
assumptions. That is the argument for the exercise.*

### B-033 · Every contract declares a calendar and the engine ignores it
**Found:** 2026-09-21, first run against unseen data · **Severity:** P1 · **Status:** open

**Symptom:** a United Kingdom revenue series was detrended against Diwali,
Holi, Onam, Pongal and Eid.

**Root cause:** `_calendar()` in `whychain/detect/calendar.py` returns
`holidays.India(years=...)` unconditionally. `contract.calendar` is parsed,
stored on the model, printed in `docs/REQUIREMENTS.md` as part of the governed
semantic layer, and **read by no code path at all.**

**What this does and does not invalidate.** It does not touch any published
number: our three warehouses are Indian businesses, so an Indian festival
calendar is the right one and the benchmark stands. What it invalidates is the
*claim* that the calendar is contract-governed. It is hardcoded, and the
contract field is decoration.

**Trap:** T-26. This is the same class as the `row_filter` defect fixed earlier:
a policy declared in the contract while the engine applied its own. We caught
that one because a test exercised it. Nothing exercised this one, because every
contract we had declared the same value.

### B-034 · The engine assumes a metric cannot go negative
**Found:** 2026-09-21, same run · **Severity:** P2 · **Status:** open

**Symptom:** the detector reported a movement of **-573.2%** on 2010-04-29.

**Root cause:** that day's net revenue is **-£20,746**. Returns exceeded sales,
which happens twice in 604 real trading days. Percentage change against a
baseline the series has crossed is not meaningful, and the multiplicative
seasonal handling is not defined there either.

**Why our own data could never surface it:** `datagen` composes revenue from
priced units with a returns rate well below one, so a negative day is not in
the space it can generate. The assumption was invisible because the generator
shared it.

**Trap:** T-27.

### B-035 · The unit vocabulary has one currency in it
**Found:** 2026-09-21, same run · **Severity:** P2 · **Status:** open

**Symptom:** a contract for a UK business cannot declare its own currency. The
`Unit` enum offers `INR`, `pct`, `pct_point`, `count`, `hours`, `ratio`, `none`.

**Consequence:** pounds render with a rupee sign, and `min_abs_delta_inr` is a
currency name in a field name, so a materiality floor in another currency is
expressible only by lying about the unit. The real-data contract declares `INR`
with a comment saying the figures are pounds, which is the honest workaround
and not a fix.

**Note for the pitch:** this is a scope statement rather than a flaw. The
product is built for an Indian deployment and says so. It becomes a defect the
moment we claim the contract layer is currency-agnostic, and `docs/REQUIREMENTS.md`
comes close to that. **Trap:** T-20, again.

### B-032 · A copy edit took the audit from 33/33 to 32/33
**Found:** 2026-09-21, running `make audit` to validate a number we had been quoting · **Severity:** P2 · **Status:** fixed

**Symptom:** `32/33 checks pass`. The failure was
`design / Method and thresholds are stated, not hidden: materiality rule not
explained`, while the README and every draft of the pitch claimed 33/33.

**Root cause:** `scripts/audit.py` asserts the literal string
`"Both tests must pass"` appears in `ui/index.html`. A copy pass earlier in the
same session rewrote that paragraph to be shorter. The rule was still explained,
arguably better, but the sentence the check pins was gone.

**Fix:** the phrase is restored inside the tightened sentence, so the copy stays
short and the check stays literal. **Not** by relaxing the assertion: T-14.

**The wider lesson, and it is the reason this is written up rather than quietly
fixed.** We were quoting "33 of 33" in three documents without having run it
since the change. That is the same failure the product exists to prevent, in our
own materials. Every number in the deck is now re-measured rather than recalled,
and the measured set is in `_internal/handoff/BUSINESS-CASE.md`.

**Trap:** T-25.

### B-031 · Two of the four scope filters did nothing, and on the landing page none of them did
**Found:** 2026-09-21, reported from a click-through · **Severity:** P1 · **Status:** fixed

**Symptom:** "the channel and category does nothing". Correct, and worse than
reported. Measured: `/api/series` for the West returned an identical series with
and without `category=beverages`, and on the overview page neither channel,
category nor device changed a single figure.

**Root cause, three separate ones behind one symptom.**

`/api/series` filtered with `for column, value in (("region", region),
("channel", channel), ("device", device)): if value and column in raw.columns`.
Category was never in the tuple, so the parameter did not exist and the request
was accepted anyway. The `column in raw.columns` guard is the other half of the
fault: a dimension the frame does not carry is skipped silently, which is the
same silence by a different route.

`/api/overview` and `/api/triage` never took the parameters at all. The console
sent them, FastAPI ignored what it had no signature for, and the landing page
answered the unsliced question under a rail that said otherwise.

Both of those were mine, added in the same session as the filters. The console
was wired to a slice that only one of three endpoints honoured.

**Why it matters more than a missing feature.** The file already carried the
argument, written for the Period control: *"a control that visibly does nothing
teaches a reader that none of them mean anything."* Having made that argument,
we shipped three of them.

**Fix:** one `_narrow(frame, sliced)` helper, used by every endpoint that reads
figures, which **raises** when a contract declares a dimension the frame does not
carry rather than skipping it. `_slice_of` already refused a dimension outside
the contract's grain; this closes the other end. Overview and triage take the
three parameters, and the slice is now part of the decompose cache key on both,
without which a channel series and a national one would share an entry (T-06).

**Second fault found while fixing it:** `/api/triage` wrote
`["North", "South", "East", "West"]` when no entitlement was set, which is
retail's answer serving three verticals. T-20, again. It now reads the region
list from the warehouse.

**Honesty that came out of it.** A filter cannot reach every metric:
`checkout_conversion` is measured by region and device and has no channel, so a
channel filter leaves its count exactly where it was. The overview response now
carries `not_narrowed` per metric and the table prints "no channel" under the
count, because an unexplained still number is indistinguishable from a broken
control.

**Trap:** T-24.

### B-030 · Slicing by channel turned every finding into a contradiction
**Found:** 2026-09-21 (while adding the channel and device filters) · **Severity:** P0 if shipped · **Status:** fixed before release

**Symptom:** with the new `channel=app` filter, the flagship West case returned
`contradicted`, no cause proposed, and a reconciliation reason saying the two
systems disagreed "by up to 68.0%, against a 5% tolerance".

**Root cause:** `finance_ledger` posts at invoice level by region and carries no
channel column. The revenue series was sliced to one channel and compared
against the whole region's ledger, so the two disagreed by exactly the share of
the region the other channels account for. Nothing was wrong with either source.

**Why this was the worst possible failure mode for this engine.** Contradiction
is not a soft verdict here: it suppresses the causes, prints "no cause is
proposed", and tells the reader the movement itself is in question. We would
have shipped a filter that made the product refuse to answer, using the one
output whose whole value is that it is only used when it is true.

**Fix:** narrow the second source by every dimension it actually has, and when
the reader asks for one it does not, decline the comparison rather than make it
badly. The state becomes `not_reconciled` with a reason naming the dimension:
"finance_ledger is not broken down by channel, so this slice has no second
posting to check against. The movement stands on one source alone."

**Trap:** T-23.

### B-029 · The demo gate had been failing, and the check under it was vacuous
**Found:** 2026-09-21 · **Severity:** P1 · **Status:** fixed

**Symptom:** `make smoke` exited non-zero on `entitlement: 200/403`. It is the
one command whose stated job is to gate a demo, so a red result there is either
acted on or, worse, learned to be ignored.

**Root cause, two of them.** The check asked for West as a South-only reader and
required HTTP 200. Since B-025 that request is refused at the boundary with 403
before anything is computed, which is the behaviour B-025 was filed to get. The
check was never updated, so correct behaviour reported as a failure.

Underneath it, the withholding assertion read `body["causes"]`. The diagnose
response has no `causes` key; the list is `verified`. So both counts were always
zero, the guard `shut >= open and open > 0` was always false, and the check
passed on the notice alone without ever confirming anything had been withheld.
It had been green for the wrong reason before it went red for the wrong reason.

**Fix:** split into the two behaviours. An out-of-scope region asserts the 403
refusal. Withholding uses an unsliced window the reader is allowed to ask about,
reads `verified`, fails when the unrestricted run verified nothing (so the
comparison cannot be vacuous again), and asserts the notice's own
`withheld_count` matches what was removed. Also switched from the `ops` persona
to `analyst`: ops withholds cross-region comparison, and on an unsliced window
every verified cause is a cross-region statement, so ops sees zero either way.

**Trap:** T-22. A check that reads a field the response does not carry passes
silently forever. Any assertion counting things must fail when the count it is
comparing against is zero, and T-17 is the same rule for shell.

### B-028 · A reader entitled to one region never sees the withholding notice
**Found:** 2026-09-21 (building the one-click scenario launcher) · **Severity:** P1 · **Status:** open

**Symptom:** the README tells a reviewer to set Entitlement to "South only" with
All regions selected and watch three causes be withheld with an escalation role
named. That does not happen. The console shows a South-scoped finding on a
different day, headed "in South (your regions)", with no notice.

**Root cause:** the server does the right thing. `/api/diagnose` with
`entitled=South` over the national window 13 to 15 Aug 2026 returns
`entitlement.notice` naming three withheld causes and `escalate_to:
finance_director`. The console never asks that question: it passes `entitled` to
`/api/series` as well, so the series, the flagged days and therefore the chosen
window are all restricted to South before a diagnosis is ever requested. A
national answer with holes in it and a South answer are different things, and
the console only ever produces the second.

**Decision needed, not just a fix.** Restricting the series is defensible on its
own terms. But the withholding notice is the more interesting behaviour, it is
already built and tested server side, and it is what the README promises a
reviewer. Either the console asks for the national window when the reader has
partial entitlement, or the README stops describing a step that does not
reproduce.

**Trap:** T-21. A capability that exists at the API and is unreachable from the
only client is not a shipped capability, and a README step nobody re-ran after
a client change is how that stays invisible.

### B-027 · A metric that beat expectation produces no finding at all
**Found:** 2026-09-21 (same session) · **Severity:** P2 · **Status:** fixed

**Symptom:** `aov` carries two detected anomalies in the current warehouse,
2026-08-01 at +9.3% and 2026-08-03 at +8.9%, both well past the robust-z floor.
Opening the metric prints "Nothing moved enough to explain".

**Root cause:** `ui/index.html` builds the findings list as
`series.anomalies.filter(a => a.direction === 'drop')`. The detector labels both
directions and `rank_exact` already sorts by the direction the total moved, so
the engine handles a rise correctly end to end. The view discards it.

**Why it matters beyond correctness:** a tool that only explains bad news is an
audit function and gets budget once. Explaining a beat tells the owner which
lever to repeat. The wording is the work, not the filter: "fell", "short by" and
"Impact" all assume a shortfall, and changing the filter without changing them
produces a page that says a metric fell by a negative amount.

**Fix:** the filter was dropped, and then eleven strings were made
direction-aware, which was the actual work. `fell` / `rose`, `short by` /
`ahead by`, `below expected` / `above expected`, `Impact` / `Upside`, `Worst
day` / `Best day`. `aov` now reads "AOV rose 8.9% above expected, ahead by ₹38"
where it read "Nothing moved enough to explain". All twelve demo scenarios land
unchanged, 512 tests, 33/33 audit, 35/35 smoke.


### B-026 · A rate metric rendered its own figures in rupees
**Found:** 2026-09-21 (reported from a click-through) · **Severity:** P1 · **Status:** fixed

**Symptom:** checkout conversion, all regions, 2 Jun to 31 Aug 2026 read
"Observed ₹0 against an expected ₹0, short by ₹0 (36.8%)" with an Impact tile of
₹0, under a headline correctly saying 36.8%.

**Root cause:** `fmtValue` and `fmtDelta` were added for the chart when this
exact failure was found there, and carry a comment saying so. `basisLine` and
`objectHeader` were not updated and still called `inr`, which rounds a
conversion rate of 0.0428 to zero rupees. The unit was available at both call
sites as `series.unit`.

**Second defect on the same screen:** the status pill read "Verified" because
`objectHeader` fell back to `'explained'` whenever a window existed, including
when no diagnosis had been run at all. A ratio metric cannot go through the
price/volume/mix identity, so the engine refuses a full diagnosis for it, and
the header was claiming verification over causal tests that had never executed.
Now `detected`, rendered "Detected, not diagnosed", which agrees with the
paragraph directly below it instead of contradicting it.

**Fix:** both call sites take the unit. Observed and expected render through
`fmtValue`, the shortfall and the Impact tile through `fmtDelta`, which states a
gap between two rates in percentage points per T-02.

**Trap:** T-02 already existed and this is the same claim it names. The trap was
written for the narrative validator and the UI was not checked against it.

### B-025 · The refusal was enforced on the diagnosis and not on the chart beside it
**Found:** 2026-09-17 (click-through before a mentor demo) · **Severity:** P0 · **Status:** fixed

**Symptom:** with Entitlement set to "South only" and West selected, the console
printed *"Nothing was computed ... no figure for West was produced, so none can
leak"* directly beneath the headline *"Net revenue fell 17.2% in West"*, West's
movement chart with its expected band, and West's price/volume/mix bridge
(₹2,71,320 → ₹2,34,939 a day). `make audit` reported 33/33 throughout.

**Root cause:** B-022 moved the refusal ahead of computation on `diagnose` and
`candidates`, and the audit check written for it asked those two endpoints. The
page draws from four more. `series` (the headline and chart), `decomposition`
(the bridge), `overview` (the metric table) and `document` (the full ticket
behind a citation) took no entitlement parameter at all, and the console never
sent one to `series` or `overview`. The same class as B-022: a restriction on one
endpoint and not its neighbour is not enforced. A second leak waited behind the
fix: `overview` caches its seasonal decomposition by `(kpi, region)`, so a scoped
all-regions total would have been served from, or written into, the unscoped
entry.

**Fix:** one guard, `_refuse_outside_scope`, called by all six endpoints before
anything is read; an all-regions request from a scoped reader is filtered to that
reader's regions rather than totalled across everyone; the scope is part of the
overview's cache key; the console sends the entitlement on every request and
renders a 403 as a refusal rather than leaving the previous page on screen.

**Regression test:** `tests/test_entitlement_neighbours.py`, parameterised over
all three industries, and the audit check now drives all six endpoints.

**Lesson:** the audit was green because it tested the endpoints the last fix
touched rather than the ones a reader's page reads. Test from the page inward.

### B-023 · A governance artefact that governed nothing
**Found:** 2026-08-30 (red-team audit) · **Severity:** P1 · **Status:** fixed

**Symptom:** every contract declared `row_filter`, `column_masks` and
`domain_restriction`. Grepping for consumers found exactly one: `inspect.py`,
which *printed* them. The README calls contracts executable governance, and two
thirds of the access policy was a label.

Worse than absent, because it invites the question it cannot answer. A judge
asking "show me the column mask working" gets nothing, and the masked columns
named — `unit_margin`, `customer_email` — **do not exist in the source table at
all**, so the policy protected data that was never there.

**Fixed, each field now doing the job it claimed:**

- **`row_filter`** is compiled from the contract instead of hardcoded. It was a
  literal `WHERE region IN (?)` that happened to match what every contract
  declared, so a contract could declare a different rule and the engine would
  silently apply its own. It now **fails closed**: a filter that does not bind
  `:entitled_regions` raises rather than being dropped, because a declared access
  rule that is quietly ignored is the exact failure the policy exists to prevent.
- **`column_masks`** are applied to any frame handed out under a contract, via
  `Warehouse.masked`. Masking here rather than in the SQL is deliberate: the
  calculation may legitimately need a column a reader may not see, and removing
  it from the query would change the answer rather than restrict the view.
- **`domain_restriction: [pii]`** redacts at the quarantine boundary, which is
  the last point before untrusted text becomes prompt tokens. Emails, Indian
  mobile numbers, Aadhaar-shaped and card-shaped runs. Citations are checked
  against the *redacted* text, so a model cannot quote back what it was never
  shown, and the scan for injection runs *before* redaction so a payload hidden
  beside an email keeps its flag.

**Two ordering bugs found while writing the patterns**, both the same shape as
the defects this file already records — a general rule applied where a specific
one had to go first:

1. A sixteen-digit card in groups of four begins with a twelve-digit run, so the
   Aadhaar pattern matched first and turned `4111 1111 1111 1111` into
   `[id-number] 1111`, leaving four digits of a card number in the prompt.
2. `(?:\+91[\s-]?)?\b[6-9]\d{9}\b` misses `+91 98765 43210`, because people
   put a space in the middle of their own phone number.

**And the honest half:** `Warehouse.unenforceable_policy` reports which declared
restrictions this deployment cannot apply — masks naming absent columns, domain
classes with no patterns. `make audit` prints it. A mask that protects nothing
looks identical to a working one from the outside, which is precisely why it has
to be named rather than passed over.

**Why the existing check missed it:** there was no check. The security section
asserted entitlement filters in SQL, which it did, and never asked whether the
filter came from the contract that declared it.

### B-024 · An asymmetry that was measured, and kept
**Found:** 2026-08-30 (red-team audit) · **Severity:** Low · **Status:** kept deliberately

**Symptom:** event-time isolation tests `pre_trend < 0` — whether the series had
*fallen* beforehand — without checking that the prior drift and the candidate's
effect point the same way. A candidate credited with an increase is therefore
judged against a decline it did not share a direction with.

**The obvious fix made four measured rates worse:**

```
                    with fix   without
top-1                 38.2%     38.9%
traps rejected        85.9%     87.5%
abstention precision  81.0%     85.7%
abstention recall     82.4%     88.2%   (3 missed vs 2)
```

**Why.** The direction check removes a guard, not a bias. In a population whose
movements are mostly declines, a candidate that "explains" an increase against a
falling trend is overwhelmingly a coincidence, and rejecting it is right even
though isolation is a clumsy place to catch it. The gate that ought to catch it,
exposure consistency, cannot: these candidates are single-region, and consistency
is UNAVAILABLE there by design.

**Status: kept, and recorded.** It stays until there is a gate that rejects these
for the right reason. "Conservative in a way we have measured" is a defensible
answer to a judge; "asymmetric because nobody noticed" is not, and that was the
state before this entry existed.

### B-022 · A redaction notice printed next to the data it said it had removed
**Found:** 2026-08-30 (red-team audit) · **Severity:** P0 · **Status:** fixed

**Symptom:** a reader entitled to South alone, asking about West, received all
three West causes with their exact rupee contributions, the ranking table, the
set-aside list and a narrative naming them — beneath a notice reading *"3
verified cause(s) lie outside your entitlement scope and are not shown"*. The
default persona is `analyst`, so the default path leaked.

**Root cause, and it is one line:**

```python
else:  # analyst: the full record, nothing removed
    out = {**result, **out}
```

`out` carries no `verified` key of its own — only the CFO and Ops branches set
one — so merging the raw result over the filtered `out` restored every row the
entitlement had just removed, while the notice assembled from `withheld_causes`
survived and went on claiming otherwise. Persona depth and row entitlement are
different things: an analyst may see more *detail* than a CFO; neither may see a
region they are not entitled to.

**Four more surfaces carried the same figure in different clothes**, and each had
to be found separately. This is the finding with the longest reach:

1. `movement.per_cause` — a map from candidate id to exact rupees. The most
   machine-readable possible form of the protected quantity, passed through
   untouched to every persona.
2. `scenarios` — "what if we reversed this cause" names the cause and quantifies
   its reversal.
3. `narrative.validation.accepted` — **a second copy of the same sentences**,
   kept so a reader can see which checks passed. Redacting `sentences` and
   shipping `accepted` is not a redaction. This one survived three rounds of
   fixing while `redacted_sentences` reported 3.
4. `ranking.track_a` — spans several dimensions and only one is region, so a row
   labelled `channel · store` carried the withheld region's rupees under a
   different label. Filtering by region leaked; the table is now withheld whole.

**The notice itself leaked**, quoting *"including one accounting for 26,239
rupees per day"* — the exact figure entitlement exists to withhold, and
repeatable, so a reader entitled to one region could enumerate every other
region's contribution by asking about each in turn. Existence and materiality
are what a reader needs in order not to act on a partial picture; neither
requires the number. `tests/test_personas.py` previously asserted the old
behaviour and has been updated with the reasoning recorded.

**Two more holes in the same wall:**

- **`/api/candidates` took no entitlement parameter at all.** The console never
  called it with a scope, so nothing broke, and a caller constructing the request
  by hand could read every candidate cause and contribution for any region. A
  restriction enforced on one endpoint and not on its neighbour is not enforced.
- **`entitled=` granted everything.** `tuple(...) if entitled else None` — an
  empty string is falsy, so the one input a caller fully controls was a way of
  switching the restriction off. `None` (absent) now means unrestricted; `""`
  (present but empty) means entitled to nothing.

**Fix, and why it is a refusal rather than a better scrub:** redaction after
computation cannot be made airtight on this shape of answer — the same figure
appears in a contribution table, a scenario estimate, a narrative sentence, a
validation block and a per-cause map, and one was still leaking after three
passes. A region outside entitlement is now refused with **403 before anything is
computed**. The partial-entitlement case still redacts, and now redacts all five
surfaces.

Note what is *not* claimed: the panel still contains every region, because
difference-in-differences needs the unexposed ones as a control and filtering
them out would turn every verdict into `CANNOT_VERIFY`. Using a region as a
statistical control is not the same act as disclosing its figures to a reader,
and only the second is what entitlement governs.

**Why the existing checks missed it.** `scripts/audit.py` asserts that
entitlement filters in SQL before any projection, and it does — on `kpi_series`,
which the diagnosis path does not use. The check passed while the path it did not
cover leaked. `tests/test_entitlement_leak.py` now asserts the *property* — no
surface reaching the reader names a withheld cause — rather than the mechanism.

### B-021 · An explicit "no model" read as "decide for me", in three places
**Found:** 2026-08-30 · **Severity:** P0 · **Status:** fixed

**Symptom:** a diagnosis requested with `backend=none` took 78 to 235 seconds
over HTTP while the identical call in-process took 1.1. The console was
unusable: every KPI click sat on "Testing candidate causes" for minutes, and the
telemetry said `model_calls: 0` for eight stages and `narrate 30,318ms,
calls: 1` for the ninth.

**Root cause:** three components resolved their own backend when none was given,
and each wrote the test as truthiness or `is None`:

```python
self.backend = backend or default_model(...)          # ModelWriter
if self.backend is None: self.backend = model_for(...) # ModelExtractor, ModelQueryWriter
```

`None` was doing two incompatible jobs. From `model_for(Task.NARRATE, "none")`
it means *the caller explicitly asked for no model*; as a constructor default it
means *nobody said, so decide*. Written this way the second silently overrode the
first, so the deterministic path — the one the benchmark is produced on and the
one a reader picks to see the contrast — called the model anyway.

**Fix:** a sentinel. `whychain/llm.UNSET` means "decide"; `None` means "run
without a model", and an explicit choice now beats a default, which is the entire
point of it being explicit. Deterministic diagnosis over HTTP: **0.9s, zero model
calls.**

**Why it survived so long:** nothing failed. The answers were right, the tests
passed, and the only symptom was time. It was found by reading the per-stage
telemetry rather than the output, which is the only thing that finds a defect
whose sole cost is latency — and objective 8 names latency as a constraint the
engine must operate within, so a stage silently ignoring the switch that governs
it is a P0 rather than a performance note.

**Three things came out of it:**

1. **The suite must not depend on a backend.** Once `Task.EXPAND` was wired in,
   every pipeline test began making real calls: 18 seconds became over ten
   minutes and the result depended on whether Ollama happened to be running.
   `tests/conftest.py` now forces `WHYCHAIN_LLM_BACKEND=none` for the session.
   A test whose result depends on what a 7B generated is a sample of one.
2. **Every call is now bounded.** `WHYCHAIN_LLM_TIMEOUT`, 20 seconds by default,
   was 120. Past it the deterministic path stands in and the receipt says so.
3. **Corroboration ran for candidates nobody reads.** It is consumed for
   verified candidates only, and was computed for rejected ones too — wasted
   milliseconds deterministically, a wasted model call each with a backend on.

### B-020 · Five defects a pre-submission read-through found, four of them visible on screen
**Found:** 2026-08-30 · **Severity:** P1 · **Status:** fixed

**Symptom:** none of these crashed, failed a test or tripped the audit. Each
produced a plausible screen carrying a number that was wrong, or a sentence that
contradicted the number beside it. They were found by reading the console output
against its own arithmetic, which is the only thing that finds this class.

**The five:**

1. **Over-explanation scored as perfect coverage.** Three verified causes on the
   flagship retail case contribute −₹26,239, −₹10,084 and −₹16,989 against a
   total movement of −₹28,307: they sum to 188% of it. `explained_movement`
   detected exactly this, capped the total, and threw the finding away. Coverage
   is the largest single component of the confidence score at 0.35, and it was
   paying full marks in precisely the case where the split between the causes
   cannot be established. The cap was right; the silence was the defect. The
   overlap ratio is now returned with the total and the coverage share is
   divided by it — not an arbitrary penalty but the same statement read the
   other way, since causes claiming 188% of a fall are on average overstated by
   that factor.

   **A second defect inside the fix.** Discounting coverage before the
   `MIN_COVERAGE` gate moved the abstention boundary without anyone deciding to
   move it, which is the silent-threshold failure `score()`'s own docstring
   warns about for calibration. Measured: 16 extra abstentions and abstention
   precision from 85.7% to 51.4%. The discount is now priced into the score and
   kept out of the gate, which reads undiscounted coverage. Every benchmark rate
   returned to baseline and held-out ECE improved 0.117 → 0.069 raw, 0.099 →
   0.042 calibrated.

2. **The narrative asserted a remainder that did not exist.** "Verified causes
   account for −₹28,307 of the total movement; the remainder is unexplained" was
   emitted unconditionally, so at 100% coverage it contradicted itself in the
   same sentence. Three sentences now, chosen on whether coverage is whole,
   partial, or overlapping — and the overlapping one states the ratio, because a
   reader adding the per-cause column up otherwise finds it does not reconcile.

3. **Corroboration was structurally impossible for every externally-caused
   event.** `related_issues` maps the residual issue to an empty tuple, and an
   empty expectation does not mean "nothing corroborates this" — it discards
   every retrieved document before it is read, so the answer is identical
   whether the record is silent or full. An operational note and the complaint
   it produces are written in different registers: a terminal writes
   "allocation reduced to 55 per cent of indent", the dealer writes "no stock at
   the depot since Monday". Every petroleum and power cause classified as the
   residual and reported an empty record while the tickets describing it sat in
   the retrieved set. `Corpus.expected_for` now falls back to every recognised
   code, the residual still counts as support for nothing, and petroleum's
   vocabulary gained the operational phrasings. `TA-4411` went from
   "Nothing in the record describes this" to 12 supporting documents.

4. **The model extractor read every industry in retail's vocabulary.** The rule
   table had been made per-industry; the model path had not. `SYSTEM` named
   `checkout_failure, payment_failure, delivery_delay, stockout` in its
   instruction and `SCHEMA` pinned the same enum, and `ModelExtractor.fallback`
   defaulted to a retail `RuleExtractor` — so the API path, which always
   constructs a `ModelExtractor`, classified fuel-dealer and generator tickets
   into retail codes whatever industry was selected. `other` was the honest
   answer every time. This is the path an API-keyed run takes, so it would have
   surfaced the moment a backend was switched on for a demo. Prompt, schema and
   fallback are now built from the vertical's `Vocabulary`.

5. **A candidate named after a common noun, and colliding.**
   `re.split(r"[:\s]", text)[0]` reads "Operations circular OC-2026-14: ..." as
   the candidate `Operations`. A decision card headed by a common noun is the
   visible half; the collision is worse, since every circular in the corpus
   became the same candidate. The prefix before the first colon is now searched
   for a token that looks like a reference.

**Also fixed, latent:** `_NUMERAL` in the narrative validator was written
`\d[\d,]*`, a thousands-separator class that also swallows a *trailing* comma,
so "accounts for ₹35,323, which is all of it" scanned as the numeral
"₹35,323," — a token appearing in no fact, and the sentence was rejected as
fabricated for its punctuation. Harmless while the deterministic template
avoided that construction; it would have silently dropped model-written
sentences. `tests/test_overlap_and_corroboration.py` covers all of it.

### B-019 · Eight defects a second and third industry found in the first one's assumptions
**Found:** 2026-08-29 · **Severity:** P1 · **Status:** fixed

**Symptom:** the petroleum and power verticals were built on the existing
engine without changing a calculation. Standing three industries side by side
immediately produced eight failures, every one of them a retail assumption that
had been true by accident rather than by design.

**The eight, and what each was:**

1. **A rate of zero, divided by.** The session emitter derived scheduled volume
   as `orders / conversion_rate`. Petroleum's pipeline movement never crosses a
   loading gantry, so it was declared at a rate of nought, and the division
   produced infinities. A device with no rate is not a device with a rate of
   zero; it now emits no scheduling rows at all.
2. **Two causes that could not move their own metric.** Power's signal-gap and
   not-foreseeable cases were planted against `grid_availability`, which is
   built from the delivery outcomes -- and neither `heat_wave` nor
   `plant_outage` was in that world's `delivery_event_kinds`. Both cases were
   undetectable by construction.
3. **A sparse grade priced the wrong side of the average.** The petroleum
   sparse-history case withdrew a grade priced *below* the book average, so the
   shortfall *raised* average consignment value. The case was testing the
   opposite of what it claimed.
4. **Thresholds derived from the wrong basis.** Every materiality floor was
   computed from the generator's panel, where revenue is `orders x
   units_per_order x price`. The KPI series comes from the order lines, where
   quantity is a Poisson draw -- a six-fold difference. Two headline metrics
   could not produce a single material movement. This is B-017 exactly: a
   number derived at the wrong grain, caught this time because the queue ranked
   it against something else.
5. **A noise model three and a half times too tight.** The binomial standard
   error assumes the numerator is a subset of the denominator, so its variance
   vanishes as the rate approaches one. Power's fulfilment runs at 91 per cent
   and its numerator is metered separately: measured relative spread 0.164, of
   which binomial predicts 0.046. One observation in fifteen flagged. The
   contract now declares `noise_model: binomial | counting` and the default is
   the original, so retail is untouched.
6. **A phantom day at the end of the series.** The East extract lands in local
   time. The realisation contracts correct it; the *count* contracts inherited
   retail's transform list, which does not. Five and a half hours of orders
   fell into a day after the series ends, and that partial day -- a fraction of
   the usual count -- ranked near the top of two queues as a collapse.
7. **Off-vocabulary that was not off-vocabulary.** A petroleum complaint written
   to be unmatched by the rule table contained the word "margin", which is in
   that table. The rule extractor would have scored better than it is, and the
   with-model contrast would have measured less than it claims to.
8. **An optional that leaked.** `Corpus.vocabulary` was `Vocabulary | None`,
   where `None` meant "retail's". The API passed it straight into the candidate
   scanner and every diagnosis returned a 500. The field is no longer optional.

**Why they stayed hidden:** four of the eight are assumptions that are true of
retail and of nothing else -- a conversion rate well below one, a numerator
drawn from its denominator, an internally-driven event that always lands in the
delivery table, a sparse product priced above the mean. Nothing had ever asked
whether they were properties of the method or properties of the business. The
second and third industry are what asked.

**Fix:** each listed above. Six of the eight are data or contract changes; two
(`noise_model`, and making the vocabulary non-optional) are engine changes that
leave every default at the original value, which is why the retail warehouse
still regenerates byte for byte and the benchmark is identical on every rate.

**Regression test:** `tests/test_verticals.py`, 45 tests, parameterised over all
three industries. They check the pairs of places that have to agree: the column
names the generator writes against the ones the scanner looks for, the plan
candidate kind against the driver map, the scope terms against values the data
actually contains, the off-vocabulary against the rule table, the materiality
floor against what a rate can physically do, and the hourly floor against the
daily one. Defect 7 was found by the test rather than by a reader.

---

### B-018 · An hourly metric detected on a daily cycle, and a rate judged at one volume
**Found:** 2026-08-29 · **Severity:** P1 · **Status:** fixed

**Symptom:** `checkout_conversion` flagged 1,393 of West's 20,824 hours at
z >= 3, a rate of 6.7% where a calibrated robust z should give well under one
per cent. 385 of those survived materiality. The queue absorbed it because the
rupee ranking kept them off the top, so the working assumption was that hourly
conversion is simply noisy. It is not; the detector was misconfigured for it in
two independent ways, and "raise the z threshold" would have hidden both.

**Root cause 1 — the seasonal period is a daily constant.** `decompose` defaulted
to `periods=(7,)` and every caller took the default. For the four daily KPIs 7
means "day of week". For the hourly one it means *seven hours*, a cycle nothing
has, which beats against the real 24-hour day on a 168-hour period and leaves
the intraday shape in the residual for the detector to find. The fingerprint was
a flag rate that swung with the hour for no volume-related reason: 14.7% at
00:00 and 12.2% at 12:00 against 0.1% at 15:00. The 60-row minimum-history guard
was the same mistake in miniature — sixty rows of hourly data is two and a half
days — and it was duplicated in two API callers on top of `decompose`'s own.

**Root cause 2 — one noise scale across a twentyfold swing in volume.** The MAD
fits a single spread for the whole series, so a rate read off 49 sessions at
midnight is judged against the spread of one read off 925 in the evening. The
binomial standard error at those two volumes differs by a factor of four. The
thinnest decile of hours flagged at 14.4% against about 5% for the rest, and all
226 hours in which West took no conversions at all were flagged — though at a
4.3% rate over ~50 sessions an empty hour is roughly a one-in-nine event, and
flooring a zero rate to take its logarithm makes it a guaranteed outlier.

**Why it stayed hidden:** the four daily KPIs are the ones anybody looks at, and
for them the defaults were right. The hourly contract exists to prove the engine
reconciles grains, and it was the one thing detected at the wrong grain. B-017
found the same class of error in `materiality`; this is the same error one stage
upstream, which is why fixing the conversions did not touch the flag count.

**Fix:** seasonal periods come from `SEASONAL_PERIODS[contract.grain.time]`, the
history minimum is four cycles stated in the series' own units, and the scale is
per-observation — the standard error of the rate, binomial for a proportion and
`1/sqrt(n)` for an average, normalised so the median observation keeps the scale
the MAD already fitted. A half-count (Jeffreys) correction gives an empty period
a finite logarithm without moving a populated one. `decompose_for(series,
contract)` is now the entry point and reads all four off the contract, because
a caller that passes them by hand is a caller that can get them wrong for a
metric it was not thinking about. `_roll_up` carries the denominator alongside
the rate so the noise model has it.

**Result:** 1,393 flags to 62 (0.30%, against a nominal 0.27% for z >= 3), 226
flagged empty hours to 1, 385 material drops to 58. Nothing else moved: the
benchmark is identical to the digit on every rate, because a daily sum has no
denominator and its periods were already right.

**Cost, and what was traded away.** The obvious period set for hourly is
`(24, 168)` — trading day and trading week. It was measured rather than assumed:
it moved the flag rate from 0.35% to 0.30% and the decomposition from 0.50s to
10.23s per region, twenty times the cost for eleven flags in 20,824
observations, which objective 8 does not allow. Hourly fits `(24,)` and the
weekly rhythm is deliberately not fitted; the comment on `SEASONAL_PERIODS`
carries the numbers.

**Found alongside, same shape, one line:** `/api/series` rounded every figure
to two decimal places, which is right for rupees and destroys a rate. The whole
hourly conversion chart arrived at the browser as seven distinct levels between
0.01 and 0.07, with the lower band flat on zero — so the band this fix makes
vary with volume could not have been seen. The precision now comes off the
contract's unit, and the same three months of West conversion arrive as 56
distinct levels across 57 points.

**Regression test:** `TestGrainAwareness` and `TestVolumeWeightedNoise` in
`tests/test_detect.py`, nine tests. The one that carries the argument is
`test_the_same_fall_is_an_event_when_busy_and_noise_when_quiet`: one gateway
outage, the same 60% fall planted twice, flagged across the evening peak and
silent across the small hours. Raising the z threshold would have silenced both.

---

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
