# WhyChain — Design Checklist

Derived from the UI design brief, with corrections and additions. **Sections 1–3 are principles; section 6 is the checklist you actually run before shipping.**

---

## 1. The identity concept — keep this above everything else

**Claim → Proof.** The visual identity is not a colour scheme; it is the relationship between a sentence and its evidence. The reader should subconsciously learn:

```
Sentence → Evidence → Method → Result
```

Two acceptance tests to run on every screen:

- **Remove the logo.** Does it still read as a legitimate enterprise analytics system? If credibility depended on branding, the visual system is too thin.
- **Remove every AI label.** Delete "AI", "LLM", "Copilot", "smart", "intelligent". Does the interface still make complete sense? WhyChain is valuable because of deterministic analysis, causal verification, evidence provenance and signal-gap detection — not because a model is present.

---

## 2. Non-negotiables

**Document, not dashboard.** The narrative is the primary surface; data supports it. Not a KPI card grid, not a chart wall.

**Evidence state must never rely on colour alone.** Every state carries a label, a marker, and a typographic treatment:

```
● VERIFIED     Passed causal verification
○ HYPOTHESIS   Correlational, not causally verified
× REJECTED     Failed causal test
? UNKNOWN      Insufficient evidence
· CONTEXTUAL   Descriptive, no causal assertion
```

A reader must never mistake a hypothesis for a verified cause. This is the single most important information-design requirement in the product.

**UNKNOWN, stale, sparse, entitlement-limited and validator-rejection are first-class states**, designed with the same care as the success path — never styled as errors.

**Density over whitespace.** This is an analyst workstation. Compact metadata, tight table rows, strong alignment, controlled line lengths.

**Numbers are data, not decoration.** Tabular numerals, consistent precision, explicit units, right-aligned numeric columns, clear positive/negative notation. No giant KPI cards.

**One page.** The diagnosis contains the investigation. No Dashboard → Insights → Root Cause → Evidence navigation chain.

**Evidence opens in context.** Drawer, anchored panel or inline expansion. Never a page navigation, never a full-screen modal, never a lost scroll position.

**Cards only for real conceptual boundaries** — the evidence drawer, the monitoring plan, an operational finding. Reach for borders, typography and hierarchy first.

**Microcopy is factual.** Verified, hypothesis, rejected, evidence, method, freshness, owner, signal gap, blocking data. Never magic, smart, AI-powered, unlock, discover hidden insights.

**No chatbot personality.** "A material revenue deviation was detected", not "I found something interesting!"

### The prohibited list
Gradients of any kind · glassmorphism · glowing borders · neon · aurora backgrounds · decorative blobs or waves · gradient text · heavy drop shadows · oversized rounded containers · giant hero typography · AI sparkle icons · robot illustrations · emoji as UI icons · excessive pills · a card around every fact · three identical metric cards across the top · "AI-powered" language · hover scaling · bouncy motion · animated gradients · fake avatars · marketing feature sections.

---

## 3. Corrections to the source brief

Four things in the brief conflict with how the engine actually works. Fix them before they reach a screen a judge sees.

**Wireframes are information architecture, not visual style.** The brief's ASCII examples show *what appears and in what order*. Implementing them literally produces a monospace terminal aesthetic — which is its own kind of generated-looking design. Monospace belongs on evidence IDs, SQL, row counts and numeric columns. The narrative — the primary surface — must be set in a proper reading face.

**The evidence-drawer example is wrong.** It shows `Method: price/volume/mix bridge → Result: -18.1K orders`. The bridge produces **currency effects**, not order counts. A method and its result unit must agree, or the first analytically literate judge catches it.

**Freshness is not a percentage.** The confidence example shows `Freshness 97%`. Freshness is a timestamp, a lag, and an SLA verdict: `Orders · fresh · 14:05` / `Inventory · 5h 23m stale · SLA 72h breached`.

**Contribution tables must reconcile, not merely align.** The brief asks for aligned numbers. The stronger requirement: the dimensional contributions must visibly sum to the total movement, and that total must match the bridge. Being able to say "these add to 100%, and here is the same number in two places" is the point of using an exact identity.

---

## 4. Gaps to fill — states the brief missed

**The correlation trap needs its own treatment.** The brief covers rejected candidates generically. But the planted negative control — an event that correlates *perfectly* and caused nothing — is the anti-circularity proof and the strongest moment in the demo. Give it distinct presentation:

```
CORRELATION TRAP — REJECTED

Promotional campaign · correlation 0.94 with the movement

A correlation-ranking method would report this as the cause.

Difference-in-differences        FAIL — campaign also ran in East;
                                 East showed no comparable movement
Verdict                          Not causal
```

**Show that internal drivers come from an identity, not an estimate.** The two-track distinction is invisible unless designed. Internal structural drivers (price/volume/mix) are exact and sum to the total; external drivers (marketing, competitor, stock, weather) are regression estimates carrying intervals. Label the method on each, so the reader can see which numbers are arithmetic and which are inference.

**Set a measure for the narrative.** The brief calls for density but never bounds line length. The narrative is read continuously and needs ~65–75 characters. Density applies to tables, metadata and chrome — not to the prose that carries the product.

---

## 5. Demo path the design must make obvious

A first-time viewer should be able to follow this without explanation:

```
Open diagnosis → metric movement → narrative → click a claim → evidence
→ return in place → expand rejected candidates → the correlation trap
→ Answer 2 → signal gap → monitoring plan → confidence → telemetry
```

**Visual hierarchy test.** First thing seen: what happened. Then: what caused it. Then: how strong is the evidence. Then: what was ruled out. Then: why it wasn't anticipated. Then: what happens next. Then: how to inspect the proof.

If the eye lands first on a logo, KPI cards, or a decorative status row, the layout is wrong.

---

## 6. Acceptance checklist

### Enterprise credibility
- [ ] Reads as a production tool, not a landing page, SaaS template or chatbot
- [ ] Survives the remove-the-logo test
- [ ] Survives the remove-the-AI test
- [ ] Consistent tokens for colour, spacing, radius, elevation
- [ ] Typography creates hierarchy; cards do not
- [ ] Density appropriate to an analyst workstation

### Anti-slop
- [ ] No gradients, glassmorphism, glow, blobs, sparkles
- [ ] No oversized rounded cards, no excessive pills
- [ ] No hero section, no giant KPI row
- [ ] No hover scaling, no bouncy or ambient motion
- [ ] No AI marketing language anywhere in the copy
- [ ] Not a card grid

### Product-specific
- [ ] Narrative is the dominant surface, set in a reading face at 65–75 characters
- [ ] Every claim is clickable and visibly so
- [ ] Evidence opens in context; closing restores reading position exactly
- [ ] Verified / hypothesis / rejected / unknown / contextual are distinguishable **without colour**
- [ ] Method and unit agree on every evidence record
- [ ] Internal (exact) and external (estimated) drivers are visibly different kinds of number
- [ ] Rejected candidates preserved, with the test that killed each
- [ ] **Correlation trap has distinct treatment**
- [ ] Answer 2 is structurally separate and reads as a process finding
- [ ] All three signal-gap states reachable: gap found · not foreseeable · no gap
- [ ] Monitoring plan visible as a concrete artefact
- [ ] Confidence presented as evidence-derived, with its components
- [ ] UNKNOWN carries the same visual weight as a confident answer
- [ ] Stale sources visible globally and beside the affected claim
- [ ] Sparse history shows wide intervals and states that verification is unavailable
- [ ] Entitlement limits are announced, never silently omitted
- [ ] Validator rejections are inspectable and read as operational, not debug
- [ ] Feedback is inline per claim, not a modal
- [ ] Clarification is answerable and implies a re-run
- [ ] Telemetry reads as a receipt

### Information design
- [ ] Numeric columns aligned, tabular numerals, explicit units
- [ ] Contribution figures **reconcile** to the bridge total
- [ ] Tables dense, sortable where useful, expandable for detail
- [ ] Colour carries state, never state alone
- [ ] Progressive disclosure for statistical depth
- [ ] External signals labelled contextual and subordinate to internal evidence

### Interaction & accessibility
- [ ] Evidence click feels instant (100–200ms)
- [ ] Keyboard navigable end to end, visible focus everywhere
- [ ] Contrast sufficient in both themes
- [ ] Evidence state legible to a screen reader
- [ ] Semantic headings, accessible tables and drawers
- [ ] `prefers-reduced-motion` respected
- [ ] No horizontal page overflow; wide tables scroll in their own container
- [ ] Loading states name the actual stage running — never fake thinking animation
- [ ] Errors state what failed, what's affected, when it last worked, what to do
- [ ] Empty states explain the analytical meaning, not "no data found"
