# WhyChain

An evidence-backed diagnosis engine for business metric movements.

When a metric moves materially, WhyChain answers two questions: **what caused it**, with every statement resolving to the query, rows or document behind it, and **why it was not anticipated**, naming the signal that existed, the process that did not consume it, and the monitoring that would catch it next time.

The quantitative layer is deterministic. The language model reads unstructured text, ranks competing hypotheses and writes the narrative. It never calculates, and it never decides what is true.

## What this does not claim

Automated root-cause analysis is a solved marketing problem and a crowded
product category. ThoughtSpot's Spotter advertises causal analysis of metric
movements; Tableau Pulse ships anomaly detection with natural-language
summaries; Power BI is consolidating the same capability into Copilot.
Ingesting external signals into planning is an established category of its own,
sold as demand sensing by Kinaxis, o9 and others. The supply-chain literature
already names "missing causal factors" and "process gaps" as root causes of
forecast error.

**None of that is what this project claims to have invented.** Three things are
different, and they are narrower than "we explain why metrics move":

**1. The explanation is checkable, and the engine is measured.** Contribution
analysis presented as root cause is the market norm. Here, ranking and causal
verification are separate stages: an exact identity that reconciles to the
movement, and a correlational fit that is barred from ever becoming a stated
cause. Planted correlation traps are rejected at a published rate. No
commercial BI tool publishes an insight-accuracy number at all, which is the
asymmetry this repository is built around.

**2. The engine refuses, and the refusals are scored.** Calibrated confidence
fitted on a held-out split, a measured abstention rate, and four distinct
verdicts for the foreseeability question, three of which decline. Selective
prediction and calibration are live research topics; neither ships in
augmented analytics.

**3. Answer 2 is a retrospective audit, not a forward-looking feed.** Demand
sensing ingests signals to forecast better. This asks, after a movement has
happened and per incident: was a warning published, was it public, did it
arrive early enough to act on, does the registered planning process have a step
that consumes it, how often has this recurred, and who owns the gap. With a
foreseeability gate that returns "not foreseeable" on a warning that arrived
too late to act on. That specific audit is where the space is genuinely
unoccupied.

The method is a transfer of detection-gap analysis from software reliability
practice into business planning. It is not a new algorithm, and describing it
as one would not survive a hostile question.

## Status

Every pipeline stage runs. See `CONTEXT.md` for orientation and `HANDOFF.md` for
current state; those two files are the ones kept honest about what is built,
and the specs under `docs/` should be read as design intent.

### Measured, not asserted

160 labelled cases, with planted causes, planted correlation traps, planted
noise, and planted cases that cannot be answered at all (`make bench`).

**Read the first two rows together.** The engine explains movements that clear
both a statistical and a rupee materiality test, and declines the rest. Top-1
over the whole population is therefore bounded by how many movements are worth
explaining, not by how often the engine is wrong when it speaks.

| | |
|---|---|
| **Top-1 among movements worth explaining** | **78.6%** (55 of 70) |
| Top-1 over the whole population | 38.2% |
| True cause verified at all | 47.9% |
| **False alarms on noise-only cases** | **0.0%** |
| Planted correlation traps rejected | 87.5% |
| **Cases needing an abstention that got one** | **94.1%** (1 missed of 17) |
| Abstentions that were right | 86.4% |
| Expected calibration error | 0.1171 raw, **0.1043 calibrated** on held out |
| Latency p50 / p95 | 0.080s / 0.178s |

Lowering a threshold to raise the headline is the trap recorded as T-14 in
`BUGS.md`, and the reason the first row carries its condition rather than being
quoted alone.

**What is still weak, recorded rather than tuned away:**

- **Confidence remains overconfident at the top of its range**, after
  calibration. The isotonic curve is fitted on 73 cases from a held-out half
  and improves held-out ECE from 0.1171 to 0.1043. A real improvement on a
  small sample, not a solved problem.
- **Only `net_revenue` decomposes exactly.** The price/volume/mix bridge is an
  identity over priced units; a rate has no units to move and no price to
  change. The other four KPIs decline with a reason rather than returning a
  price effect on a percentage.
- **71 of 160 cases produce no material movement.** A sustained multi-day
  drop is currently tested one day at a time, so a movement that is obvious over
  a week can sit under the z threshold on every individual day. Pooling the
  event window is the largest single accuracy gain available and is recorded in
  `HANDOFF.md`.

Two numbers in this table have moved for reasons worth reading before quoting
them. Both are written up in `BUGS.md`: B-014, where benchmark cases were
contaminating each other's baselines and every figure was too good, and B-016,
where abstention recall was measuring correct silences as failures.

**Every objective and minimum expectation in the brief is mapped to code and to
a command in [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md), including the rows
that are only partly met.**

## On the process document behind Answer 2

Answer 2 rests on a claim about what a standard sales-and-operations planning
cycle consumes: sales history, inventory position, capacity and the financial
plan, and no external risk signal.

`data/docs/sop/sop_demand_planning_v2.md` is a **representative** process
document written for this repository. It is not a third-party SOP, because a
public repository cannot redistribute one. It exists so the extraction step has
something real to parse, with character spans that a test verifies against the
file itself.

The underlying claim is therefore cited to public sources rather than rested on
that document:

- **APICS/ASCM and the standard S&OP literature** describe the monthly cycle as
  demand review → supply review → financial reconciliation → executive S&OP,
  with inputs drawn from sales history, inventory, capacity and budget.
- **Forecast Value Added (FVA)** research in demand planning identifies
  *missing causal factors* and *process gaps* as recurring root causes of
  forecast error; the same finding this engine reports, arrived at by audit
  rather than by diagnosis.
- Published post-incident practice in software reliability treats *detection
  gap* analysis, which signal existed, who owned it, why it was not consumed,
  as a distinct question from root cause. Answer 2 is a transfer of that
  discipline to business planning, not a new algorithm.

Where the engine has no registered process document for a KPI, it returns
`coverage_unknown` and declines to infer a gap from the absence of evidence.

## Quick start

```bash
make setup      # venv + dependencies
make gen        # generate the dataset
make test       # run the suite
make demo       # start the API and console
```

Requires Python 3.12+. No database server, no Docker.

## Documentation

| Document | Contents |
|---|---|
| `CONTEXT.md` | orientation, start here |
| `docs/PROTOTYPE-SPEC.md` | architecture, data model, pipeline stages |
| `docs/PRODUCT-OUTLINE.md` | features and intended behaviour |
| `docs/CONCEPTS.md` | terminology reference |
| `docs/SECURITY-LOGIC-CHECKLIST.md` | correctness invariants and security tests |
| `docs/REQUIREMENTS.md` | **every brief objective and expectation, mapped to code and a command** |
| `docs/DESIGN-CHECKLIST.md` | interface requirements |
| `DECISIONS.md` | architectural decisions and rationale |
