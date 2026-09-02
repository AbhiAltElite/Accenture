# Documentation index

The README is the submission document and answers the challenge on its own.
These are the working documents behind it: read them when you want the reasoning
under a claim, not the claim.

**If you are evaluating this repository, start with
[REQUIREMENTS.md](REQUIREMENTS.md).** It is the only document that maps every
objective in the brief to the module that satisfies it and the command that
demonstrates it, and it marks the rows that are only partly met.

| Document | What it is | Read it when |
|---|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Requirement → implementation → command, for all eight objectives and all ten minimum expectations | You are checking the build against the brief |
| [PROTOTYPE-SPEC.md](PROTOTYPE-SPEC.md) | The design specification: the architectural spine, each pipeline stage, the contracts of every type | You want to know how a stage works before reading its code |
| [PRODUCT-OUTLINE.md](PRODUCT-OUTLINE.md) | What is being built and for whom, in product terms rather than engineering ones | You want the shape of the product without the internals |
| [CONCEPTS.md](CONCEPTS.md) | Every term used in the submission, in plain language, with the one sentence to say if asked | A term in the README or the console is unfamiliar |
| [SECURITY-LOGIC-CHECKLIST.md](SECURITY-LOGIC-CHECKLIST.md) | The security and logic checks, scoped to what this prototype actually is, with the productionisation gap named rather than omitted | You are assessing what has been hardened and what has not |
| [DESIGN-CHECKLIST.md](DESIGN-CHECKLIST.md) | The interface principles and the checklist run before shipping | You are judging the console as an interface |

The security, logic and design checklists are not prose alone: `make audit` runs
33 of their items as executable checks and prints a pass or fail for each.

## Elsewhere in the repository

| Document | Contents |
|---|---|
| [../README.md](../README.md) | The submission document: problem, approach, architecture, measured results, how to run it |
| [../DECISIONS.md](../DECISIONS.md) | Architectural decisions, each with the alternatives rejected and why |
| [../BUGS.md](../BUGS.md) | Traps identified in advance, and defects found, each with root cause |
| [../RUNBOOK.md](../RUNBOOK.md) | Operating the system: demo preparation, failure modes, recovery |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | The rules a change has to follow, including the ones CI enforces |
| [../CHANGELOG.md](../CHANGELOG.md) | What changed, in order |
