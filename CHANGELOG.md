# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

## [Unreleased]

### Added, the model earns a third job and the economics the brief asks for

- **`whychain/corroborate/query.py`, model-proposed complaint vocabulary.** An
  operational note and the complaint it produces are written in different
  registers, and bridging them is a language problem the keyword table could
  only solve by having synonyms written into it by hand, per industry, by a
  person. The model proposes them instead: given "TA-4411: Turnaround at the
  West refinery extended by nine days; downstream allocation reduced to 55 per
  cent of indent" it returns *"no stock dry out allocation cut supply delayed"*,
  which is the dealer's register and not the terminal's. Retrieval underneath is
  unchanged, the proposal is filtered to language before use, and the
  deterministic query stays in place beneath it, so a bad expansion retrieves
  less rather than retrieving wrong. It cannot reach a number
- **Used on the margin, not by default.** The expansion runs only where the
  deterministic query's best match scores below `REGISTER_FLOOR`, which is what
  a register mismatch looks like from inside retrieval. Retail's release notes
  share vocabulary with retail's tickets and spend nothing; petroleum's and
  power's do not and spend one call
- **`whychain/llm/cache.py`, a content-addressed cache.** The brief names
  caching under LLM economics and it is also the difference between a model path
  that can be demonstrated and one that cannot: a cold diagnosis on a local 7B
  made ten constrained calls and took over ten minutes. Keyed on everything that
  could change the answer — model, backend, system, user, schema, token ceiling
  — so a key that omitted the industry cannot serve one vertical's reading under
  another's heading. Hits are counted separately from calls on the receipt, and
  the token figures still report what the reading costs uncached, because a
  receipt claiming free work is the same dishonesty as an uncalibrated
  probability
- **A free-tier guard.** `WHYCHAIN_LLM_FREE_ONLY` refuses any model id without
  the provider's free marker. A key with credit on it bills happily for a
  mistyped paid model and the mistake is invisible until an invoice arrives, so
  this is a refusal rather than a warning: the backend reports itself
  unavailable, the engine takes the deterministic path, and the console says why
- **Verified TLS that works on a stock macOS Python.** A python.org build ships
  without a usable root store, so every hosted call failed
  `CERTIFICATE_VERIFY_FAILED` until someone ran `Install Certificates.command` by
  hand. `certifi` is used when importable; verification is never disabled
- **Transient provider errors are retried.** 429 and 503 with geometric backoff,
  honouring `Retry-After`. A free tier is measured in requests per minute and a
  diagnosis makes several in a row, so rate limiting is the ordinary case
- **A bounded call and a stated fallback.** `WHYCHAIN_LLM_TIMEOUT`, 20 seconds,
  after which the deterministic path stands in and says so
- **`Task.EXPAND` joins the routing table**, so all three model jobs are named,
  tiered and separately overridable
- **Google Gemini needs no code.** `OpenAICompatibleModel` already speaks the
  API Gemini's compatibility endpoint implements, so a hosted, materially faster
  backend is four environment variables. The trade is stated rather than hidden:
  inference leaves the boundary, which is what the local open-weight default
  exists to avoid. `.env.example` carries both

### Added, the access policy is enforced rather than declared

- **`row_filter` is compiled from the contract** and fails closed. It was a
  hardcoded `WHERE region IN (?)` that happened to match what every contract
  declared, which made the field documentation rather than configuration
- **`column_masks` are applied** to any frame handed out under a contract, at the
  projection rather than in the SQL: the calculation may legitimately need a
  column a reader may not see, and removing it from the query would change the
  answer rather than restrict the view
- **`domain_restriction: [pii]` redacts at the quarantine boundary**, the last
  point before untrusted text becomes prompt tokens. Emails, mobile numbers,
  Aadhaar- and card-shaped runs. Citations are checked against the redacted text
  so a model cannot quote back what it was never shown, and injection scanning
  runs first so a payload beside an email keeps its flag
- **What cannot be enforced is reported.** `unenforceable_policy` names masks
  pointing at columns this source does not have and domain classes with no
  patterns, and `make audit` prints it. A mask that protects nothing looks
  identical to a working one from outside
- **Three new security checks** drive the endpoints a reader actually hits. The
  existing entitlement check passed throughout B-022 because it covered
  `kpi_series`, which the diagnosis path does not use

### Changed, claims trimmed to what the code does

- **"A bounded feedback loop" is now "a governed correction workflow"**, because
  applying a proposal is manual and nothing in the engine consumes one
- **The README states plainly what is simulated**: six source tables from one
  generator (grain is heterogeneous, origin is not), an external feed with real
  provenance and generated rows, an indicative cost rate, and entitlement that
  enforces a claim because there is no identity provider
- **The rupee cost carries its basis.** One reference rate is wrong for a
  self-hosted model, where cost is compute, and for a free tier, where there
  isn't one
- **A short series returns a `sparse_history` verdict rather than HTTP 422.** The
  refusal to fit is right; calling it a bad request was not. The level and
  direction are reported, and nothing that needs a seasonality is — no bands, no
  expected line, no anomalies

### Fixed, entitlement, which was the requirement it was built to satisfy

- **A reader entitled to one region received another region's causes (B-022).**
  The analyst branch merged the raw result back over the filtered one, so the
  default persona saw every withheld cause beneath a notice saying they were not
  shown. Four more surfaces carried the same figure in different clothes: the
  per-cause map, the scenarios, the ranking table under a non-region dimension,
  and a second copy of the narrative's sentences in the validation block
- **A region outside entitlement is now refused before anything is computed**,
  with a 403 carrying the escalation role. Redaction after computation could not
  be made airtight on this shape of answer -- one surface was still leaking after
  three passes -- and refusing the question removes the class. The panel still
  holds every region, because difference-in-differences needs the unexposed ones
  as a control: using a region as a statistical control is not the same act as
  disclosing its figures to a reader
- **`/api/candidates` enforces entitlement**, which it previously did not take at
  all -- a way round the restriction applied on its neighbour
- **`entitled=` means entitled to nothing**, not unrestricted
- **The redaction notice no longer quotes the redacted figure.** It was the exact
  quantity the entitlement protects, and repeatable often enough to enumerate
  every region's contribution one query at a time

### Added, a question box, and the model's fourth job

- **`whychain/intent/`, plain-language questions.** *"Why did West revenue drop
  last week?"* previously had nowhere to go: the console required the reader to
  know the KPI id, the region and the window before they could ask anything,
  which is the analyst's interface rather than the business user's. The brief
  names "LLM-assisted intent understanding" as its own solutioning area, and
  this is it
- **The proposal is constrained twice.** `kpi_id` and `region` are JSON-schema
  enums built from *this* deployment's registry and the regions the caller is
  entitled to, so a metric the business does not have is unrepresentable rather
  than filtered out afterwards; and everything that does come back is checked
  again against the registry, the entitlement and the warehouse's actual date
  coverage. Nothing reaches a number: the output is a query, and the engine then
  runs exactly as if the form had been filled in by hand
- **Ambiguity is asked about, not guessed at.** *"Why are sales down"* returns
  *"Do you mean net_revenue or orders when you say 'sales'?"* and runs nothing.
  The model's uncertainty routes into the clarification mechanism objective 5
  already required, rather than into a confident answer to a question nobody
  asked. The reading is shown before the answer, so a misreading costs a click
- **Anchored on the data, not the wall clock.** "Last week" resolves against the
  last day the warehouse holds; against the real today every question would ask
  for a window that does not exist
- **Token ceilings are per task and centralised.** They were sized for a model
  that emits the object and nothing else, which the open-weight reasoning models
  on a free tier are not -- they spend most of a budget working before they
  answer, and a truncated object is indistinguishable from a refusal. The intent
  parser also scans for the first balanced JSON object rather than assuming the
  whole body is JSON

### Added, the external record reaches the cause card

- **Every verified cause now carries the warnings published over the slice it
  touched.** The section beside it asks what the *company* wrote down, which for
  a retailer is usually the whole story: the cause was something it did to
  itself. For a fuel marketer or a generator it is not, and the card said
  "Nothing in the record describes this" for precisely the causes those two
  verticals exist to demonstrate — while an IMD cyclone warning with a named
  publisher and a measured lead time sat one table away. A port-closure cause in
  East now shows four red warnings at 3.5 to 3.7 days of notice, each naming the
  India Meteorological Department and whether it was public
- **Foreseeability stays a separate question, and the card says so.** What was
  published is context for judging the cause in front of you; whether the
  planning cycle consumed it is the signal-gap verdict, and conflating the two
  would let "a warning existed" read as "the business ignored it"

### Changed, the console renders before the model does

- **Two passes, and the first is always deterministic.** Every number on the
  page is computed without a model, so a reader waits for none of them. A pinned
  backend is fetched second and swapped in when it lands, and until it does the
  page says the figures are final and the prose is still being written. This is
  also the honest demonstration of the central claim: the figures settle first
  and stay put while the prose changes around them
- **The console defaults to the deterministic path.** A latency decision, stated
  as one. The reader turns the model on for a diagnosis when they want to watch
  it read and write
- **The scope control opens on the whole estate** rather than on one region,
  which is what the watchlist beneath it was already showing
- **`Auto — whatever is configured` reworded to `Auto — routed by task
  requirement`**

### Fixed, correctness

- **An explicit "no model" was read as "decide for me" in three places (B-021),
  so `backend=none` called the model anyway.** A deterministic diagnosis took 78
  to 235 seconds against 1.1 in-process, and the console sat on "Testing
  candidate causes" for minutes. `UNSET` now separates "nobody said" from "no
  model"; the deterministic path is 0.9s and zero calls
- **The suite made live model calls** once expansion was wired in, taking it from
  18 seconds to over ten minutes with a result that depended on whether Ollama
  was running. `tests/conftest.py` forces the deterministic backend
- **Over-explanation scored as perfect coverage (B-020).** Three causes summing
  to 188% of the movement were detected, clamped and the finding discarded, so
  the largest component of the confidence score paid full marks exactly where the
  split between causes cannot be established. The overlap ratio is returned and
  the share divided by it. Held-out ECE **0.117 → 0.069** raw, **0.099 → 0.042**
  calibrated, with every other benchmark rate unchanged. The discount is
  deliberately kept out of the abstention gate: crossing `MIN_COVERAGE` with it
  moved the boundary at which the engine refuses without anyone choosing to, and
  cost 16 abstentions and 34 points of abstention precision before it was caught
- **The narrative asserted a remainder that did not exist**, saying causes
  accounted for the whole movement and that the remainder was unexplained in one
  sentence
- **Corroboration was structurally impossible for every externally-caused
  event.** `related_issues[residual] = ()` discarded every retrieved document
  before it was read, so the answer was identical whether the record was silent
  or full. `TA-4411` went from "Nothing in the record describes this" to twelve
  supporting documents
- **The model extractor read every industry in retail's vocabulary.** Prompt,
  schema enum and rule-table fallback all named `checkout_failure` and
  `stockout` whatever business was selected — and this is the path an API-keyed
  run takes, so it would have surfaced the moment a backend was switched on for a
  demo. All three now build from the vertical's `Vocabulary`
- **`Operations circular OC-2026-14: …` was read as the candidate
  `Operations`**, heading a decision card with a common noun and collapsing every
  circular in the corpus into one candidate
- **The narrative validator rejected figures for their punctuation.** `\d[\d,]*`
  also swallows a trailing comma, so "accounts for ₹35,323, which is all of it"
  scanned as the numeral `₹35,323,` and the sentence was dropped as fabricated.
  Latent while the template avoided the construction; it would have silently
  dropped model-written sentences
- **Corroboration ran for candidates nobody reads**, one wasted model call per
  rejected candidate
- **Margin labels broke mid-word** — "Prior episod / es" — and the rail held one
  fixed width until it dropped away entirely

### Added, the stages the handoff listed as empty

- **`whychain/signalgap/`, Answer 2.** Reads `ext_signals` against the
  contract's `signals_consumed`, gated on public availability, actionable
  severity and lead time. All four verdicts are reachable from the generated
  warehouse: `gap_found`, `no_gap`, `not_foreseeable`, `coverage_unknown`.
  Recurrence is counted as episodes rather than rows, so a five-day cyclone is
  one precedent
- **`whychain/rank/`, two tracks that are never merged.** Track A is exact
  from the price/volume/mix identity and its rows are stateable; track B is a
  standardised ridge over the driver series and every row is `HYPOTHESIS`,
  labelled `CORRELATIONAL`, and barred from becoming a cause. Rejected
  candidates cannot re-enter through it (T-12)
- **`whychain/narrate/`, brief, writer, validator.** A constrained
  `claude-opus-5` call and a deterministic template implement one protocol and
  pass through one validator: binding, numerals, entities, rejected-as-cause.
  Rejected sentences are dropped and counted, never repaired; a failed call
  falls back to the template and the receipt says so
- **`whychain/feedback/`, a bounded learning loop.** Corrections never edit a
  run and never move a computed value. They propose changes to business-owned
  inputs, require two independent submitters, and go contested rather than
  averaged when readers disagree. Named misses become labelled regression cases
- **`on_time_delivery` registers the S&OP document**, which is what makes the
  flagship gap case resolve rather than returning `coverage_unknown`
- **`emit_ext_signals` emits scenario-declared warnings**, so `not_foreseeable`
  is producible from the feed rather than only from a fixture; a verdict the
  data can never reach is a verdict the demo does not have

### Added, two externally-driven industries and a switcher

- **Petroleum marketing and power generation, beside the original retail
  vertical.** Both were chosen because their metrics move for reasons the
  business does not control: crude benchmarks, excise notifications, refinery
  turnarounds, pipeline integrity and port closures on one side; regulatory
  tariff orders, fuel supply, grid constraints and weather-driven load on the
  other. Retail is the contrast — mostly moved by things it did to itself
- **A national policy event is a first-class scenario, not an oversight.** An
  excise revision or a tariff order lands on every region on the same morning,
  so there is no unexposed region and difference-in-differences genuinely cannot
  verify it. Both verticals plant one deliberately, labelled `cannot_verify`,
  alongside regional events that must verify. An engine returning a confident
  cause for the national ones would be wrong
- **An industry switcher in the console header.** Contracts, warehouse, labels,
  personas and the dimension names all re-scope beneath it. The industry leads
  the cache key: a key that omitted it would serve one vertical's rows under
  another's heading, which T-06 calls a P0
- **The engine's three retail vocabularies are now per-industry configuration.**
  The issue terms and scope terms in corroboration, the driver mappings in the
  action stage, and the plan-candidate column names in the candidate scanner.
  Same algorithms, same ordering rules; the tables are supplied rather than
  literal, and every default is retail's
- **`Grain.noise_model`, declared per contract.** `binomial` when the numerator
  is a subset of the denominator, `counting` when it is metered separately and
  keeps its own variance. Below a tenth the two agree; at 91 per cent they
  differ by three and a half, which is one observation in fifteen flagged
- **`make gen-all` builds every industry.** Retail's warehouse regenerates byte
  for byte after the generator was parameterised, and the benchmark is identical
  on every rate

### Fixed, correctness

- **The brief's action chain broke at "expected impact" for two of three
  industries.** `RECOVERY_SHARE` held retail's four levers, so every decision
  card in petroleum and power reported its expected recovery as blank — the
  engine declining to guess, correctly, but the link the brief names explicitly
  was missing. Recovery is now a per-industry `RecoveryModel` carrying the
  shares, the reversal scenario and the words for it: retail rolls a release
  back, a fuel marketer re-sources from another refinery, a generator brings a
  unit back on bar
- **Three retail levers had no recovery share either.** `assortment`,
  `carrier_mix` and `gateway_failover` appear on retail contracts and were
  absent from the table, so those cards were blank too. Found by the new test
  rather than by a reader
- **`Vertical` carried a path to the ground truth.** The engine never read it,
  but T-04 forbids `whychain/` and `api/` from naming that directory at all — a
  path in the package is one edit from a read, and the audit's `git grep` caught
  it. The map now lives in the tests, which are the only things allowed to read
  the labels
- **Eight defects the second and third industry exposed in the first one's
  assumptions**, written up as B-019: a rate of zero divided by, two planted
  causes that could not move their own metric, a sparse product priced the wrong
  side of the average, materiality floors derived from the generator's panel
  rather than the KPI series, a noise model three and a half times too tight at
  high rates, a phantom boundary day from an uncorrected timezone, an
  off-vocabulary phrase the rule table could match, and an optional that leaked
  a `None` into the candidate scanner
- **The hourly KPI was detected on a daily seasonal cycle.** `decompose`
  defaulted to `periods=(7,)`, which means "day of week" on the four daily
  contracts and "seven hours" on `checkout_conversion`, a cycle nothing has.
  Periods now come from `SEASONAL_PERIODS[contract.grain.time]` and the
  minimum-history guard is four cycles in the series' own units, not sixty rows
  (B-018)
- **A rate was judged at one volume across a twentyfold swing in volume.** A
  single MAD scale held a conversion read off 49 midnight sessions to the spread
  of one read off 925 evening sessions. The scale is now per observation — the
  standard error of the rate, binomial for a proportion and `1/sqrt(n)` for an
  average — normalised so the median observation keeps the scale the MAD already
  fitted, so the calibration is corrected rather than loosened. Together with
  the period fix this took West `checkout_conversion` from 1,393 flags at
  z >= 3 to 62, a rate of 0.30% against a nominal 0.27%, without moving the
  benchmark by a digit (B-018)
- **An empty hour was a guaranteed anomaly.** Flooring a zero rate to take its
  logarithm flagged all 226 hours in which West took no conversions, though at
  4.3% over ~50 sessions an empty hour happens about one time in nine. A
  half-count correction gives it a finite logarithm without moving a populated
  one; 226 flags became 1
- **The rate charts were quantised to two decimal places.** `/api/series`
  rounded rupees and ratios alike, so three months of hourly conversion reached
  the browser as seven distinct levels between 0.01 and 0.07 and the lower band
  sat flat on zero. Precision comes off the contract's unit; the same window now
  arrives as 56 distinct levels across 57 points (B-018)
- **`decompose_for(series, contract)` is the entry point.** Grain, denominator
  and noise model are read off the contract rather than passed by hand, because
  the defect above was every caller taking a default that was right for the
  metric they had in mind
- **The signal gap is scoped to the verified cause, not to the window.** Weather
  warnings are in the feed most weeks of the monsoon, so assessing the window
  alone reported a gap on an internal release regression: a real warning, real
  lead time, and no relationship to what happened. Superficially the
  best-evidenced output this stage can produce, and entirely false
- **The persona projection dropped `decisions`, `signal_gap` and `narrative`**,
  so the CFO, the reader for whom "the warning existed and no function owns
  it" *is* the finding, saw neither Answer 2 nor the decision they were being
  asked to back
- **`FeedbackStore.record` counted every entry twice.** It wrote to disk before
  warming its cache, so the reload picked up the new line and the append added
  it again, inflating precisely the number the quorum rule depends on
- **Track A was sorted backwards.** Slices that moved *against* the total headed
  the list of reasons the metric fell
- **The scoping dimension is excluded from Track A.** With a region selected,
  `region = West` was the top contributor at a 100% share: true, useless, and
  displacing a real contributor out of the list
- **The narrative validator rejected its own correct output.** ISO dates parsed
  as numerals and `4.05` quoted from inside a cited claim read as a fabricated
  figure. A validator with false positives is one somebody switches off

### Fixed, benchmark

- **Planted effects now clear regional materiality.** The old table planted
  10–40% moves on slices worth 6–20% of a region, landing at 1–5% of regional
  revenue, below the materiality floor by construction, so 152 of 160 cases
  produced nothing to explain and top-1 read 2.9%. The benchmark was measuring
  a generator bug. Each profile now plants on a slice wide enough that an
  incident-sized effect is worth reporting, with the arithmetic recorded beside
  the table. **Top-1 2.9% → 46.4%**, and of the 64 cases that clear materiality
  the true cause is ranked first in 100%. The floor itself was not touched
  (T-14)

### Changed, interface

- **Complete console overhaul.** A masthead carrying the live run context, a
  rail, a document column and a margin for run metadata and cost. Report
  sections are numbered so the page has a spine. The overview is a watchlist
  table with shared right edges rather than a stack of tiles. Answer 2 renders
  all four verdicts with the reached one marked, so a reader can see the engine
  chose. States are words with a hairline, not coloured discs


### Fixed, correctness

- **Every diagnosis endpoint now executes the KPI contract it was asked for.**
  `/api/diagnose`, `/api/decomposition` and `/api/candidates` resolved the
  contract only to reject an unknown name, then read `_panel`, the generator's
  own working frame, which carries revenue. A decomposition labelled
  `checkout_conversion` was arithmetic over revenue. `Warehouse.bridge_facts`
  reads each contract's own source with its own transforms, and `_panel` is no
  longer readable through `Warehouse.table` at all
- **The price/volume/mix bridge is declared per contract rather than assumed.**
  It is an identity over priced units, so it applies to `net_revenue` and to
  nothing else currently modelled. The four other KPIs decline with a reason
  instead of returning a price effect on a percentage (T-03 in a second form)
- **Ratios roll up as ratio-of-sums, not mean-of-means.** `aov`,
  `checkout_conversion` and `on_time_delivery` declared `aggregation: mean`, so
  a slice with three orders weighed as much as one with thirty thousand. On AOV
  this understated the daily figure by 4.6% on average and 17.1% at worst. A
  contract validator now rejects a ratio metric that declares `mean`
- **Verification requires every mandatory gate, not only difference-in-differences.**
  `event_time_isolation` and `placebo` were computed, reported, and then ignored
  when deciding `VERIFIED`, so a candidate could be verified with its placebo
  never run. SECURITY-LOGIC-CHECKLIST §1.1 specified all three
- **`/api/candidates` applies `region`.** It accepted the parameter and dropped
  it. It now filters which candidates are reported while still testing them
  against the full panel, because difference-in-differences needs the unexposed
  regions as a comparison group
- **The retriever cache key is content-addressed.** It was the ticket row count:
  a key that collides whenever one document replaces another and carries no
  entitlement context, which is precisely the cache key T-06 warns is a P0
- **Entitlement SQL is parameterised** and `Warehouse.table` takes an allowlist
- **`ext_signals` exists.** All three contracts declared a `severe_weather`
  driver sourced from it and a 36h SLA, and `source_freshness` reported a row
  for it, but the generator never emitted the table, B-003 recurring
- **The chart names its points by grain.** Hourly checkout conversion reported
  "1,729 days", overstating the history twenty-four-fold

### Added

- `whychain/telemetry/`, per-stage latency, method class, model calls, tokens
  and cost, rendered as a run receipt. It reports the model-call count it
  observed rather than asserting one: with no narrate stage yet that count is
  zero, and the receipt says the narrative came from a deterministic template
- `whychain/actions/`, decision cards carrying the brief's chain: driver, lever,
  action, expected impact, owner, confidence, monitoring rule. Impact is a
  declared share of the movement the causal test already measured, never an
  estimate. Causes with no controllable lever return `controllable: false` with
  no action and no recovery figure, which is what weather does
- Approval drafts. Nothing executes; a card produces a request for a named human
- `ext_signals`, public weather warnings per city with issue time, validity,
  severity, lead time and publisher: the fields foreseeability is decided on.
  Generated, and every row says so in `source`

### Changed

- A diagnosis takes 449ms rather than 2,317ms. Scans are bounded to the history
  a diagnosis actually reads instead of the whole table, and the document corpus
  is no longer rebuilt per candidate through `iterrows` to look up twelve rows
- Interface: IBM Plex throughout, one superfamily rather than two chosen fonts;
  a 17px base with the headline brought down from 40px; larger navigation and
  controls; a second accent so a clickable claim and a verified one are no
  longer the same colour. An hourly series opens on a readable window instead of
  drawing two points per pixel
- `whychain/evidence/`, `Evidence`, `Provenance`, `Freshness`, `EvidenceStore`.
  Append-only store, immutable records, unit/method agreement enforced at
  construction, acyclicity check on the support graph
- `whychain/corroborate/`, `Retriever` protocol with `NumpyRetriever` (default)
  and `PgVectorRetriever`; offline deterministic `TfidfSvdEmbedder`; sentence-level
  span citation
- `whychain/contracts/`, contract model and registry. Cross-contract validation
  covers KPI graph consistency, cycles, duplicate ids, missing freshness SLAs and
  unowned controllable levers
- `contracts/*.yml`, all five KPIs: net revenue, orders, AOV, checkout conversion
  (hourly, digital only), on-time delivery (T+1, no SOP registered)
- `data/docs/sop/`, the demand planning SOP that Answer 2 reads
- `datagen/`, retail calendar with real festival dates, catalog with real city
  coordinates, scenario and planted-event types, six demo cases
- `whychain/decompose/`, price/volume/mix bridge and dimensional contribution,
  both reconciling exactly and refusing to report if they do not
- `/api/decomposition`; console sections for the bridge and contributions
- `whychain/verify/`, event-time isolation, difference-in-differences,
  exposure consistency and placebo, with `CANNOT_VERIFY` held distinct from
  `REJECTED`. Candidates are read from the operational record with nothing
  marking which are real
- `/api/candidates`; console section showing verified, rejected and untestable
  candidates with the outcome of every test
- `whychain/corroborate/quarantine.py`, the boundary for untrusted text:
  fence neutralisation, control-character stripping, truncation, and detection
  of eleven classes of instruction injection
- `whychain/corroborate/extract.py`, structured extraction with span citations,
  behind a protocol so a model-based extractor drops in
- `whychain/corroborate/pipeline.py`, retrieval and extraction per candidate
- Placebo is now a distribution over six quiet windows rather than one
- `whychain/confidence/`, deterministic score over coverage, causal strength,
  corroboration and freshness, with contradiction detection and structured
  abstention. Not presented as a probability until there are held-out cases to
  calibrate against
- `/api/diagnose` ties the pipeline together and returns either a diagnosis or
  an abstention, never both
- `datagen/bulk.py`, 160 labelled cases across ten independently generated
  panels, spaced so their lookback windows do not contaminate each other
- `bench/run.py` and `make bench`, top-1 and top-k accuracy, false alarm rate,
  negative-control rejection, abstention precision and recall, calibration
  buckets with ECE, and latency
- Interface: sentence case throughout, warmer palette, tabbed panels so the
  answer is visible without scrolling past the working
- `tests/test_dependencies.py`, asserts every third-party import is pinned
- 142 tests, 40 marked `invariant`

### Fixed
- `holidays` was imported by the calendar modules but missing from
  `requirements.txt`, so CI failed on a clean runner while everything passed
  locally (B-007)
- GitHub Actions CI: lint, tests on Python 3.12 and 3.14, invariants as a
  separate check, and a job that fails the build on AI attribution in history
- Pull request template
- Repository scaffolding: one package per pipeline stage, Makefile, pinned requirements, `.env.example`
- Specifications: prototype design, product outline, design checklist, security & logic checklist, concepts reference
- Collaboration docs: context, handoff, decisions, bugs & traps, contributing

- `scripts/audit.py` / `make audit`, 30 executable checks across security,
  logic and design. Each one runs something rather than reading the code
- `sessions` and `shipments` sources; all five KPIs now compute
- Materiality converts to business impact via `value_per_unit_inr`

### Verified
- Full scientific stack installs on Python 3.14.6, numpy 2.5.2, pandas 3.0.5, scipy 1.18.1, statsmodels 0.15.0, scikit-learn 1.9.0, duckdb 1.5.5, fastapi 0.141.1
- `MSTL`, `IsotonicRegression` and `Ridge` importable; no wheel gaps on 3.14

### Decided
- DuckDB replaces Postgres + pgvector; no external service required (D-002)
- Two-track hypothesis ranking; GBM and SHAP dropped (D-003)

### Fixed
- Three dependency pins were wrong (`pytest-cov`, `ruff`, `uvicorn`), written
  from memory rather than from the working environment, which would have broken
  `make setup` on a teammate's machine. Now taken from `pip freeze` and verified
  by a clean install in a throwaway venv

### Changed
- D-002 revised: retrieval is pluggable rather than DuckDB-only. The original
  entry's justification was partly wrong and is corrected in place
