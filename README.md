# WhyChain

An evidence-backed diagnosis engine for business metric movements.

When a metric moves materially, WhyChain answers two questions: **what caused it**, with every statement resolving to the query, rows or document behind it, and **why it was not anticipated**, naming the signal that existed, the process that did not consume it, and the monitoring that would catch it next time.

The quantitative layer is deterministic. The language model reads unstructured text, ranks competing hypotheses and writes the narrative. It never calculates, and it never decides what is true.

## Status

Every pipeline stage runs. See `CONTEXT.md` for orientation and `HANDOFF.md` for
current state; those two files are the ones kept honest about what is built,
and the specs under `docs/` should be read as design intent.

### Measured, not asserted

Over 160 labelled synthetic cases with planted causes and planted decoys
(`make bench`):

| | |
|---|---|
| Top-1 accuracy | 38.2% |
| Top-1 among cases that clear materiality | 78.6% (55 of 70) |
| True cause verified at all | 47.9% |
| False alarms on noise-only cases | **0.0%** |
| Planted correlation traps rejected | 87.5% |
| Abstention precision | 86.4% |
| Abstention recall | 20.9% |
| Expected calibration error | 0.1171 raw, **0.1043 calibrated** on held out |
| Latency p50 / p95 per diagnosis | 0.077s / 0.180s |

Read those with their conditions attached. The engine explains movements that
pass both a statistical and a rupee materiality test and declines the rest, so
top-1 over the whole population is bounded by how many movements are worth
explaining at all. Lowering a threshold to raise the headline is the trap
recorded as T-14 in `BUGS.md`.

Three of these are worse than they should be, and are recorded rather than
tuned away:

- **The engine under-abstains.** Abstention recall is 20.9%: faced with a
  case it cannot answer it more often reports "no material movement" than
  "unknown". When it does abstain it is right 86.4% of the time, so the
  judgement is sound and the trigger is too conservative.
- **Confidence is still overconfident at the top of its range**, even after
  calibration. The isotonic curve is fitted on 73 cases from a held-out
  half and improves held-out ECE from 0.1171 to 0.1043. That is a real
  improvement on a small sample, not a solved problem.
- **Only `net_revenue` decomposes exactly.** The price/volume/mix bridge is an
  identity over priced units; a rate has no units to move and no price to
  change. The other four KPIs decline with a reason rather than returning a
  price effect on a percentage.

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
