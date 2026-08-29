# The brief, verbatim

**This is the Round 2 problem statement as issued. It is the authority.**

Do not paraphrase it, tidy it, or edit it to match what was built. Where this
file and any other document in the repository disagree, this file is right and
the other one is out of date. `docs/REQUIREMENTS.md` maps every line of it to
code and to a command; if a row there cannot be traced back to a line here, the
row is scope that was invented rather than required.

Two failure modes this file exists to prevent. Drifting from the brief while
believing the work still matches it, which is what happens when a summary
becomes the thing everyone reads. And quietly narrowing a requirement to what
was convenient to build, which is only visible if the original wording survives
somewhere.

---

## BusinessIntelligence.ai

### Recap & Expanded Context

In Round 1, you explored a KPI storytelling engine that explains what changed in
a business metric, identifies likely root causes, and recommends next steps in
plain language. In practice, most businesses track KPIs across fragmented
systems with different refresh cadences and granularities, and the "right"
explanation for a movement often depends on who's asking and what they plan to
do about it.

### Round 2 Objective

Design and demonstrate a working prototype of a KPI intelligence-to-action
engine that:

1. Detects and prioritises material KPI movements.
2. Reconciles data and business context across heterogeneous sources.
3. Identifies and ranks explanatory drivers using appropriate analytical methods.
4. Generates persona-specific narratives supported by traceable evidence.
5. Communicates uncertainty and abstains when evidence is insufficient or contradictory.
6. Recommends practical actions grounded in business levers, constraints and decision rights.
7. Mechanism to learns from analyst and business-user feedback.
8. Operates within realistic security, cost, latency and scalability constraints.

The LLM should not be treated as the source of quantitative truth. Teams should
explicitly demonstrate when they use deterministic logic, SQL, business rules,
statistics, traditional ML, causal inference, retrieval or LLMs—and why.

### Real-World Complexities to Consider

- Multiple interacting drivers such as price, volume, mix, marketing, supply,
  seasonality, competition and external events.
- Different source-system refresh cadences, grains, data quality levels and
  historical coverage.
- Inconsistent KPI definitions, hierarchies, calendars, business rules and
  aggregation logic.
- Sparse history for new products, categories or markets.
- Materiality based on both statistical significance and business impact.
- Contradictory evidence, missing data and confidence calibration.
- Role-based personalization of insight depth, recommended actions and delivery
  channels.
- Row-, column- and domain-level security, sensitive-data protection and
  auditability.
- Model and data drift, feedback capture and continuous evaluation.
- LLM economics, including model choice, token consumption, latency, caching and
  cost per insight.

### Solutioning Areas You Could Explore

Teams may explore a hybrid combination of:

- Anomaly detection, contribution analysis, forecasting, causal inference and
  business-rule reasoning.
- Governed KPI semantics, metadata, lineage, business rules, ontology or
  knowledge graphs.
- LLM-assisted intent understanding, orchestration, narrative synthesis and
  contextual retrieval.
- Proactive alerts, conversational analysis, augmented dashboards or decision
  workspaces.
- Confidence scoring, evidence citation, alternative hypotheses and abstention
  mechanisms.
- Action recommendations structured as: driver → controllable lever → action →
  expected impact → owner → confidence → monitoring plan
- Human feedback, expert validation, correction workflows and learning loops.
- Platform-native and custom capabilities using Databricks, Snowflake, Microsoft
  Fabric, Tableau, Qlik, Looker or another suitable technology. (Open to chose
  any platform, or build completely custom solution or hybrid)

Platform-specific solutions are acceptable, but teams should distinguish between
native, configured, custom-built and externally integrated capabilities.

### Minimum Prototype Expectations

- Three to five connected KPIs across two or three data sources with different
  grains or refresh cadences.
- A lightweight KPI or semantic contract covering definitions, calculations,
  drivers, thresholds, lineage and access restrictions.
- At least two personas receiving different insight narratives or recommended
  actions.
- One multi-factor KPI movement with known or simulated underlying drivers.
- One low-confidence scenario in which the engine requests clarification or
  abstains.
- One sparse-history or newly launched KPI scenario.
- One role-based security or entitlement scenario.
- Evidence showing source freshness, analytical method, contribution, confidence
  and lineage.
- A clear breakdown of LLM versus non-LLM processing.
- Runtime telemetry covering latency, model calls, token usage and estimated
  cost.

---

## What is submitted

**Five uploads, not four.** The business proposal is required twice, as a PDF
and again as a deck. An earlier version of this file said four and was wrong,
which is the drift this document exists to catch.

These are the portal's own field names, so they can be checked off against the
form rather than against anyone's recollection of it.

| Portal field | Format | State |
|---|---|---|
| Public GitHub link | URL, 500 characters | repo exists; **confirm it is public before submitting** |
| Prototype video | mp4 or mov | **not started** |
| README document | PDF, ≤20 MB | `README.md` is written; **not yet rendered to PDF** |
| Detailed Business Proposal in PDF | PDF, ≤20 MB | **does not exist** |
| Detailed Business Proposal in PPT | pptx | **does not exist** |

**The deck must use the same presentation template as Round 1.** Not a new one,
however much better a new one might look. A judge who saw the Round 1 deck reads
a changed template as a different team, and the instruction is explicit. The
template file is held by the team and is not in this repository, so it has to be
dropped in before the deck can be built. Content first, template applied to it,
never the other way round.

The proposal must cover: problem framing, solution design, target users,
business case and impact, a phased roadmap, and key risks with mitigations. The
same content in both formats, so it is one piece of work rendered twice rather
than two pieces of work.

The README reference template is the Drupal project README template.

**What the prototype itself is judged on**, which is not the same list as the
eight objectives:

- How the solution works in practice
- How AI enables or enhances the solution
- The potential scalability of the idea
- The impact the solution can create

## Reading this against the build

`docs/REQUIREMENTS.md` is the map: every objective and every minimum expectation
above, against the module that satisfies it and the command that demonstrates
it, including the rows only partly met.

The four demonstration criteria are not the same as the eight objectives, and
it is worth checking them separately, because a build can satisfy every
objective and still answer none of these well:

- **How the solution works in practice** — the console, the six demo scenarios
- **How AI enables or enhances it** — `make capture-ai`, the routing table, the
  citation checks that make a small open model safe to use
- **Potential scalability** — the weakest of the four; see `HANDOFF.md`
- **Impact it can create** — belongs in the business proposal, which does not
  yet exist
