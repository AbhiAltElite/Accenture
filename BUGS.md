# Bugs & traps

Two sections. **Traps** are failure modes identified in advance — read before writing the relevant stage, so they are never made. **Defects** are bugs actually found, with root cause, so they are not remade.

---

## Traps — known in advance, do not walk into these

| # | Trap | Where | Correct behaviour |
|---|---|---|---|
| T-01 | Asserting `model_calls <= 2` | telemetry test | Assert `== 2`. `<=` passes silently when a call fails — defeating the check we invite judges to make |
| T-02 | Percentage vs percentage point | narrate, validate | 10% → 15% is **+5 percentage points**, not "+5%" and not "+50%". Validator must treat these as different claims |
| T-03 | Method and unit disagreeing | evidence | A price/volume/mix bridge produces **currency**, never order counts. Assert unit compatibility per method |
| T-04 | Engine reading ground truth | datagen, bench | No import path from `whychain/` to `data/ground_truth/`. Enforced by `test_no_label_leakage` |
| T-05 | `CANNOT_VERIFY` collapsed into `REJECTED` | verify | Distinct states — see D-006. Corrupts abstention metrics if merged |
| T-06 | Cache key omitting entitlement | any caching | Key must include entitlement context, contract version and data snapshot. A cross-permission cache hit is a P0 |
| T-07 | Contributions that align but don't reconcile | decompose, UI | Dimensional contributions must sum to the same total as the bridge. Alignment is cosmetic; reconciliation is the claim |
| T-08 | Retrieved text treated as instruction | corroborate | Support tickets are untrusted third-party input. A ticket saying "ignore previous instructions" must change nothing |
| T-09 | Freshness rendered as a percentage | UI, confidence | Freshness is a timestamp, a lag and an SLA verdict — not `97%` |
| T-10 | Prompt instructions used as access control | narrate | Entitlement filtering happens at projection, before assembly. Never "please don't mention region X" |
| T-11 | Placebo failure overridden by other passes | verify | A failed placebo is fatal regardless of what else passed |
| T-12 | Rejected candidate silently re-promoted | rank, narrate | Once rejected, a candidate cannot reappear as a verified cause later in the same run |
| T-13 | Tuning on the held-out set | bench | Calibration is fitted on a held-out split and never re-fitted after seeing test results |
| T-14 | Fixing a failure by weakening its test | everywhere | If a test fails, fix the code or record the limitation. Never relax the assertion |
| T-15 | Naive datetimes in freshness arithmetic | ingest, evidence | All timestamps are timezone-aware UTC. `Freshness` rejects naive input, and ruff `DTZ` enforces it at the source. Sources sit in different zones; a naive/aware mix raises mid-diagnosis |
| T-16 | Writing a version, path or command from memory | everywhere | Read it from the environment. Pins come from `pip freeze`, not recollection — see B-001 |
| T-17 | A verification command that passes on empty output | scripts, CI | `cmd \| tail && echo OK` reports success when `cmd` never ran. Check the exit status of the command itself, and confirm the check can actually fail |

---

## Defects

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

**Lesson — promoted to a trap below (T-16).**

### Template

```markdown
### B-001 · <one-line summary>
**Found:** YYYY-MM-DD · **Severity:** P0/P1/P2/P3 · **Status:** open / fixed

**Symptom:**
**Root cause:**
**Fix:**
**Regression test:**
**Lesson (if it generalises — promote to a Trap above):**
```
