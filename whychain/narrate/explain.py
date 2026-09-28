"""Explain one card of a finding: what it shows, and what it means for the reader.

The summary explains the finding; this explains a single card on its page (the
bridge, the fishbone, the what-if, the decision), which is where a reader
actually gets stuck. It is the summary's own machinery pointed at a smaller
table: the model is given only the facts that card displays, writes at most
three sentences that cite them, and the same validator removes any sentence
whose figure is not in a fact it cites. What survives is what is shown.

A card is constant for a given finding, so its explanation is too: the call is
content-addressed like every other model call, written once by `make warm-ai`
and read from disk after that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from whychain.evidence import Unit
from whychain.llm import MAX_TOKENS, UNSET, ChatModel, Task, model_for
from whychain.narrate.brief import Brief, Fact, _fact, _plain, build_brief
from whychain.narrate.validate import Sentence, ValidationResult, validate
from whychain.narrate.writer import SENTENCE_SCHEMA, _house_style

CARDS = ("chain", "bridge", "fishbone", "whatif", "decide")

MAX_EXPLAIN_SENTENCES = 3

SYSTEM = """\
You explain one card of a business diagnosis to a finance reader: what the card \
shows, and what it means for the decision in front of them. You are not writing \
the summary of the whole finding; stay on this card.

You are given the card's name and a table of facts. Every fact has an id, a \
claim, and a `display` string that is the ONLY way its number may be written.

Rules, all of which are checked mechanically after you answer:

1. At most three short sentences. Every sentence cites at least one fact id.
2. Any figure you print is copied character for character from the `display` of \
a fact that sentence cites. Do not convert, round, add or compare figures.
3. Do not name a person, role, region or product that is not in the table. \
When a sentence names a cause (a release number, the weather), it also cites \
that cause's fact, so what it names can be checked.
4. Facts whose state is `rejected` were tested and ruled out: say so, never \
state them as causes. Facts whose state is `untested` could not be tested yet.
5. Everyday words a busy director reads in ten seconds. No jargon: never write \
"attribution", "baseline", "variance", "slice", "scenario", "decomposition" or \
"elasticity" (say "how much sales react to price"). Each sentence under twenty \
words. Say what it means for the decision, not how it was computed.
6. A cause's figure is that cause's own part of the fall, never the whole fall.\
"""

# What each card is, in a line the model is given with the facts.
CARD_PURPOSE = {
    "chain": "The chain: the eight links from a movement to a signature. Every link has "
             "to hold; where one breaks, nothing after it is attempted. Walk the links in "
             "order, one short clause each. For the decision and the signature say who does "
             "it, never whether it has happened yet: that changes after this is written.",
    "bridge": "The bridge: how the daily figure got from the fortnight before to "
              "this window, step by step, one step per verified cause.",
    "fishbone": "The fishbone: every explanation that was considered, and whether "
                "it held, was ruled out, or could not be tested yet.",
    "whatif": "The what-if: a projection of what a price change would do, with the "
              "assumptions it rests on. A projection, not a measurement.",
    "decide": "What to do: the actions proposed for each verified cause, who owns "
              "them, and what each is expected to recover.",
}


@dataclass(frozen=True)
class Explanation:
    card: str
    sentences: tuple[Sentence, ...]
    validation: ValidationResult
    writer: str
    model: str
    model_calls: int = 0
    cache_hits: int = 0

    def as_dict(self) -> dict:
        # The citation tags ("(f-cause-1)") are how the validator binds a
        # sentence to its facts; a reader sees the sentence without them.
        return {
            "card": self.card,
            "text": " ".join(_untag(s.text) for s in self.sentences),
            "sentences": [{**s.as_dict(), "text": _untag(s.text)} for s in self.sentences],
            "accepted": len(self.validation.accepted),
            "rejected": len(self.validation.rejected),
            "writer": self.writer,
            "model": self.model,
            "model_calls": self.model_calls,
            "cache_hits": self.cache_hits,
        }


def _untag(text: str) -> str:
    return re.sub(r"\s*[\(\[](?:f-[\w-]+(?:,\s*)?)+[\)\]]", "", text).strip()


def _readable(description: str | None) -> str:
    """A candidate as a reader says it: the record's own ids made into words.

    "Promotion promo-monsoon-sale active in East" reached the model as it is,
    and the model quoted the id back into a sentence for a finance director.
    """
    text = _plain(description)
    text = re.sub(r"\bPromotion promo-([a-z0-9-]+)", lambda m: "The " + m.group(1).replace("-", " ") + " promotion", text)
    return re.sub(r"\b([a-z]+)-([a-z]+)-([a-z0-9-]+)\b", lambda m: m.group(0).replace("-", " "), text)


def _shown(fact_id: str, claim: str, display: str, state: str | None = None) -> Fact:
    """A fact whose display is already the text the card shows (an assumption
    like "-1.40" or "+10%"), rather than a number to be formatted."""
    return Fact(id=fact_id, claim=claim, value=None, unit=Unit.NONE, display=display,
                kind="assumption", state=state)


def _chain_facts(result: dict, cand: dict, view: dict | None, worst: dict | None) -> list[Fact]:
    """The chain as this reader's card draws it (`chainLinks` in ui/app.html).

    `result` is the full diagnosis; `view` is this reader's projection, which is
    what the card is drawn from, so a link the card withholds is withheld here
    too. Decided and Signed change as people act, so they are given by what
    they require: an explanation written once must not contradict the page
    after a click.
    """
    view = view or result
    rec = view.get("reconciliation") or {}
    out: list[Fact] = []
    if worst:
        out.append(_fact("f-chain-moved", "Moved: on the worst day the figure came in this much "
                         "short of what was expected, far outside the normal range",
                         abs(float(worst["delta"])), Unit.INR, "chain"))
    if rec.get("state") == "agreed":
        out.append(_shown("f-chain-confirmed", "Confirmed: the finance ledger agrees with the figure",
                          f"within {100 * abs(float(rec.get('worst_residual') or 0)):.1f}%"))
    elif rec.get("state") == "contradicted":
        out.append(_shown("f-chain-confirmed", "Confirmed: the finance ledger disagrees, so the "
                          "data is checked before any cause", "ledger disagrees"))
    top = ((view.get("ranking") or {}).get("exact") or [None])[0]
    if top:
        out.append(_shown("f-chain-located", f"Located: {_plain(top.get('label')).replace(' · ', ': ')} "
                          "carries this share of the movement, exactly",
                          f"{round(100 * abs(float(top.get('share') or 0)))}%"))
    else:
        out.append(_shown("f-chain-located", "Located: price, volume and mix add back exactly to "
                          "the total", "adds back exactly"))
    n = len(result.get("verified") or [])
    tested = "each passed every test"
    if view.get("verified") is not None and cand:
        tested += (f"; {len(cand.get('rejected') or [])} other explanations ruled out, "
                   f"{len(cand.get('cannot_verify') or [])} not yet testable")
    out.append(_shown("f-chain-caused", f"Caused: causes verified, {tested}", f"{n} verified"))
    if view.get("verified"):
        docs = sum(int(v.get("supporting_documents") or 0) for v in view.get("verified") or [])
        out.append(_shown("f-chain-evidence", "Evidence: customer tickets and notes quoted word "
                          "for word", f"{docs} documents"))
    else:
        out.append(_shown("f-chain-evidence", "Evidence: the customer tickets behind the causes "
                          "are shown in the analyst view, not in this one", "in the analyst view"))
    lever = next((d for d in result.get("decisions") or [] if d.get("controllable")), None)
    if lever:
        out.append(_shown("f-chain-lever", f"Lever: {str(lever.get('lever', 'an action')).replace('_', ' ')}, "
                          f"owned by the {str(lever.get('owner', '')).replace('_', ' ')}", "has an owner"))
    out.append(_shown("f-chain-decided", "Decided: the lever's owner decides; nothing executes "
                      "until they do", "owner decides"))
    out.append(_shown("f-chain-signed", "Signed: the finance director signs by name; if the "
                      "evidence changes it must be signed again", "signed by name"))
    return out


def card_brief(card: str, result: dict, candidates: dict | None = None,
               withheld: bool = False, view: dict | None = None,
               worst: dict | None = None) -> Brief:
    """The facts one card displays, and nothing else it does not.

    Built from the same result the page renders, so the explanation cannot
    describe a card the reader is not looking at.
    """
    if card not in CARDS:
        raise ValueError(f"no such card: {card}")
    base = build_brief(result)
    keep: list[Fact] = []

    if card == "bridge":
        keep += [f for f in base.facts if f.id in ("f-movement", "f-movement-pct")]
        over = next((f for f in base.facts if f.id == "f-overlap"), None)
        if over:
            # "Gross attribution over the movement" came back as "combined
            # attribution exceeds the total movement", which no reader follows.
            keep.append(Fact(id=over.id, value=over.value, unit=over.unit,
                             display=f"{round(100 * float(over.value or 0))}%" if over.value else over.display,
                             kind=over.kind, state=over.state,
                             claim="measured one at a time, the causes add up to this share of "
                                   "the fall, more than all of it, because some lost sales were "
                                   "hit by both; the bridge scales them so they add up exactly"))
        wf = result.get("waterfall") or {}
        if wf.get("start"):
            keep.append(_fact("f-bridge-before", f"the daily figure, {wf['start'].get('label', 'before')}",
                              wf["start"].get("value"), Unit.INR, "bridge"))
        for i, step in enumerate(wf.get("steps") or [], 1):
            keep.append(_fact(f"f-bridge-step-{i}",
                              f"bridge step for {_plain(step.get('label'))}"
                              + (", scaled so the steps add up to the fall"
                                 if wf.get("scaled_for_overlap") else ""),
                              step.get("value"), Unit.INR, "bridge"))
        if wf.get("end"):
            keep.append(_fact("f-bridge-after", f"the daily figure, {wf['end'].get('label', 'this window')}",
                              wf["end"].get("value"), Unit.INR, "bridge"))

    elif card == "fishbone":
        keep += [f for f in base.facts if f.kind == "cause"]
        cand = candidates or {}
        for i, c in enumerate(cand.get("rejected") or [], 1):
            keep.append(_shown(f"f-ruled-out-{i}",
                               f"ruled out: {_readable(c.get('description'))}; "
                               f"{c.get('reason') or 'failed the tests'}",
                               "ruled out", state="rejected"))
        if withheld:
            keep.append(_shown("f-withheld", "the explanations tested and ruled out are "
                               "withheld from this reader; the analyst view shows them",
                               "withheld"))
        for i, c in enumerate(cand.get("cannot_verify") or [], 1):
            keep.append(_shown(f"f-untested-{i}",
                               f"not yet testable: {_readable(c.get('description'))}",
                               "not yet testable", state="untested"))

    elif card == "whatif":
        for sc in result.get("scenarios") or []:
            # A projection over the horizon changes with the horizon buttons;
            # leaving it out keeps one explanation per price position, each
            # of which is warmed.
            if not sc.get("available") or sc.get("horizon_days"):
                continue
            sid = sc.get("scenario_id")
            keep.append(_fact(f"f-whatif-{sid}", f"{sc.get('question')} Effect on "
                              f"{sc.get('effect_of')}, per day", sc.get("effect_inr_per_day"),
                              Unit.INR, "scenario"))
            for j, other in enumerate(sc.get("alongside") or [], 1):
                keep.append(_fact(f"f-whatif-{sid}-also-{j}",
                                  f"{sc.get('question')} Effect on {other.get('name')}, per day",
                                  other.get("inr_per_day"), Unit.INR, "scenario"))
            for j, a in enumerate(sc.get("assumptions") or [], 1):
                keep.append(_shown(f"f-whatif-{sid}-assume-{j}",
                                   f"assumption for {sid}: {a.get('name')} ({a.get('basis')})",
                                   str(a.get("value"))))

    elif card == "chain":
        keep += _chain_facts(result, candidates or {}, view, worst)

    else:  # decide
        keep += [f for f in base.facts if f.kind in ("decision", "cause")]

    return Brief(run_id=base.run_id, kpi=base.kpi, region=base.region, window=base.window,
                 verdict=base.verdict, facts=tuple(keep), entities=base.entities)


def _template(card: str, brief: Brief) -> tuple[Sentence, ...]:
    """What is said when there is no model, or nothing it wrote survived.

    Plain restatements of the card's own facts, each citing them, so they pass
    the same validator.
    """
    f = {x.id: x for x in brief.facts}
    out: list[Sentence] = []
    if card == "bridge" and "f-bridge-before" in f and "f-bridge-after" in f:
        out.append(Sentence(f"The daily figure went from {f['f-bridge-before'].display} to "
                            f"{f['f-bridge-after'].display}, one step for each verified cause.",
                            ("f-bridge-before", "f-bridge-after")))
    elif card == "fishbone":
        held = [x for x in brief.facts if x.kind == "cause"]
        out_ = [x for x in brief.facts if x.state == "rejected"]
        if held:
            # No count: a number here is not on any fact, and the validator
            # rightly removes it.
            out.append(Sentence("The verified explanations held up under every test.",
                                tuple(x.id for x in held)))
        if out_:
            out.append(Sentence("The others were tested and ruled out, or could not be tested yet.",
                                tuple(x.id for x in out_)))
    elif card == "whatif":
        first = next((x for x in brief.facts if x.kind == "scenario"), None)
        if first:
            out.append(Sentence(f"This is a projection, not a measurement: {first.display} a day "
                                "under the stated assumptions.", (first.id,)))
    elif card == "chain" and "f-chain-moved" in f:
        out.append(Sentence("Each link must hold before the next is tried, from the movement "
                            "to a signature by name.", ("f-chain-moved", "f-chain-signed")))
    elif card == "decide":
        first = next((x for x in brief.facts if x.kind == "decision"), None)
        if first:
            out.append(Sentence(f"The first action is expected to recover {first.display} a day.",
                                (first.id,)))
    return tuple(out)


def explain(card: str, result: dict, candidates: dict | None = None, *,
            withheld: bool = False, view: dict | None = None, worst: dict | None = None,
            backend: ChatModel | None = UNSET,
            known_entities: frozenset[str] = frozenset()) -> Explanation:
    """Explain one card. A model failure falls back to the template, never to an error."""
    brief = card_brief(card, result, candidates, withheld, view, worst)
    model = model_for(Task.NARRATE) if backend is UNSET else backend
    calls = hits = 0
    sentences: tuple[Sentence, ...] = ()
    writer = "template"
    if model is not None and brief.facts:
        try:
            completion = model.complete(
                system=SYSTEM,
                user=("Card: " + CARD_PURPOSE[card] + "\n\nFacts available to you:\n"
                      + json.dumps(brief.for_model(), indent=1)
                      + "\n\nExplain this card."),
                schema=SENTENCE_SCHEMA,
                max_tokens=MAX_TOKENS["narrate"],
            )
            payload = json.loads(completion.text or "{}")
            sentences = tuple(
                # Tags stripped before validation: written in square brackets they
                # are not recognised as citations, and the digits in an id like
                # "f-whatif-price_move-also-1" read as an invented "-1". The
                # citations themselves travel separately, in `cites`.
                Sentence(text=_untag(_house_style(str(s["text"]))), cites=tuple(str(c) for c in s["cites"]))
                for s in payload.get("sentences", [])[:MAX_EXPLAIN_SENTENCES]
            )
            calls, hits = (0, 1) if completion.cached else (1, 0)
            writer = "model"
        except Exception:
            sentences = ()
    validation = validate(list(sentences), brief, known_entities=known_entities)
    if not validation.accepted:
        writer = "template"
        validation = validate(list(_template(card, brief)), brief, known_entities=known_entities)
    return Explanation(card=card, sentences=validation.accepted, validation=validation,
                       writer=writer, model=model.name if (model and writer == "model") else "none",
                       model_calls=calls, cache_hits=hits)
