# Running WhyChain

Everything runs locally. No database server, no Docker, no API key for anything
built so far.

---

## Step 1, Set up

```bash
make setup
```

Creates `.venv` and installs pinned dependencies. Python 3.12+ required; the pins
are verified against 3.14.6.

## Step 2, Generate the dataset

```bash
make gen
```

Builds three years of a synthetic Indian retail business and writes it to
`data/warehouse/whychain.duckdb`, plus labelled ground truth to
`data/ground_truth/`, **which the engine has no code path to read.**

You should see roughly:

```
pos_txn              1,803,529 rows      order lines, hourly
sessions               416,461 rows      hourly session counts, digital only
shipments              300,324 rows      promised against delivered, T+1
plan_ops                 3,160 rows      weekly plan, T+2 lag
voice_ops                7,204 rows      tickets, notes, release log
ext_signals                546 rows      public weather warnings, per city
source_freshness             4 rows      when each source last landed
```

`ext_signals` is the feed Answer 2 reads. Its rows are generated and say so; see
`DECISIONS.md` D-004 for exactly which parts of the dataset are real.

## Step 3, Check what the engine knows

```bash
make status
```

Prints the KPI graph, drivers with their owners, freshness SLAs, signal coverage
and access policies, read through the real contract loader, not mocked.

## Step 4, Run the console

```bash
make demo
```

Then open **http://localhost:8000**.

## Step 5, Run the tests

```bash
make test                        # everything
.venv/bin/pytest -m invariant    # only the hard correctness invariants
```

---

# Understanding what you are looking at

The console opens on **net revenue, West region, last 90 days**; the case the
demo is built around.

### The headline
Names the largest material fall in the window. It should read close to
*"net revenue fell 14.9% on 2026-08-15"*. That is a real detection, not a
scripted string: a bug was planted in the data on 12 August and the engine found
it without being told.

### The chart
Three things are drawn:

- **Observed**, what actually happened
- **Expected**, trend, weekly rhythm and the retail calendar combined. This is
  what a normal day *should* have looked like
- **Normal range**, three robust standard deviations either side of expected

A dot marks a movement that passed both materiality tests.

**The thing to look for:** the cluster of dots in mid-August. And equally, the
*absence* of dots around 20–27 October 2025, where revenue collapses by nearly a
fifth after Diwali. That collapse is enormous and entirely ordinary, and the
detector stays silent because the festival was removed before anything was
measured.

### Material movements
Both tests must pass before a row appears here: a robust z of at least 3.0
**and** an absolute movement of at least ₹15,000. Statistical significance alone
surfaces movements too small to act on; size alone surfaces noise that happens
to be large. The brief asks for both.

`Robust z` is how far the day sits from expectation, measured in units built
from the median and MAD rather than mean and standard deviation, so a genuine
shock earlier in the history does not inflate what counts as normal and hide the
next one.

### Source freshness
Each source with its lag and its SLA. `plan_ops` runs at T+2 by design, so it is
routinely close to breaching. When a source does breach, confidence drops and
the narrative will say so rather than failing quietly.

---

# What to infer, and what not to

**What this proves.** Detection works on data it was not tuned to. The planted
event surfaces as five consecutive material drops of 10–16%. The seasonal decoy
is correctly ignored. Materiality genuinely filters on both axes. Freshness is
tracked per source against contracted SLAs.

**What it does not prove yet.** There is no signal-gap stage and no
model-written narrative: `whychain/signalgap/` and `whychain/narrate/` are empty
files, so Answer 2 does not exist in code and the narrative you read is a
deterministic template. A diagnosis therefore makes zero model calls, which the
run receipt states rather than hides. See `HANDOFF.md`.

**A full diagnosis is available for net revenue only.** The price/volume/mix
bridge is an identity over priced units, so the other four metrics decline to be
decomposed rather than returning revenue arithmetic under their own name. See
`DECISIONS.md` D-008.

**A number worth knowing.** About 2.6% of days are flagged as material across the
full three years. Some are the planted scenarios; the rest are false positives.
That rate is not hidden; the benchmark harness will measure and publish it,
because a detector that never reports its own false-alarm rate is asking to be
trusted rather than believed.

---

# Things worth trying

| Do this | Because |
|---|---|
| Set the range to **Full history** and look at October 2025 | The post-Diwali collapse, unflagged |
| Switch region to **East** | The same window is quiet; the event was regional, which is what makes a comparison group possible later |
| Switch KPI to **checkout conversion** | Hourly grain, digital channels only. A different metric, a different shape |
| Switch KPI to **on-time delivery** | Arrives from a third source at T+1 |
| Stop the server, run `make status` | The contracts drive everything the console shows |

## Poking at the data directly

```bash
.venv/bin/python -c "
from whychain.ingest import Warehouse
with Warehouse() as w:
    print(w.table('pos_txn', limit=5))
"
```

## API

```
GET /api/health
GET /api/kpis
GET /api/series?kpi=net_revenue&region=West&from=2026-07-01&to=2026-08-31
```

Interactive docs at http://localhost:8000/api/docs
