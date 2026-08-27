# WhyChain

An evidence-backed diagnosis engine for business metric movements.

When a metric moves materially, WhyChain answers two questions: **what caused it**, with every statement resolving to the query, rows or document behind it — and **why it was not anticipated**, naming the signal that existed, the process that did not consume it, and the monitoring that would catch it next time.

The quantitative layer is deterministic. The language model reads unstructured text, ranks competing hypotheses and writes the narrative. It never calculates, and it never decides what is true.

## Status

Early development. See `CONTEXT.md` for orientation and `HANDOFF.md` for current state.

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
| `CONTEXT.md` | orientation — start here |
| `docs/PROTOTYPE-SPEC.md` | architecture, data model, pipeline stages |
| `docs/PRODUCT-OUTLINE.md` | features and intended behaviour |
| `docs/CONCEPTS.md` | terminology reference |
| `docs/SECURITY-LOGIC-CHECKLIST.md` | correctness invariants and security tests |
| `docs/DESIGN-CHECKLIST.md` | interface requirements |
| `DECISIONS.md` | architectural decisions and rationale |
