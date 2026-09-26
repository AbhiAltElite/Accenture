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
| T-29 | A handler called in-process as a Python function | api, scripts | FastAPI parameters declared as `Query(...)` arrive as `Query` objects, which are truthy, when the handler is called directly rather than over HTTP. Every parameter the caller omits becomes a filter for a slice that does not exist (B-040). Call through `TestClient`, or pass every parameter explicitly, and never report success without checking the response |
| T-30 | A demo scenario is data, and data drifts | ui, datagen | A button's label promises an outcome its coordinates no longer produce: a gap on a metric that cannot be diagnosed, a refusal that crashes the page (B-039, B-041). Scenario coordinates are read out of the page by a test that asserts each one's promised outcome (`tests/test_scenarios.py`), and the rendered page is checked in a browser (`/uat`) |
| T-31 | A page sentence composed from a template that is true only for some results | ui | "No cause survived testing" was printed over two causes that had passed testing, and "nothing external warned of this" over a verdict one of whose three causes is that a warning was received (B-044, B-045). Every fixed sentence is checked against every value its inputs can take, or the engine's own reason is shown instead |
| T-32 | A field attached to the diagnosis after the projection | api | `diagnose()` projects, then adds fields. Anything added there skips entitlement. A hash is safe; anything that names a cause or sizes one is not, and must be withheld whole when the projection withheld a cause, since a partial set of figures subtracts to the missing one. B-049. The audit check `No surface names a cause outside entitlement` catches it |
| T-33 | A candidate tested at a wider scope than the one its source names | verify | A note about one SKU or one category, tested as the whole region, borrows every other cause's movement and verifies (B-056). Carry every scope the source names; when a scope cannot be read, return `cannot_verify` rather than widening |
| T-34 | A contract that reads a source's timestamps without that source's correction | contracts | `orders` got `tz_normalise` in B-019; `aov` and `checkout_conversion` read the same `order_ts` and did not (B-058). A test asserts every contract reading `pos_txn.order_ts` declares it, rather than each contract remembering |
| T-35 | Scoring the benchmark and not the demo | bench, uat | The cases a jury sees are the ones that must be right. Score each demo case against its own planted causes, not only for page-equals-API consistency (B-063) |
| T-36 | A component class named after a common word, in a shared stylesheet | ui | `ui/theme.css` defines `.who` (the seat chip), `.facts`, `.chain`, `.status`; a page that already used the same word for something else inherited a border, padding and flex from the theme (B-067). Page classes that could collide are named for what they are (`owner-note`, `kvgrid`, `whychain`), and a new shared class is grepped for in every page before it lands |
| T-37 | A figure shown in two views, computed twice | api, ui | The rain's share was scaled for overlap in the bridge with the exact ratio and in the recovery line with one rounded to three places: four rupees apart (B-071). Where one figure appears in two views, one test asserts they agree, and a ratio used as a divisor is never rounded before use |
| T-18 | A benchmark result that improved for a reason nobody checked | bench, datagen | Numbers that move the flattering way get accepted; numbers that move the other way get investigated. A harness defect usually shows up as the former. Any invariant the generator depends on is executed by a test, never only stated in a docstring (see B-014) |

---

## Defects

### B-075 · A change already made could be raised as a change request
**Found:** 2026-09-26, clicking every button that writes a record · **Severity:** P1 · **Status:** fixed

**Symptom:** on the flagship, the e-commerce lead confirmed the rollback worked (the release log records it as done on 19 Aug), and the card then offered **Raise change request** for "Apply release rollback". A service desk would have received a ticket for work already finished.
**Root cause:** the ticket rule checked only that a decision was accepted, not whether the change it names had already been made.
**Fix:** the engine refuses a ticket for a card with `already_actioned` (409, "the change is already done"), and the button is not shown. Confirming it worked now reads "Confirmed it worked, by …" rather than "Accepted by …".
**Regression test:** `test_a_change_already_made_raises_no_ticket`; the open-decision path is tested on the petroleum turnaround through single sign-on.
**Known limit, demo only:** the five demo seats hold no petroleum or power owner (supply manager, trading head and so on), so on the demo no seat can raise a change request. Single sign-on accepts every role.

### B-074 · Every Teams card went to one channel while the preview named the owner
**Found:** 2026-09-26 · **Severity:** P1 for the hand-off claim · **Status:** fixed

**Symptom:** the Teams preview said "to E-commerce lead", but the engine posted every card to the single `WHYCHAIN_TEAMS_WEBHOOK`, whoever owned the decision.
**Root cause:** routing was never built; the preview implied it.
**Fix:** a card goes to `WHYCHAIN_TEAMS_WEBHOOK_<ROLE>` for its owner's role (each Teams channel has its own incoming webhook), falling back to the shared one and saying so. The audit entry records where it went.
**Regression test:** `test_a_card_goes_to_the_owners_channel_not_a_shared_one`.

### B-073 · A courier's collapse was put on the marketing budget
**Found:** 2026-09-26 · **Severity:** P1, visible on a finding · **Status:** fixed

**Symptom:** South, 18 to 22 May: "A regional carrier suspended operations without notice" produced a decision card "Apply media budget for South", owned by the marketing lead.
**Root cause:** notes were matched to drivers, and to scope, by substring: "suspended" contains "spend". The scope reader had the same flaw ("approach" would have read as the app channel), though no current note triggered it.
**Fix:** `mentions()` matches whole words, plurals included, for both. The carrier note now matches no driver, so the card says there is no lever and gives a monitoring rule, which is the truth: net revenue's contract declares no logistics driver. The benchmark is identical to the decimal.
**Regression test:** `test_a_word_inside_another_word_names_no_driver`, verified to fail without the fix.

### B-072 · A container build would have carried the model key
**Found:** 2026-09-26, preparing the deployment guide · **Severity:** P0 for any deployment · **Status:** fixed

**Symptom:** `.dockerignore` excluded the virtualenv, caches and the warehouse, but not `.env`. `docker build`, and any cloud build from the folder (`gcloud run deploy --source .`), would have copied the model API key into the image. The audit trail and the demo archive would have gone in too.
**Root cause:** `.env` is gitignored, so it never reached GitHub, and the image was only ever built locally; nothing checked what the build context contained.
**Fix:** `.dockerignore` excludes `.env` and `.env.*`, the audit, archive and app-data folders, and the desktop package outputs. A deployment sets the key as the platform's secret.
**Lesson:** gitignored is not the same as excluded from every other copy of the folder. Every packaging path (git, the portable zip, the image) keeps its own list, and each has to name the secrets.

### B-071 · One cause, two figures; a slide that contradicted its finding
**Found:** 2026-09-26, a page-by-page pass with every figure re-derived from the raw warehouse · **Severity:** P1 for the flagship · **Status:** fixed

**What held:** 21 of 21 worst-day values re-derived by hand from `pos_txn`, applying each contract's declared SQL and transforms without the engine (averages as a ratio of sums, as the contracts declare), matched the app to the paisa across all three industries; `/uat` 88 of 88.

**What did not, each with its cause:**
- **The rain was ₹12,572 a day in one line and ₹12,576 in two others.** The recovery line divides by `movement.overlap`, which the API rounded to three places (1.127 for 1.12669); the bridge and the fair target divide by the exact ratio. Kept at full precision now: it is a divisor, not a display figure. Test: `test_one_cause_is_one_figure_in_every_view`, verified to fail without the fix.
- **The board-pack slide said "Awaiting approval"** for the rollback the finding page reports as already done on 19 Aug. The slide read only the audit trail, not `already_actioned`. It now says "Already done ...; awaiting the owner's confirmation that it worked."
- **The slide's cause bars were sized against the largest cause**, so the largest always drew full. Now each is its share of the movement, with the percentage.
- **The workbench said "calibrated to 1"**; the decision view never states certainty ("above 0.95"). Both now read the same. Its worst day was an ISO date.
- **Sentence case capitalised identifiers** (`Pos_txn`, `Unit_margin`). A block that opens with code keeps its case.
- **"Prior episodes"** broke into the value beside it in the workbench margin; the value is shortened to fit.

**Lesson:** a figure that appears in more than one view needs one test asserting the views agree, not one test per view (T-37).

### B-070 · A decoy planted in one region verifies as a cause in another
**Found:** 2026-09-26, breaking down the benchmark misses · **Severity:** P1 for the published decoy figure · **Status:** open, root cause not yet established

**Symptom:** in `bench/report.json`, 13 cases are explained but not exactly right. In all of them the true cause was verified; a planted decoy passed too. In 6 of the 13 the decoy belongs to a different region from the case (`bench-02-north-0` verifies `bench-02-south-0-decoy`). These are part of the "14 planted decoys got through" on the track record.
**Root cause:** not a scope defect; the first hypothesis (T-33) was wrong. `datagen/bulk.py` plants each decoy as a plan entry active in its own region **and two others**. Where one of those regions has its own real cause in the same window, the decoy lines up in place and time with a real fall and passes every statistical test there. The tests measure coincidence, and this is a perfect coincidence.
**Evaluated, not shipped (26 Sep):** a check that reads each cause's note for whether it supports or disrupts the business, and sets aside one that points against the measured effect (model reads, code decides, keyword fallback). On the benchmark it looked like 87.5% to 100% decoy rejection, but only because it was reading the engine's own label, "Promotion X active", which the plan also puts on rivals' activity; it also set aside six true causes whose note and plan row share an id. Restricted to what a person wrote, it changed nothing on the benchmark (decoys have no documents) and nothing on any of the 36 findings across the three demo industries. A check that cannot be shown to help a real case does not go into the engine. Kept at its design, for when real notes can measure it.
**Fix:** none yet. Any fix re-runs `make bench` and the demo answer key: it changes published figures.
**Lesson:** a benchmark whose decoys carry no text cannot measure anything that reads text. Before building a reading step, check the benchmark can score it.

### B-069 · Closing the app window left an engine running for good
**Found:** 2026-09-26, the Mac slowing down with four engines running · **Severity:** P1 on a demo laptop · **Status:** fixed

**Symptom:** two engines on ports 8765 and 8766, 12 and 5 hours old, parent `launchd`, nothing connected, 1.2 GB between them, alongside the two in use. The Mac had pushed 2 GB into swap and every app on it lagged.
**Root cause:** opening WhyChain while a window was already open hands the request to that window, and the second launcher returns at once. If the code had changed since the first engine started, the second launch had already stopped it and started a new one, recorded in `engine.json`. Closing the window then stopped only the first launcher's own pid, already dead, and deleted the record: the new engine ran on, known to nothing. The open window's engine was also restarted underneath it, which reads as the app glitching.
**Fix:** `close_engines` stops both this launch's engine and the one the state file names, since every window shares one profile and none is left once it closes.
**Regression test:** `test_closing_the_window_stops_the_engine_a_second_launch_started`, verified to fail without the fix.
**Lesson:** a process that hands ownership to a file must read the file back before it tears down, not only its own memory of what it started.

### B-068 · The UI pass that followed the redesign: nine defects a reader saw
**Found:** 2026-09-26, reviewing the redesign on screen · **Severity:** P2 · **Status:** fixed

**Symptom and root cause, each:**
- The board-pack slide rendered dark text on a dark ground in a dark-mode system. The shared theme's `prefers-color-scheme: dark` block overrode the slide's own `:root`. The slide now carries `data-theme="light"`, which the dark block excludes: a board pack is paper.
- The seat avatar wrapped onto a second line of the top bar at 1280px. The bar was `flex-wrap: wrap` and its content summed to within 9px of the width. It no longer wraps above 760px, and the tabs tighten below 1400px.
- A large figure ran out of its card in the workbench (`₹2,71,63,12…`). A fixed size with no fit for a nine-digit rupee value. Long values drop a size; none wrap.
- "All unit classs": plurals were an appended `s`. `pluralWord` now forms them.
- An em dash in the power industry's summary, shown on the workbench.
- "Relative size" meters were sized against the largest cause, so the largest always read full and said nothing. They show each cause's share of the movement, with the percentage.
- The calendar ran a warning on every day into a solid saw of triangles, drew events from before the axis into the lane labels, and set two labels on top of each other. Consecutive warnings are one band with a count, only events on the axis are drawn, and the labels are placed apart.
- Figures in the what-if cards carried no direction beyond their sign, and "+₹0" was printed with a sign. They are coloured by direction, and zero has no sign.
- Captions, table cells and badges began in lower case ("a day", "not excused", "volume"). Much of it is contract and engine data. Fixed at display: every block of text starts with a capital, and the data is untouched.

**Regression test:** `/uat` (74 of 74) and the screenshots of this pass; the class collision is T-36.

### B-067 · "You are the accountable owner" drawn as a seat chip
**Found:** 2026-09-26 · **Severity:** P2 · **Status:** fixed

**Symptom:** the owner line under the sign button rendered as a bordered pill with the avatar chip's padding and flex layout.
**Root cause:** the page's `.actions .who` and the theme's `.who` (the signed-in seat) are the same class. The theme loads first, and every property the page did not set came from it.
**Fix:** renamed to `.owner-note`; the right column is now one contained sign-off box.
**Lesson:** T-36.

### B-066 · A Mac stops anything that arrived by AirDrop or download, including our Python
**Found:** 2026-09-25, building the offline packages · **Severity:** P1 for sharing by AirDrop · **Status:** designed around; the full fix is signing

macOS marks every file that arrives by AirDrop, a browser, Slack or email as
quarantined, and refuses to run a quarantined program that is not signed and
notarised by a registered Apple developer. That covers `Start WhyChain.command`,
`WhyChain.app` and the Python the offline package carries. Since macOS 15 the
old right-click, Open bypass no longer works for unsigned files; the approval
is System Settings, Privacy & Security, Open Anyway.

**What is done:** a copy made by USB stick or shared drive in Finder is not
marked, so it opens with no prompt; `START HERE.txt` says so first. By AirDrop
or download, one approval of `Start WhyChain.command` is the only one: its first
line clears the mark from its own folder and nothing outside it, before any
program in the folder runs, so the bundled Python and `WhyChain.app` are never
stopped afterwards. `launch.py` and the app bundle do the same before running
anything, for a start that bypassed the script. Tested by marking a package the
way AirDrop does, unzipping it the way Finder does (2,505 files marked), and
running it with pip pointed at a dead address: marks cleared, environment built
from the bundled Python, nothing downloaded, 9 of 9.

**The only complete fix** is a Developer ID signature and notarisation, which
needs a paid Apple developer account. Recorded rather than pretended away.

### B-065 · Moving the app to another computer failed in six ways, none of them tested
**Found:** 2026-09-25, packaging the app and installing it cold from the zip · **Severity:** P1, demo risk · **Status:** fixed

The cross-platform launcher arrived on 24 Sep on a branch CI never ran on (CI
runs on `main` and on pull requests; the last run was 18 Sep), so its
Windows, macOS and Linux first-run job had never executed. Reproduced here:

1. **An interrupted first install was never repaired.** The launcher trusted
   `.venv` because it existed. Close the window during the silent install, or
   lose the network, and every later start died with "No module named
   uvicorn". The same after a pull that changed `requirements.txt`.
2. **The install was silent for minutes**, which is what made people close it.
3. **The macOS app carried the builder's own path** (`/Users/<builder>/...`) as
   its fallback. macOS runs a quarantined app (one that arrived by AirDrop or
   download) from a hidden copy that cannot see its folder, so the app fell
   back to a path that exists on no other Mac and silently did nothing.
4. **Windows ran the Microsoft Store placeholder** when that was the only
   `python`: a console flashed and closed with no message.
5. **Anything started through `.venv/bin/uvicorn` broke when the folder moved**:
   the script's first line names where the venv was built. `run.sh` then
   printed "the server exited during start-up" and discarded the reason.
6. **`make package ARGS="--wheels mac"` could not resolve**: one platform tag
   per target, and scipy's Apple-silicon wheels are tagged macOS 12 and later.

Also: the engine log was appended, so a failure showed an earlier day's lines
as its reason; a zip with no key failed its own self-check instead of saying
AI was off; two double-clicks ran two installs into one folder.

**Fix:** one installer for every entry point (`app/launch.py`; `run.sh` and
`make setup` call it with `--setup`). It writes a marker inside `.venv` only
after every dependency imports, keyed to a hash of `requirements.txt`, and
repairs or updates whenever that does not hold; shows pip's progress and keeps
all of it in `data/app/install.log`; takes a lock; starts a fresh engine log;
clears quarantine on its own app bundle once the reader has run it. Entry
scripts run a Python before trusting it, and pause on failure. Everything
starts through `.venv/bin/python -m`. The package carries `Start
WhyChain.command` and `start-whychain.sh` beside the Windows file, a rewritten
`START HERE.txt`, a SHA-256, and a self-verified zip; the answer key, audit and
feedback stay out. CI's first-run job now goes through each system's
double-click file and then breaks an install on purpose to prove it is
repaired. Tested here from the zip and from a clone-equivalent copy, cold,
bare, killed mid-install, concurrent, requirements changed, folder moved, and
with no key. `tests/test_portable.py`, verified to fail on the old scripts.

**Not tested on Windows hardware.** Every pinned dependency was resolved
against the package index for Windows x64 on 3.12, 3.13 and 3.14, and the CI
job above runs it on a clean Windows machine the first time this branch is
pushed with a pull request.

### B-064 · A scenario summed withheld causes and showed the total to a reader who could not see them
**Found:** 2026-09-25, by `make audit` after B-056 was fixed · **Severity:** P1, security · **Status:** fixed

A South-only reader asking about all regions, 13 to 16 Aug, was shown "What
happens if the external pressure persists: −₹27,072 a day". That is the West
weather and SKU causes, both withheld, added together. **Root cause:** the
projection withheld a scenario only if its text named a withheld cause, and the
sustained-external estimate is a sum that names none. The audit's check looks
for the weather cause's exact figure, which a sum never equals, so it passed by
coincidence until B-056 removed the SKU cause and the sum became the weather
figure alone. **Fix:** every scenario carries `derived_from`, the causes it was
computed from, and entitlement withholds by that. T-32 again: a figure computed
from a withheld one is withheld.
`test_a_scenario_built_from_withheld_causes_is_withheld_too`, verified to fail
without the fix.

### B-056 · A cause about one SKU was verified and sized as if it covered the whole region
**Found:** 2026-09-25, independent review, recomputing `?demo=trap` from the warehouse · **Severity:** P1, flagship demo · **Status:** fixed

On West, 13 to 15 Aug, "Introductory pricing ended on a SKU launched three
weeks earlier" is shown verified at **−₹23,391 a day**. SKU PC-1099 in the West
fell **₹5,304 a day** over the same windows (₹60,684 to ₹55,380, recomputed by
hand from `pos_txn` with the contract's lineage). The page overstates it about
4.4 times, and the overstatement is most of the 177% overlap the page then has
to explain.

**Root cause:** `from_operations` builds a `Candidate` from the note's region and
whatever `_scope` can read of channel, device and category. `Candidate` has no
SKU field, and the note names none of the three, so the candidate is the whole
West region. Its difference-in-differences then measures West against the other
regions, which is the release and the rain falling, and passes.

*Corrected while fixing:* the first write-up said `comp-pricecut-aug` was also
widened. It was not: `_scope` reads "personal care" and it is tested on that
category. Its rejection is a genuine placebo failure (quiet windows on personal
care range to −25.6%, partly because the PC-1099 launch lands in that category),
so a true −9% effect is not distinguishable from noise there. That is the
method working, and it stays.

Scored against `data/ground_truth/cases.json` for this window: release and rain
verified correctly, the promotion decoy rejected correctly, the competitor price
cut rejected wrongly, and the SKU event verified when its own case expects
`cannot_verify` (three weeks of history) and it ran in every region, so no
region is an unexposed control.

**Fix:** `Candidate` carries `sku`, read from the note by `_sku` against the
SKUs the warehouse holds (the note's identifier, `pc1099-launch-dip`, names it).
Every consumer narrows through one helper, `narrow_to`, which returns nothing
rather than everything when the panel lacks a dimension. Tested on its SKU, the
event has no history before launch, so timing and placebo cannot run and it is
`cannot_verify`, which is what its own case expects. The flagship now verifies
two causes at 113% overlap instead of three at 177%, and confidence rises from
0.79 to 0.90 because coverage is no longer discounted for a borrowed movement.
`tests/test_demo_answer_key.py`, verified to fail before the fix. T-33.

### B-057 · A rollback note became a candidate cause of its own
**Found:** 2026-09-25, independent review · **Severity:** P1 for the decision view's "One day, asked about the app" · **Status:** fixed

West, app, 12 to 20 Aug verifies `rel-4.05` at −₹22,792 a day **and** `4.05` at
**+₹13,936 a day**, then abstains because "rel-4.05 and 4.05 move West in
opposite directions".

**Root cause:** the 19 Aug release-log entry is "Release note 4.05: rollback of
the card entry component applied...". `_identifier` takes the last token with a
digit before the colon, `4.05`, which is not `rel-4.05`, so the fix is tested as
a new cause and the recovery it produced verifies.

**Second consequence:** the 13 to 15 Aug finding recommends "Apply release
rollback", while the warehouse, which runs to 1 Sep, records that rollback as
applied on 19 Aug. A decision card should check whether its lever has already
been pulled.

**Fix:** a note that rolls back, reverts or hotfixes is not a candidate
(`is_remediation`). It is linked to the release whose version it names
(`remediations`), and the card carries `already_actioned`: the page says
"Already done on 19 Aug, per OPS006805. What is left to decide is whether it
worked." The 12 to 20 Aug app window now explains instead of abstaining.

### B-058 · East checkout conversion and AOV read order times without the timezone correction
**Found:** 2026-09-25, independent review · **Severity:** P2 · **Status:** fixed

The East extract lands 5.5 hours ahead (the reason `tz_normalise` exists, and
why B-019 added it to `orders`). `checkout_conversion` declares
`transforms: []` and `aov` declares `[dedupe_order_id, net_returns]`. On 15 Aug,
East shows 72 to 306 sessions an hour from 07:00 to 11:00 with **zero** orders,
and orders at 01:00 to 05:00 with no session row, which the join from sessions
drops. The "East checkout conversion 100% below expected" findings on 15, 20 and
30 Aug are this artefact. AOV East is on a day boundary 5.5 hours off revenue's,
so revenue is not orders times AOV there, and the series ends on a partial day.
T-34.

**Fix:** both contracts declare `tz_normalise` (version 2); conversion lists
`pos_txn` first because transforms apply to the first upstream source. East
hours now read 2 to 10%. The `hourly` scenario moved from 29 Aug to 25 Aug:
the 29th was flagged only because of this artefact. **Residual, recorded:** nine
single quiet hours a year still read "100% below expected", genuinely zero
orders from about thirty sessions. That is a small-denominator limit of an
hourly ratio, and the right fix is a minimum-session floor in the contract's
materiality, not a timezone change.

### B-059 · "Last 90 days" meant a different window for each filter
**Found:** 2026-09-25, independent review · **Severity:** P2 · **Status:** fixed (`_latest_day`)

`/api/triage` anchors the window at `max(f["end"] for f in findings)`, after the
metric and region filters. Unfiltered, 90 days starts 1 Jun; filtered to
on-time delivery, whose newest finding ends 14 Aug, it reaches back to 18 May.
The comment says "the last day the warehouse actually holds", which is the right
anchor and is not what the code reads. Non-negotiable 4 in spirit: a filter
changed what was considered, not only what was drawn.

### B-060 · One event sized three ways, and a total that counts a contradicted finding
**Found:** 2026-09-25, independent review · **Severity:** P2, finance reader · **Status:** fixed

West, 13 to 15 Aug: the inbox says **₹41,224 a day** (mean shortfall against
expected over the flagged days), the finding's headline says **₹52,952** (worst
day against expected), and the causes are sized against **₹36,381 a day** (the
window against the fortnight before). All three are correct and labelled; the
inbox figure appears nowhere on the page it opens, and the fortnight before sits
on the PC-1099 launch surge (every region's August runs about 35% above July).

"Shortfall in these findings, ₹10,08,906" reproduces exactly, and includes
₹1,36,664 from the North finding the engine marks **Contradicted** (the ledger
says the revenue was there) and ₹1,13,820 of on-time delivery priced at a
declared rate. Uncontested revenue shortfall is about ₹7.35 lakh.

**Fix:** the tile is "Revenue shortfall in these findings", over rupee metrics
not disputed by the ledger, with the disputed and contract-rate amounts shown
beside it. It covers every finding in the queue, signed or not, so it no
longer changes when verdicts arrive. The finding page shows the queue's figure
under the worst day ("₹41,224 a day across the 3 flagged days").

### B-061 · One scenario name, two windows, and `?demo=` ignored on the decision view
**Found:** 2026-09-25, independent review · **Severity:** P2, demo risk · **Status:** fixed

`ui/app.html` `SCEN` and `ui/index.html` `DEMOS` are separate lists. "One day,
asked about the app" is 12 to 20 Aug on `/` (nine days, and Unknown, B-057) and
15 Aug on `/workbench` (explained). "Scoped to South" and "Detected, not
diagnosed" also differ. `/?demo=trap`, the link the handoff rehearses, opens
the plain inbox; only `/workbench?demo=` and `/kpi/...?demo=` apply it.

**Fix:** decision-view scenarios carry ids; `/?demo=<id>` opens the finding, or
the workbench for ids only it has. "One day" became "The same finding, asked
about the app", on 13 to 15 Aug.

### B-062 · Net revenue and AOV count test accounts; orders does not
**Found:** 2026-09-25, independent review · **Severity:** P3 · **Status:** fixed for AOV; **net revenue deferred by decision**

0.4% of `pos_txn` rows are `is_test` (7,272). `orders` declares
`exclude_test_accounts`; `net_revenue` and `aov` do not, and the Metrics page's
definition of net revenue does not say so. Small in rupees, but it is the
revenue identity again, and the Metrics page is where a finance reader checks
definitions.

`aov` now excludes them, so its numerator and denominator count the same
orders. `net_revenue` is left as it is until after 29 Sep: changing it moves
every rehearsed figure (−17.2% appears 36 times and ₹36,381 eleven times in the
pitch material) by about 0.4%. One line in `contracts/net_revenue.yml` when it
is done, then re-read the deck.

### B-063 · The demo cases were never scored against their own answer key
**Found:** 2026-09-25, independent review · **Severity:** P1, process · **Status:** fixed (`tests/test_demo_answer_key.py`)

`make bench` scores 160 generated single-cause panels. The seven demo cases in
`data/ground_truth/cases.json`, including the multi-factor one every rehearsal
opens, are checked by `/uat`, `make smoke` and `tests/test_scenarios.py` for
*consistency* (page equals API, promised verdict appears) and never for
*correctness* against the causes planted there. That is how B-056 reached the
flagship. T-35.

### B-055 · A Teams card said "awaiting approval" over a decision already taken
**Found:** 2026-09-24, in the interactive pass after accepting a decision · **Severity:** P2, demo risk · **Status:** fixed

**Root cause:** `_adaptive_card` wrote a fixed heading and never read the audit
trail, so after the owner accepted, the card a manager would read in Teams
still showed the decision as pending. It also printed the engine's action text
("for channel app, device mobile"), "Ecommerce lead" and ISO dates where the
page says otherwise. **Fix:** the card reads the decision's latest audit entry
and states it, with the page's wording and date format.
`test_the_teams_card_carries_the_decision_as_it_stands`, verified to fail
without the fix.

### B-054 · A question about a month opened on its last day, not on the fall
**Found:** 2026-09-24, testing the questions for the demo · **Severity:** P2, demo risk · **Status:** fixed

**Root cause:** the workbench handed the reading to the page with `day: d.end`.
"Why did net revenue fall in North in June?" read correctly as 1 to 30 June and
opened 30 June, while the fall was on the 10th. **Fix:** the page opens the
largest flagged move the engine found inside the window asked about, falls
first, and says which day it opened.

### B-053 · One finding page, two answers
**Found:** 2026-09-24, by the extended value sweep in `/uat` · **Severity:** P2 · **Status:** fixed

Three places where a page contradicted itself:

- **Quotes.** The page draws from the deterministic pass, then `refine()`
  replaced the whole diagnosis with the model's pass. On petroleum West, 13 to
  15 Aug, the button said "6 customer quotes" and its drawer showed none: the
  model's quotes had failed the character check and been dropped. `refine()`
  now swaps only the prose, which is all it exists to do.
- **Calendar.** "All 11 events" listed a capped 11 of 13. It now says "The 11
  nearest of 13 events" when capped.
- **Workbench causes tile.** A contradicted finding's tile read "Causes 1/1"
  beside "No cause is proposed". A contradicted finding now shows none.

Also aligned in the same pass: confidence reads High in the workbench as on the
decision view (it said Strong), metric names, "E-commerce lead", the cost
caption (a reference rate, not what the run cost), and the Ask box's
clarifications, which printed metric ids.

### B-052 · An unknown finding hid a decision the service would accept
**Found:** 2026-09-24, by the value sweep added to `/uat` · **Severity:** P2 · **Status:** fixed

**Root cause:** the engine builds decision cards for every verified cause with
a lever, whatever the verdict. On petroleum South, 11 to 15 May, one cause
passed its tests but covered 7% of the movement, so the verdict was unknown,
and the response carried a card with a ₹6,26,277-a-day recovery and an
approval route. The unknown page never rendered decisions, so the owner could
not see an action that `/api/decision` and the Teams card would both accept.
The page and the service disagreed about whether a decision existed.

**Fix:** the unknown page shows the card under "What can be done now", with a
note that the cause is part of the movement, not the explanation of it. This
follows the page's own rule for partial causes: hiding evidence the engine
found is its own error. The value sweep in `/uat` now compares every figure on
every finding in all three industries with the engine, including recoveries,
and failed on this before the fix.

### B-051 · The workbench lost the finding it was opened from, and its "Open findings" went nowhere
**Found:** 2026-09-24, adding a Back button on request · **Severity:** P2, demo risk · **Status:** fixed

**Root cause:** "Open in workbench" linked to `/kpi/<metric>` with nothing else,
so a presenter on West, 13 to 15 Aug landed on all regions over the default
ninety days and had to find the finding again on camera. The workbench already
knew how to open on a day (the triage queue hands one over through
`STATE.pending`); the link never used it. Separately, the breadcrumb's "Open
findings" was `href="#"` with no handler, a link that did nothing.

**Fix:** the link carries region, slice, a year of range and the headline's day,
and the workbench reads `day` on boot. "Open findings" goes to `/workbench`.
Every page with a breadcrumb has a Back button: it returns to the page before
when that page was in the app (the decision view marks its history entries,
the workbench marks the ones it pushes, since its first entry also carries a
state), and otherwise goes to the findings rather than off the app.

### B-050 · Two decoy figures that read alike, and one cause listed twice
**Found:** 2026-09-24, checking the track record before the finale · **Severity:** P2, Q&A risk · **Status:** open, documented

**What:** the benchmark's `negative_control_rejection` is 87.5%: of the 64
cases planted with a decoy, the engine verified that case's *own* decoy in 8.
The inbox's "a planted decoy got through in 14" counts, among the 68 answers
that named a cause, those that verified *any* decoy, including one planted for
a neighbouring case in the same panel. Both are right as defined. Quoted side
by side they look like a contradiction, and 87.5% alone reads as more than it
is. Say the strict one: 14 of 68 answers carried a decoy.

Separately, 6 benchmark cases list the same verified id twice
(`bench-04-south-1` and five more). **Root cause:** `from_operations` makes one
candidate per document, and the generator writes a release log and an ops note
naming the same release, so the candidate is built and verified twice.
`explained_movement` keys by id, so the explained share and the confidence are
not double counted; only the list repeats. The track record's exact count uses
a set and is unaffected; an earlier "97%" that did not was withdrawn. No live
finding in the three warehouses has a duplicate (12 checked).

**Fix, deferred past the finale:** dedupe candidates by id in `from_operations`,
merging descriptions. It changes the benchmark lists and possibly prompts, so it
needs a re-bench and a re-warm, which is not a risk worth taking this week.

### B-049 · The fair target named a cause withheld by entitlement
**Found:** 2026-09-24, by `make audit` the day the fair target shipped · **Severity:** P1 · **Status:** fixed

**Root cause:** `fair_target` was computed from the full evidence and attached
after the projection, the same way the evidence fingerprint is. The fingerprint
is a hash and discloses nothing; the fair target lists causes by name with their
rupee sizes. A reader entitled to South saw the Mumbai weather cause and its
value on a finding whose causes panel correctly withheld it. The same trap as
the four surfaces in the audit check's docstring: a new field added after the
projection is outside entitlement until someone puts it inside.

**Fix:** when the projection withheld any cause, the fair target is withheld
whole, with a notice and no figures. Dropping only the withheld factor would not
do: the net less the visible factors recovers its exact value. `/api/adjustment`
refuses under partial entitlement for the same reason.
`test_withheld_whole_under_partial_entitlement`, verified to fail with the guard
disabled.

### B-048 · The evidence drawer showed tickets unmasked
**Found:** 2026-09-24, adding PAN and UPI patterns · **Severity:** P1 · **Status:** fixed

**Root cause:** personal data was masked at the quarantine boundary, before a
ticket became prompt tokens, and nowhere else. `/api/document` returned the raw
text, so an email or phone number the model never saw was shown to whoever
opened the source in the drawer. Citation spans are measured on the masked text,
so on a ticket that held personal data the highlight also landed in the wrong
place. UPI handles (no dot after the @) and PAN numbers were not caught at all.

**Fix:** the endpoint masks with the contract's declared classes and says what
it scanned for and what it masked, and both drawers print that. UPI and PAN
patterns added, UPI ahead of the phone pattern so a number-based handle is
masked whole. `tests/test_personal_data.py`, verified to fail with the endpoint
returning raw text. No synthetic ticket holds personal data, so no prompt, and
no cached answer, changed.

### B-047 · "These causes overlap" named one of two reasons their sizes exceed the fall
**Found:** 2026-09-24, from a question in review · **Severity:** P2, Q&A risk · **Status:** fixed in the page

**Symptom:** three causes of −₹26,821, −₹23,391 and −₹14,169 a day against a net
fall of −₹36,381: 177%, and the page said only that they overlap.

**Root cause:** two things make the sizes exceed the fall. The pricing cause is
unscoped, so its sales sit inside the app and store slices the other two are
measured on: overlap. And each cause is sized by difference-in-differences
against regions it did not touch, which rose over those days, while the net fall
is against the fortnight before: the release bug is sized at −₹26,821 against an
app channel whose raw fall was −₹23,763. The second is the larger effect.

**Fix:** the decision view says both. The engine's confidence caveat still says
"overlap" only; changing it would change prompt inputs and the demo cache, so it
is left for after the finale. An additive (Shapley) split is the real fix.

### B-046 · Files read without an encoding break on Windows
**Found:** 2026-09-24, preparing the portable package · **Severity:** P1 on Windows · **Status:** fixed

**Symptom:** none on macOS or Linux; predicted, not observed, on Windows.

**Root cause:** seven `read_text()`, `write_text()` and `open()` calls named no
encoding, including the one in `ContractRegistry` that loads every contract.
Python on Windows decodes those as cp1252, so any non-ASCII byte in a contract,
the rupee sign among them, fails or garbles on load.

**Fix:** `encoding="utf-8"` at all seven sites, found with an AST scan rather
than grep so multi-line calls were not missed. The launcher also runs every
child process in UTF-8 mode (`PYTHONUTF8=1`), which covers printing ₹ to a
Windows console.

### B-045 · A fixed "no gap" sentence contradicted one of the verdicts it described
**Found:** 2026-09-24, content review of the decision view · **Severity:** P2 · **Status:** fixed

**Root cause:** the decision view printed "nothing external warned of this" for
every `no_gap`. The engine returns `no_gap` from three places, and one of them
means a warning *was* published and the planning process *did* receive it. The
page would have told a reader the opposite of the engine.

**Fix:** a neutral heading per verdict, with the engine's own reason beneath it
in every case. Trap T-31.

### B-044 · "No cause survived testing" over two causes that had
**Found:** 2026-09-24, value test of the decision view · **Severity:** P1 · **Status:** fixed

**Symptom:** West, app channel, 12 to 20 Aug. The headline said no cause
survived testing; the engine had verified two, pulling in opposite directions
(a release bug and its rollback) and together covering 39% of the movement, which
is why it abstained.

**Root cause:** the Unknown layout assumed an abstention means nothing was
verified, and did not render verified causes at all, hiding evidence the engine
found. The value test compared the causes on screen with the API and failed.

**Fix:** the headline says how many causes passed and how little they explain,
and the page shows them sized, under "Passed testing, but not enough to explain
it", with the causes set aside for the slice beside them.

### B-043 · The decision view sent an empty entitlement and every sign-off was refused
**Found:** 2026-09-24, interaction test · **Severity:** P1 · **Status:** fixed

**Root cause:** the page built its request body from the URL, including
`entitled: ""` when the URL had none. The server reads a present but empty
entitlement as "entitled to nothing", on purpose (an earlier fix closed the hole
where `entitled=` switched the restriction off), so it refused.

**Fix:** the client drops empty fields. The server rule stays, and
`test_an_empty_entitlement_in_a_body_grants_nothing` holds it.

### B-042 · A scoped reader's ranking crashed the workbench render
**Found:** 2026-09-24, clicking every scenario · **Severity:** P1, on stage · **Status:** fixed

**Symptom:** `?demo=entitled` showed the headline and nothing below it.

**Root cause:** for a reader entitled to some regions the server withholds the
ranking whole, returning `{"withheld": true, "reason": ...}`. `rankingBlock`
read `.exact.length` from that notice and threw, and because `render()` builds
the page as one string, the throw took every section below the headline with it.

**Fix:** the withheld ranking renders as its own section saying why.

### B-041 · The demo's entitlement refusal crashed instead of refusing
**Found:** 2026-09-24, clicking every scenario · **Severity:** P0, demo moment 4 · **Status:** fixed

**Symptom:** `?demo=blanked`, a South-only reader asking about the West, showed
the rail and an empty page.

**Root cause:** `/api/overview` refuses a region outside scope with 403, before
the series is ever asked for. The console replaced the refused response with
`{kpis: []}`, and `renderNav` then read `roots.forEach` from it and threw. The
refusal the scenario exists to show was never reached. A first fix that asked
for the overview again without the region also adopted that answer's region
list, which silently reset West to "all" and answered a different question.

**Fix:** on a refused overview the rail's metric list is fetched without the
region, its dimension lists are not adopted, and the refusal is rendered at
once through the same function the series refusal uses.

### B-040 · `make warm-ai` warmed nothing and said it had
**Found:** 2026-09-24 · **Severity:** P0 for the demo · **Status:** fixed

**Symptom:** every case failed with 404 "no data for that slice", then the script
printed "Re-running any of these is now instant" and exited 0.

**Root cause:** it called `diagnose()` as a function. When the scope filters were
added to its signature, the parameters the script did not pass arrived as
FastAPI `Query` objects, which are truthy, so every case asked for a channel,
device and category that do not exist. The cache was warm only because earlier
sessions had clicked through by hand; a prompt change would have left six
scenarios generating live, about 30 seconds each, on stage.

**Fix:** it goes through HTTP with `TestClient`, covers every scenario the two
views open for all three readers, re-requests each to prove it is answered from
cache, and exits 1 naming any case that is not. Trap T-29.

### B-039 · "Why nobody saw it coming" opened a metric that cannot be diagnosed
**Found:** 2026-09-24 · **Severity:** P1, on stage · **Status:** fixed

**Root cause:** the scenario pointed at on-time delivery, a ratio. The signal gap
is computed inside a full diagnosis, and a ratio has none, so the button landed
on "Detected, not diagnosed" with no gap anywhere on the page. It had done so
since the scenario was added.

**Fix:** it opens net revenue, West, 13 to 15 Aug, where the gap is found (nine
warnings, up to 72 hours ahead), and scrolls to that section.
`tests/test_scenarios.py` fails on the old coordinates, verified.

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
