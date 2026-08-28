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
| Top-1 accuracy | 36.6% |
| Top-1 among cases that clear materiality | 75.4% (52 of 69) |
| Cause verified at all | 48.6% |
| False-alarm rate on noise-only cases | 0.0% |
| Planted correlation traps rejected | 86.7% |
| Expected calibration error | 0.103 |
| p95 latency per diagnosis | 0.175s |

The headline number carries its condition on purpose. The engine explains
movements that pass both a statistical and a rupee materiality test; the
remaining cases are ones it declines to explain, because a movement of about
10% at regional level sits at roughly z = 2.2 against 4.5% daily noise and is
not distinguishable from it at the z >= 3 threshold the contracts declare.
Declining those is the correct behaviour, and lowering the threshold to raise
the headline is the trap recorded as T-14 in `BUGS.md`.

Two of these numbers are worse than they should be, and are recorded here
rather than tuned away:

- **Confidence is overconfident at the top of its range.** Scores between 0.8
  and 1.0 average 0.917 and are right 71% of the time, a 20-point gap. The
  score is not yet calibrated against a held-out split, and until it is, the
  band label is more trustworthy than the number beside it.
- **Abstention is not measurable from this population.** Every case is either
  `verified` or `no_anomaly`, so there is no case whose correct answer is "the
  evidence is insufficient", and the two abstention rates are reported as zero
  for want of a denominator. The behaviour is real and fires in the console on
  `demo-02-low-confidence`; what is missing is the labelled population needed
  to score it. See `HANDOFF.md`.

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
| `docs/DESIGN-CHECKLIST.md` | interface requirements |
| `DECISIONS.md` | architectural decisions and rationale |
