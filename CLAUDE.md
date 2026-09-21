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
./run.sh
```

Console at `http://localhost:8000`. `make test` (512), `make smoke` (gates a
demo), `make bench`, `make audit`, `make lint`, `make real-data`.

`make prepare` computes each contract's lineage once at ingest. It is idempotent
and runs automatically from `gen`, `gen-all` and `run.sh`. A warehouse that has
not been prepared still reads correctly, just slower.

Before any demo: `make warm-ai`, then `make smoke`.

## Non-negotiables

1. **The LLM never calculates.** It reads unstructured text, ranks hypotheses
   and writes prose. Every figure comes from deterministic code.
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
