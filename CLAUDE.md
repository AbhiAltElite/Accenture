# WhyChain

An evidence-backed diagnosis engine for business metric movements. Accenture
Innovation Challenge 2026, team CtrlAltReinvent, IIT Hyderabad. **Grand Finale
29 Sep 2026: a 10-minute pitch and 5 minutes of jury Q&A.**

## Read these before working

| File | What it is |
|---|---|
| `_internal/handoff/HANDOFF.md` | state, what is done, what is left, decisions already taken |
| `_internal/handoff/APP.md` | the system, the layout, how to run it |
| `_internal/handoff/RESEARCH.md` | market, competitors, Indian CPG org structure, mentor feedback |
| `docs/BRIEF.md` | the problem statement, verbatim. **The authority.** Where any other document disagrees with it, it is right and the other is out of date |
| `BUGS.md` | traps known in advance, and defects with root cause. Read the traps before writing in the area they name |

## Run it

```bash
./run.sh          # terminal, console at http://localhost:8000
make app          # builds WhyChain.app: double-click, opens in its own window
```

Sign-in at `/login`: a choice of demo seat (no password anywhere), or single
sign-on in proxy mode. Design: `ui/theme.css` (fonts bundled in `ui/fonts`,
OFL), light by default, and scaled up automatically from 1900px wide
(external monitors and projectors; laptops are never zoomed, B-068). A finding
page carries the chain, the variance bridge, the fishbone, the calendar and
**What-if analysis** (price slider and horizon, every figure from the engine).
A decision goes to its owner as a Teams card; once accepted or modified it
becomes a **change request** (`/api/dispatch/ticket`, `WHYCHAIN_TICKET_WEBHOOK`),
a preview until a service desk is connected. The board-pack slide is always light.

Two views. `/` is the **decision view**: findings inbox (filter by metric,
region, falls or rises, status), one finding at a time, sign-off, decisions,
board-pack slide (`/slide`), audit trail, and **Metrics** (`/?tab=metrics`),
the governed definitions read from the contracts. Clicking a finding's
headline figure opens its aggregated rows, the query that reproduces them
(checked against the warehouse on every open), and an audited CSV export.
`/workbench` is the analyst's full method page with the twelve `?demo=`
scenarios.

`make test` (670), `make smoke` (gates a demo; `WHYCHAIN_BASE` picks the
server), `make bench`, `make audit`, `make lint`, `make real-data`. `/uat` in
any browser runs the acceptance checks against every scenario and persona.

**For team laptops: `make package-offline`** builds `dist/WhyChain-win.zip`,
`WhyChain-mac-arm.zip` and `WhyChain-mac-intel.zip`, each with its own Python
(python-build-standalone, pinned in `app/runtime.py`, checksum-verified) and
every dependency inside: unzip, double-click, no installs, no internet. On a Mac,
a copy made by USB or shared drive opens with no prompt; one that arrived by
AirDrop or download needs one "Open Anyway" for `Start WhyChain.command`, which
then clears the downloaded mark from its own folder (B-066).

On another PC: `make package` builds `dist/WhyChain-portable.zip` (code, data,
AI cache and the `.env` key: USB or AirDrop only; `ARGS=--no-key` to leave it
out) and a `.sha256` beside it. There, follow `START HERE.txt`: double-click
`Start WhyChain.bat` (Windows) or right-click `Start WhyChain.command`, Open
(macOS, first time). `python app/launch.py --check` should end "... checks pass
on this computer. Ready." `app/launch.py` is the one installer for every entry
point, `run.sh` and `make setup` included: it verifies the environment against
`requirements.txt` and repairs it, so an interrupted first run fixes itself.
Never start anything through `.venv/bin/<script>`; use `.venv/bin/python -m`,
which survives the folder being moved (B-065).

`make prepare` computes each contract's lineage once at ingest. It is idempotent
and runs automatically from `gen`, `gen-all` and `run.sh`. A warehouse that has
not been prepared still reads correctly, just slower.

Before any demo, with the app running: `make stage-check` (warms the AI cache and
must end "All N cases warm", resets the demo records, runs the smoke test), then
`/uat` in the browser (must be all pass). **Reset demo** in the seat menu does the
reset from the app. A decision card goes to its owner's Teams channel
(`WHYCHAIN_TEAMS_WEBHOOK_<ROLE>`, falling back to `WHYCHAIN_TEAMS_WEBHOOK`); a change
already made (per the release log) raises no change request.

Deploying: `docs/DEPLOY-FREE.md`. `.github/workflows/deploy.yml` deploys `main` to
Google Cloud Run and smoke-tests the link, once `GCP_SA_KEY` and `GCP_PROJECT` are set.

Accountability: sign-off, decisions and dispatch go to a hash-chained log
(`whychain/audit`). Identity is a demo picker unless `WHYCHAIN_IDENTITY=proxy`,
where a single-sign-on proxy's headers decide who the reader is and which
regions they see, believed only from a proxy that proves itself
(`WHYCHAIN_PROXY_SECRET` and/or `WHYCHAIN_TRUSTED_PROXIES`; with neither set it
refuses everyone, B-076). See `whychain/identity.py`.

Serving: the container runs `WHYCHAIN_WORKERS` processes (Cloud Run: 2). The
audit chain and feedback log are safe across processes (B-077,
`tests/test_workers.py`); anything new that a request writes must be too. The
desktop app runs one process.

`make eval-extraction` scores the keyword rules and the model on 96 labelled
tickets (`bench/tickets_heldout.json` was labelled and committed before any run);
`WHYCHAIN_LLM_CACHE=off` for a live reading. Results in `bench/extraction.json`.
Six live runs on 26 Sep: where a batch answered, held-out tickets 88 to 92% right
against 11.5% for the keyword rules, 0 false alarms in five of six runs; but the
free model sometimes returns nothing for a whole batch (B-081, open).

## Non-negotiables

1. **The LLM never calculates.** It interprets the question, reads unstructured
   text (tickets, notes) in the writer's own words, and writes prose. Ranking
   causes is statistical, not the model. Every figure comes from deterministic code.
2. **A claim that cannot be traced is not shipped.** A deterministic validator
   runs after the model and rejects any sentence whose figures are not in the
   evidence table.
3. **Refusal is a designed output**, not an error path. `UNKNOWN`,
   `CANNOT_VERIFY`, `not_foreseeable` and `coverage_unknown` each render their
   own way. A polished false diagnosis is worse than an explicit unknown.
4. **A filter must narrow what is considered, not only what is drawn.** See
   `touches_scope` in `whychain/verify/relevance.py`.
5. **Never weaken a test to make something pass** (T-14). Fix the code, or
   record the limitation in `BUGS.md`.
6. When you find a defect, write it up in `BUGS.md` with its root cause, and add
   a trap if the class of mistake can recur.
7. **A performance change must not be able to change an answer.** If it caches
   or materialises anything derived from a contract, a test asserts the stored
   form equals the declared form, and that test is verified to fail. See
   `tests/test_materialised_lineage.py`.

## Naming, decided

**No real company is named in anything deck-facing.** The org-structure research
read the published leadership pages and filings of real consumer goods companies
to find the *pattern*. The pattern is what we present, labelled "reference
operating model, drawn from published structures of leading Indian and global
consumer goods companies". Naming one invites a juror to check our chart against
theirs and implies a relationship we do not have.

The names live in `_internal/RESEARCH-INDIAN-CPG.md` and
`_internal/handoff/SOURCES.md`, both carrying a banner saying so, and go no
further. Competitors are a separate question: naming SAP, Oracle and the BI
vendors in the concession is deliberate and mentor-advised.

## House style

- **No em dashes.** Comma, semicolon or full stop.
- **No AI co-author trailer on commits.**
- Comments explain why, not what. Match the density of the surrounding file.
- Do not say "root cause" in user-facing copy. Say **verified cause**, and
  **signable**. The incumbents own the other phrase.
- **Never write "nobody does X" or "the only".** Write **"not documented"**: it
  says we looked, says what we found, and cannot be falsified by one
  counter-example. This applies to the deck as much as the code comments.
