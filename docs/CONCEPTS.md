# WhyChain, Concepts & Terminology Reference

**How to use this:** every term below appears somewhere in the plan. The rule for the submission is simple, **if you cannot explain a term aloud in one sentence, do not put it in the README, the deck, or the video.** A judge asking "what does that mean?" and getting silence costs more than the term ever gained you.

Each entry gives: what it is in plain language → why it is in your system → the sentence to say if asked.

---

## PART 1; The eight you will most likely be asked about

### 1. MSTL / STL decomposition
**What it is.** A method that splits a time series (daily revenue, say) into three parts: a **trend** (slow long-term direction), **seasonality** (repeating patterns), and a **residual** (whatever is left over, i.e. the unexplained part). STL handles one repeating pattern; **MSTL** handles several at once, which you need, because retail has a weekly rhythm *and* a yearly rhythm *and* festival effects.

*LOESS, the "L", is just the smoothing technique used internally. You do not need to defend it.*

**Why it is in your system.** You detect anomalies on the **residual**, not on the raw number. That is what makes Diwali not look like a crisis, the festival effect gets absorbed into the seasonal component, so it never reaches the anomaly detector.

**Say this:** *"We strip out trend and the repeating seasonal patterns first, and only look for anomalies in what's left. That's why a festival week doesn't trigger a false alarm."*

---

### 2. Robust z-score (and MAD)
**What it is.** A z-score says "how many standard deviations away from normal is this?" The problem: if your history contains a few wild outliers, they inflate the definition of "normal" and real anomalies stop looking anomalous. A **robust** z-score fixes this by using the **median** instead of the mean, and **MAD (Median Absolute Deviation)** instead of standard deviation. Medians ignore extremes.

**Why it is in your system.** Retail history has genuine shocks in it. Robust statistics stop last year's crisis from hiding this year's.

**Say this:** *"Standard deviation gets distorted by outliers, so we use median-based statistics, past shocks don't blind us to new ones."*

---

### 3. Price / Volume / Mix bridge (PVM)
**What it is.** A standard finance decomposition. If revenue fell ₹10 lakh, PVM splits that into three exact pieces:
- **Price**, we charged less per unit
- **Volume**, we sold fewer units
- **Mix**, we sold a different *blend* of products (more cheap items, fewer premium ones), even if total units held

The three add up **exactly** to the total change. It is arithmetic, not estimation.

**Why it is in your system.** This is your "the LLM never does the maths" claim made concrete. And because it is an identity rather than a model, you can say your contributions sum exactly, something a machine-learning attribution cannot promise.

**Say this:** *"Revenue movement decomposes into price effect, volume effect and mix effect, and those three sum exactly to the total. No model, no estimation, arithmetic."*

---

### 4. SHAP / Shapley values, and why you separate them from causation
**What it is.** **Shapley values** come from cooperative game theory: if a team wins a prize, how do you fairly split credit among players? **SHAP** applies that idea to machine learning, how much did each input feature contribute to this prediction?

**The critical limitation.** SHAP explains **the model**, not **reality**. If your model learned that ice cream sales correlate with drownings, SHAP will faithfully report ice cream as a contributor. It measures association, never causation.

**Why it matters to you.** Most competing teams will show a SHAP chart and call it root cause. Your plan's core methodological claim is that this is wrong, and that ranking (association) must be separated from verification (causation).

**Note: you no longer use SHAP.** Internal drivers are ranked by the exact price/volume/mix bridge (an identity), and external drivers by a regularised linear regression whose coefficients are read directly. You still need to understand SHAP, because you will be asked why you didn't use it, and "because it explains the model rather than reality, and because an identity that sums exactly is a stronger basis than an estimate" is a strong answer.

**Say this:** *"SHAP tells you what the model leaned on. It does not tell you what caused anything. That's why we treat ranked candidates as hypotheses and then test them."*

---

### 5. Difference-in-Differences (DiD)
**What it is.** The workhorse causal method, and genuinely intuitive. You have an **affected group** and an **unaffected comparison group**. You measure the change over time in *both*.

Example: mobile app release 4.05 went to the West region only.
- West revenue: −8%
- East revenue (no release): −1%
- **Difference in the differences: −7%** attributable to the release

The East's −1% captures everything affecting the whole business, economy, season, national events. Subtracting it isolates what was unique to the West.

**Why it is in your system.** This is your "we test causes, we don't just rank them" claim. It is the stage where a correlated candidate either survives or dies.

**Say this:** *"We compare the affected region against one that wasn't affected. Whatever moved both is background; what's left is the effect we're attributing."*

---

### 6. Placebo test
**What it is.** A sanity check on your own method. You deliberately run the same analysis on a period or group where the cause **definitely was not present**. If your method still "finds" an effect, your method is broken and you should not trust its real findings.

**Why it is in your system.** It is cheap, and it is the difference between a method and a method you have reason to trust.

**Say this:** *"We run the same test where we know nothing happened. If it finds an effect there, we don't trust it here."*

---

### 7. Calibration, ECE, and reliability diagrams
**What it is.** **Calibration** asks: when your system says "80% confident," is it actually right about 80% of the time? A system can be accurate but badly calibrated (right often, but its confidence numbers are meaningless).

**ECE, Expected Calibration Error**, is one number summarising the gap. You bucket predictions by stated confidence, compare each bucket's stated confidence to its actual accuracy, and average the differences. **Lower is better; 0 is perfect.**

A **reliability diagram** is the picture: stated confidence on the x-axis, actual accuracy on the y-axis. Perfect calibration is a straight diagonal line.

**Isotonic regression** is the repair tool, it learns a correction mapping from your raw scores to honest probabilities. (**Platt scaling** is the alternative that fits a logistic curve instead.)

**Why it is in your system.** This is your single strongest anti-fake asset. A team whose confidence number was written by an LLM **cannot produce this chart at all**, because there is nothing to calibrate against.

**Say this:** *"When we say 80% confident, we've checked that we're right about 80% of the time. Here's the curve. A confidence number generated by a language model can't have one."*

---

### 8. Abstention precision and recall
**What it is.** Two ways of being right about saying "I don't know."
- **Precision**, of all the times you said UNKNOWN, how often *should* you have?
- **Recall**, of all the cases where UNKNOWN was the correct answer, how often did you actually say it?

A system that always says UNKNOWN has perfect recall and terrible precision. One that never does has the reverse. You need both.

**Say this:** *"We measure both whether our 'unknowns' were justified, and whether we caught the cases we should have abstained on."*

---

### 9. Negative control
**What it is.** A deliberately planted case where you **know** there is no causal relationship, used to test whether your method wrongly finds one. Two flavours: a **negative control exposure** (a cause known not to affect the outcome) and a **negative control outcome** (an outcome known not to be affected by the cause).

It is an established method in observational causal inference, Lipsitch, Tchetgen Tchetgen & Cohen, *Epidemiology* (2010), "Negative controls: a tool for detecting confounding and bias in observational studies", and that same literature lists difference-in-differences among the standard negative-control approaches. So DiD plus negative controls is a textbook pairing, not something you invented for a hackathon.

**Why it is in your system.** Your generator plants events that correlate perfectly with the drop but caused none of it, a promotion launched the same day as a checkout bug. A correlation-ranking tool picks the promotion. Your verification stage must reject it, and you report **how often it does**.

**Why this is the most valuable thing in the benchmark.** The sharpest attack on synthetic data is "you verify causes you planted, that's circular." Negative controls convert that from an argument into a measurement: *we plant traps, and here is the rate at which we catch them.*

**Say this:** *"We plant events that correlate perfectly but cause nothing. If our verification promoted those to claims, the method would be worthless. Here's how often it rejects them."*

---

## PART 2, Statistical & analytical terms

| Term | Plain meaning |
|---|---|
| **Residual** | What's left of a number after removing trend and seasonality, the unexplained part |
| **Event-time isolation** | Checking the effect starts *only after* the suspected cause. If the drop began two weeks before the release, the release is innocent |
| **Confounder** | A hidden third factor causing both things you observed, creating a fake link between them |
| **Comparison / control group** | The unaffected group you measure against (the "East" in the DiD example) |
| **Falsification test** | Any test designed to *disprove* your hypothesis. If it survives deliberate attempts to kill it, it's stronger |
| **Synthetic control** | Building a weighted blend of unaffected regions that mimics the affected region's history, used as a stand-in for "what would have happened anyway." **You cut this**, DiD plus placebo is enough |
| **Contribution analysis** | Which slice (region, channel, product) accounts for what share of the total movement |
| **Bayesian shrinkage / hierarchical model** | For a product with 3 weeks of data, its own numbers are noisy. You pull its estimate toward the category average, heavily when data is sparse, less as data accumulates. **This is your sparse-history scenario** |
| **Prior** | What you believed before seeing this data |
| **Beta-Binomial** | A standard way to track "how often has this kind of hypothesis been right?" as accept/reject counts accumulate. **This is your feedback loop's mechanism** |
| **Confidence interval (CI)** | The range the true value probably falls in. Wide CI = uncertain |
| **Materiality** | Does the movement actually matter, both statistically (unlikely to be random) *and* in business terms (₹ large enough to act on). The brief asks for both |
| **Top-1 / Top-3 accuracy** | Was the true cause ranked first / in the top three |
| **False alarm rate** | How often you flagged something that wasn't real |
| **Elasticity** | How much demand moves when price moves |
| **Ridge / Lasso (regularised regression)** | Linear regression with a penalty that keeps coefficients small and stable when inputs are correlated (marketing spend and competitor activity often move together). Lasso additionally pushes weak coefficients to exactly zero, which does feature selection for you. **This is your Track B ranking**, coefficients are read directly, no SHAP needed |
| **Standardisation** | Rescaling inputs so they're comparable (spend in ₹ lakh vs temperature in °C). Required before you can compare regression coefficients to each other |
| **Lag alignment** | Matching cause and effect in time, marketing spend this week may affect sales next week. Getting the lag wrong manufactures or hides relationships |
| **Permutation importance** | Shuffle one input's values and see how much the model degrades. Big drop = important feature. **Not used, noted because it pairs with SHAP, which you cut** |
| **Partial dependence plot** | A chart showing the *shape* of a relationship, not just "price matters" but "below ₹500, demand jumps" |

---

## PART 3, Data engineering terms

| Term | Plain meaning |
|---|---|
| **Grain** | The level of detail of one row. Order-line grain = one row per item per order. Daily×region grain = one row per region per day. **Mismatched grains are why your three sources need reconciling** |
| **Cadence** | How often data refreshes (hourly, daily, T+2 = arrives two days late) |
| **Semantic layer / contract** | The single agreed definition of a metric, its SQL, filters, owner, thresholds, so "revenue" means the same thing everywhere. **Your governance artefact** |
| **Lineage** | The traceable path from a number back through every transformation to its source tables |
| **RLS (Row-Level Security)** | Users see only rows they're entitled to, a West manager sees West rows. **Your entitlement scenario** |
| **Column masking** | Hiding or obscuring a sensitive column (unit margin) while leaving the rest visible |
| **PII** | Personally Identifiable Information, names, emails, phone numbers. **Must never enter an LLM prompt in your design** |
| **Embeddings** | Text converted into a list of numbers that captures its meaning, so similar meanings sit near each other numerically |
| **Vector search** | Finding text by *meaning* rather than exact keywords, "checkout broken" matches "payment page won't load" |
| **pgvector** | The Postgres extension that stores embeddings and does vector search |
| **BM25** | Classic keyword-relevance ranking (what search engines used pre-embeddings). **You cut this** |
| **RAG (Retrieval-Augmented Generation)** | Retrieve relevant real documents, then feed them to the LLM so it answers from sources instead of memory. **Your corroboration stage** |
| **DuckDB** | A fast analytical database that runs inside your process with no server, "SQLite for analytics" |
| **JSONL** | One JSON object per line. Convenient for logs and telemetry |
| **SLA** | Service Level Agreement, the promise about freshness or uptime. **Your freshness gate enforces one** |
| **Drift** | When incoming data or model behaviour changes over time and quietly degrades quality |
| **VPC** | Virtual Private Cloud, the client's own isolated cloud boundary. "Runs in your VPC" means their data never leaves |

---

## PART 4, Business & finance terms

| Term | Plain meaning |
|---|---|
| **FP&A** | Financial Planning & Analysis, the finance team that budgets, forecasts, and explains why actuals differed from plan. **Your primary user** |
| **Variance** | The gap between what happened and what was planned. "Variance analysis" is explaining that gap, literally your product |
| **KPI** | Key Performance Indicator, a metric the business steers by |
| **CPG** | Consumer Packaged Goods, everyday branded products (food, toiletries). Retail's supplier side |
| **AOV** | Average Order Value, revenue ÷ number of orders |
| **CSAT** | Customer Satisfaction score |
| **Churn** | Customers leaving |
| **SOP** | Standard Operating Procedure, the written document describing how a process runs. **Answer 2 reads these to find which signals a process consumes** |
| **S&OP** | Sales & Operations Planning, the monthly cycle where demand forecasts meet supply plans. The industry-standard cycle consumes historical sales, inventory levels, capacity metrics and financial inputs, **all internal and backward-looking, with no external risk signal.** That publicly documented absence is what Answer 2 demonstrates against a document your team did not write |
| **FVA (Forecast Value Added)** | A diagnostic asking whether each step of a forecasting process actually *improved* accuracy versus a naive baseline. Often steps make it worse. **Your academic precedent, proof the "audit the process, not just the number" idea is established** |
| **SRE** | Site Reliability Engineering, the software discipline of keeping systems running |
| **Blameless postmortem** | After an outage, a write-up focused on *systems* rather than people, including what stopped it being detected sooner. **Answer 2's direct ancestor** |
| **Decision rights** | Who is authorised to make which call. The brief asks for actions grounded in these |
| **Lever** | Something you can actually change, price, marketing spend, stock allocation. As opposed to weather |
| **BI** | Business Intelligence, dashboards and reporting (Power BI, Tableau) |
| **SI** | Systems Integrator, a firm like Accenture that implements technology for clients |
| **CDO** | Chief Data Officer |

---

## PART 5, LLM & AI terms

| Term | Plain meaning |
|---|---|
| **LLM** | Large Language Model, the text model (Claude, GPT, etc.) |
| **Token** | A chunk of text, roughly ¾ of a word. Models are billed per token, which is why your telemetry counts them |
| **Frontier model** | The largest, most capable current generation. Expensive. **You use one, once, for the narrative** |
| **Prompt caching** | Reusing a repeated prompt prefix across calls so you aren't billed full price each time. **Your contract context is cached** |
| **Hallucination** | The model stating something confidently that isn't true. **Your validator exists to make this structurally impossible in the narrative** |
| **Structured extraction** | Making the model return JSON with defined fields instead of prose, so downstream code can rely on it |
| **Span citation** | A pointer to the exact character range in a source document that a claim came from, not just "this ticket," but "these words in this ticket" |
| **Agentic / agent** | An LLM that can take actions, call tools, query data, decide next steps, rather than only producing text |
| **Agent swarm** | Many agents talking to each other. Popular; hard to audit; expensive. **You deliberately don't use one** |
| **Tool use** | Giving the model functions it can call (run this query, search these docs) |
| **Orchestration** | The control logic deciding what runs in what order. **Yours is deterministic code, not an LLM deciding**, that's the auditability argument |
| **Deterministic** | Same input always produces the same output. The opposite of an LLM's variability. **Your whole quantitative layer is deterministic** |

---

## PART 6, The one-paragraph version of your own system

If someone asks what you built and you have thirty seconds:

> *We take a business metric that moved. First we strip out seasonality to check the movement is real rather than a festival effect. Then we break the change into price, volume and mix, exact arithmetic, no model. We rank possible drivers statistically, then **test** the top ones against an unaffected comparison region, so correlation doesn't get reported as cause. We search the company's own support tickets and release logs for independent corroboration. Every sentence in the final report is bound to the query, rows and document passage behind it, and a validator rejects any sentence that isn't. If the evidence is weak we return Unknown with what we ruled out. And then we report the part nobody else does: whether a warning signal existed beforehand, which process should have been watching it, and who owns that.*

