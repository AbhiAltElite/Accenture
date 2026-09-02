## What changed

## Why

## How it was verified
<!-- Commands run, cases checked. "Tests pass" alone is not verification. -->

## Invariants touched
<!-- Which of docs/SECURITY-LOGIC-CHECKLIST.md §1 does this affect, if any? -->

## Checklist
- [ ] `make test` passes, including `-m invariant`
- [ ] `ruff check .` clean
- [ ] `make ci` passes locally — the same steps CI runs, in CI's order
- [ ] `CHANGELOG.md` entry added
- [ ] New trap recorded in `BUGS.md`, if one was found
