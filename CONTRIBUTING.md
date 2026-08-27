# Contributing

Three people on one repository, working in parallel. These conventions exist to keep the main branch demoable at all times.

## Before you start a session
1. `git pull`
2. Read `HANDOFF.md` — someone may have stopped mid-stage
3. Skim `DECISIONS.md` if you intend to change structure, and `BUGS.md` for the stage you're touching

## Before you stop
1. Update `HANDOFF.md` using the template at its foot — especially *where exactly you stopped*
2. Add a `CHANGELOG.md` entry under Unreleased
3. Record any new trap in `BUGS.md`
4. Commit and push, even if incomplete — a pushed branch is recoverable, a local one is not

## Branches
```
main                  always demoable — never commit directly
feat/<stage>          feat/detect-mstl, feat/evidence-model
fix/<short>           fix/bridge-residual
docs/<short>
```

## Commits
Conventional commits, imperative mood, present tense:

```
feat(detect): add MSTL decomposition with festival regressors
fix(decompose): bridge residual was dropped when qty was zero
test(verify): add negative-control rejection case
docs(handoff): record stopping point in contract loader
```

**No AI attribution anywhere** — not in commit messages, trailers, code comments, or docs. No `Co-Authored-By` for tools, no "generated with". Check before pushing:

```bash
git log --format='%an <%ae>' | sort -u
```

Only the three of you should appear.

## Pull requests
Small and single-purpose. In the description: what changed, why, how it was verified. If it touches a pipeline stage, say which invariants from `docs/SECURITY-LOGIC-CHECKLIST.md` §1 it affects.

## The interface contract
`whychain/evidence/` defines the `Evidence` type. **It is frozen once the first stage consumes it.** Changing its shape breaks all three workstreams at once — raise it as a decision, don't just edit it.

## Testing
```bash
make test                    # all
.venv/bin/pytest -m invariant  # the hard correctness invariants
make bench                   # benchmark metrics
```

Invariant tests must never be skipped, marked xfail, or relaxed to pass. If one fails, either the code is wrong or the invariant needs a documented decision entry — not a weaker assertion.

## Setup on a fresh machine
```bash
make setup
cp .env.example .env      # LLM stages only; stages 0–6 and the benchmark run without a key
make gen
make test
```
