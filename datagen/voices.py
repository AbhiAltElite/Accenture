"""The document estate: many voices, several registers, and a chain over time.

The first version of this generated 7,419 documents from 28 fixed strings, six
of which appeared a thousand times each, all with the same `doc_type`. Three
things were wrong with that, and only the first is cosmetic.

**It made corroboration hollow.** "Twenty-four tickets describe what happened,
in the company's own words" is a strong claim until a reader clicks two
citations and finds the same sentence twice.

**It made the model extractor unprovable.** The argument for reading tickets
with a model is that customers do not use the company's vocabulary. But those
templates were written next to the keyword table, so every phrasing in the data
was already in the rules, and the model could never demonstrate the thing it is
there for. `OFF_VOCABULARY` below exists to fix that specifically: real
complaints, describing real issues, using none of the words the `RuleExtractor`
looks for. A rule table misses them and a reader does not.

**There was no chain.** 7,411 tickets, seven ops notes, one release log. Real
corroboration crosses document types and accumulates over hours: customers
complain first, an agent notices a pattern, a store or a supplier reports it, an
incident is opened, and only then does an operational record exist. A diagnosis
that can show that sequence is showing how the business found out. One that
counts matching strings is not.

So documents are composed rather than chosen, from fragments that vary by
speaker. A customer writes in lower case with a typo and no order id; an
incident record carries a ticket reference, a timestamp and a severity. The
registers should be distinguishable at a glance, because in a real estate they
are.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from datagen.scenarios import CauseKind

# ---------------------------------------------------------------------------
# Customer voice. Composed, so the same complaint is never written twice.
# ---------------------------------------------------------------------------

OPENERS = (
    "", "", "", "Hi, ", "Hello, ", "hi ", "Please help. ", "Third time now. ",
    "Really frustrated. ", "Not sure if this is known but ", "FYI ",
)

CLOSERS = (
    "", "", "", "", " Please fix.", " Any update?", " Losing patience.",
    " Have been a customer for years.", " Will try again tomorrow.",
    " Placed it on the website instead.", " Gave up and went elsewhere.",
    " Screenshot attached.", " Ticket raised earlier too, no reply.",
)

# Phrasings a keyword table catches. These keep the rule-based path working, so
# the two extraction paths can be compared on the same data rather than the
# rules simply failing everywhere.
IN_VOCABULARY: dict[CauseKind, tuple[str, ...]] = {
    CauseKind.INTERNAL_BUG: (
        "cannot complete checkout on the app, the card entry page is blank",
        "the payment step crashes every time on Android",
        "app checkout broken since the last release, it spins and then fails",
        "unable to pay on mobile, the card form does not load at all",
        "checkout fails right at the end, card declined every time",
        "the payment page will not load on my phone",
    ),
    CauseKind.EXTERNAL_WEATHER: (
        "delivery delayed due to flooding in the area, no update for two days",
        "store was shut because of the rain, could not collect my order",
        "shipment stuck, courier says roads are closed after heavy rainfall",
        "my delivery was late again, apparently the roads are closed",
        "the store was closed because of the storm",
    ),
    CauseKind.STOCKOUT: (
        "the item I wanted has been out of stock for a week now",
        "cannot find the product in my area any more",
        "order cancelled by the seller citing unavailability",
        "everything in this range is sold out",
    ),
    CauseKind.COMPETITOR_PROMO: (
        "found the same pack cheaper elsewhere, cancelling this order",
        "your price went up compared to the other app",
        "there is a much better discount on the other site",
    ),
    CauseKind.PRICE_CHANGE: (
        "the price of this item changed between adding it and checking out",
        "introductory offer seems to have ended without notice",
        "the price went up overnight with no warning",
    ),
}

# Phrasings a keyword table misses, describing exactly the same issues. Every
# line here was written by reading `_ISSUE_TERMS` in the rule extractor and
# deliberately avoiding all of it. These are what the model is for, and what
# makes the with-model / without-model contrast a real comparison rather than a
# demonstration of prose style.
OFF_VOCABULARY: dict[CauseKind, tuple[str, ...]] = {
    CauseKind.INTERNAL_BUG: (
        "the last screen just spins forever and nothing happens",
        "it keeps kicking me back to the basket at the final step",
        "the app freezes when I try to confirm, then logs me out",
        "goes round and round on the confirm screen, never finishes",
        "after the update it dies right at the end, every single time",
        "spinning wheel and then it throws me out, three attempts now",
        "the little wheel spins and spins and then nothing",
        "wont let me finish on my phone, works fine on the laptop",
    ),
    CauseKind.EXTERNAL_WEATHER: (
        "nobody could get to the shop, whole road was under water",
        "the shutters were down all day, no one there",
        "van never turned up, apparently they could not get through",
        "everything is waterlogged here, nothing is moving",
        "driver called to say he cannot reach us",
    ),
    CauseKind.STOCKOUT: (
        "shelf has been empty for days, staff say they do not know when",
        "they keep saying it is coming but it never arrives",
        "nothing left in the size I need, hasn't been for a while",
        "the whole section is bare",
    ),
    CauseKind.COMPETITOR_PROMO: (
        "the other lot are doing it for a lot less right now",
        "saw a much better deal on a different app this morning",
        "why would I buy here when it is twenty rupees less elsewhere",
    ),
    CauseKind.PRICE_CHANGE: (
        "it was one number in the basket and another at the end",
        "cost me more than it said it would",
        "the deal I signed up for has quietly gone",
    ),
}

BACKGROUND = (
    "delivery arrived on time, no issues",
    "requesting a refund for a damaged item",
    "how do I change my delivery address",
    "product quality was good but packaging was torn",
    "please cancel my subscription renewal",
    "the invoice shows the wrong GST number",
    "can I change the delivery slot",
    "the packaging was fine this time, thank you",
    "do you deliver to my pin code",
    "wrong item sent, need an exchange",
    "the app logged me out for no reason",
    "can I get a GST invoice for a business order",
    "loyalty points have not been credited",
    "asked for a callback last week and never got one",
)

# Roughly one ticket in nine arrives with a typo. Enough that the text does not
# read as machine-written, not so much that it becomes a spelling exercise.
TYPOS = (
    ("the", "teh"), ("and", "an"), ("cannot", "cant"), ("does not", "doesnt"),
    ("payment", "payement"), ("delivery", "delivary"), ("please", "pls"),
    ("received", "recieved"), ("checkout", "chekout"),
)


@dataclass(frozen=True)
class VoicePack:
    """Everything one industry's people say, and how they say it.

    Four speakers and one shape. Customers (or dealers, or discoms) write in
    their own words; an agent summarises the pattern across contacts; the field
    or the supplier confirms it; an incident record exists only once somebody
    has decided it is one thing rather than several. That sequence is the same
    everywhere and lives in `chain`. Only the words are here.

    `off_vocabulary` is the part that has to survive the move to a new industry
    intact: roughly two in five event-driven complaints must use phrasing the
    rule table does not contain, or the with-model comparison stops measuring
    anything. A pack whose off-vocabulary accidentally overlaps its own
    industry's `Vocabulary` terms would quietly make the rule extractor look
    better than it is, which is why a test checks the overlap rather than
    trusting the prose.
    """

    openers: tuple[str, ...]
    closers: tuple[str, ...]
    background: tuple[str, ...]
    typos: tuple[tuple[str, str], ...]
    in_vocabulary: dict[str, tuple[str, ...]]
    off_vocabulary: dict[str, tuple[str, ...]]
    agent_summaries: dict[str, str]
    field_reports: dict[str, str]
    incidents: dict[str, str]
    external_records: dict[str, str]
    # Which cause kind's closing record is filed as a deployment log rather than
    # an external notice, and the identifier that appears in it.
    release_kind: str = "internal_bug"
    release_label: str = "4.05"


@dataclass(frozen=True)
class Voice:
    """One document, and what kind of speaker produced it."""

    doc_type: str
    text: str
    ts: datetime
    region: str


def _distort(text: str, rng: random.Random, typos: tuple = TYPOS) -> str:
    """Ordinary human mangling: a typo, a lost capital, a stray full stop."""
    if rng.random() < 0.11:
        wrong, right = rng.choice(typos)
        text = text.replace(wrong, right, 1)
    if rng.random() < 0.30:
        text = text[0].upper() + text[1:] if text else text
    if rng.random() < 0.55 and not text.endswith("."):
        text += "."
    return text


def customer_ticket(
    kind: CauseKind | None,
    when: datetime,
    region: str,
    rng: random.Random,
    pack: VoicePack | None = None,
) -> Voice:
    """A ticket in the customer's own words.

    Roughly two in five event-driven complaints use vocabulary the rule table
    does not contain. That ratio is the point: high enough that a keyword-only
    reading visibly under-counts, low enough that the rules are not useless and
    the comparison stays honest.
    """
    pack = pack or RETAIL_VOICES
    if kind is None:
        body = rng.choice(pack.background)
    elif rng.random() < 0.4 and kind in pack.off_vocabulary:
        body = rng.choice(pack.off_vocabulary[kind])
    else:
        body = rng.choice(pack.in_vocabulary.get(kind, pack.background))

    text = rng.choice(pack.openers) + body + rng.choice(pack.closers)
    return Voice("support_ticket", _distort(text, rng, pack.typos), when, region)


# ---------------------------------------------------------------------------
# The chain. Each link is a different speaker, later than the last.
# ---------------------------------------------------------------------------

AGENT_SUMMARIES: dict[CauseKind, str] = {
    CauseKind.INTERNAL_BUG:
        "Contact summary: {n} calls this shift about the app failing at the "
        "final step. All Android. Advised customers to use the web journey. "
        "Escalating to the ecommerce queue.",
    CauseKind.EXTERNAL_WEATHER:
        "Contact summary: {n} calls about undelivered orders in {region}. "
        "Common thread is access, not stock. Told customers we will re-attempt "
        "once conditions allow.",
    CauseKind.STOCKOUT:
        "Contact summary: {n} calls about availability in {region}. Customers "
        "report empty shelves rather than a website issue, so this is supply "
        "rather than listing.",
    CauseKind.COMPETITOR_PROMO:
        "Contact summary: {n} cancellations quoting a cheaper price elsewhere. "
        "No service complaint attached to any of them.",
    CauseKind.PRICE_CHANGE:
        "Contact summary: {n} contacts about a price differing between basket "
        "and payment. Confirmed the list price changed mid-session.",
}

FIELD_REPORTS: dict[CauseKind, str] = {
    CauseKind.EXTERNAL_WEATHER:
        "Store report, {region}: shutters down from opening. Water across the "
        "approach road, no footfall to speak of. Staff sent home at midday.",
    CauseKind.STOCKOUT:
        "Store report, {region}: gaps across the affected range since the "
        "weekend. Replenishment has not arrived and we have no ETA from the DC.",
    CauseKind.INTERNAL_BUG:
        "Store report, {region}: customers coming in saying the app would not "
        "let them pay. Several completed the purchase at the till instead.",
    CauseKind.COMPETITOR_PROMO:
        "Store report, {region}: the competitor two streets over has price "
        "cards up on the same range. Noticeably quieter than last week.",
    CauseKind.PRICE_CHANGE:
        "Store report, {region}: several customers queried the shelf price "
        "against what the app charged them.",
}

INCIDENTS: dict[CauseKind, str] = {
    CauseKind.INTERNAL_BUG:
        "INC-{num}: Checkout failure on Android following release {release}. "
        "Severity 1. Card entry component fails to mount. {n} tickets and "
        "{calls} calls attached. Owner: ecommerce. Rollback under discussion.",
    CauseKind.EXTERNAL_WEATHER:
        "INC-{num}: Distribution disrupted in {region} by severe weather. "
        "Severity 2. {n} deliveries affected. Owner: supply planning. No "
        "system fault; this is an access and safety issue.",
    CauseKind.STOCKOUT:
        "INC-{num}: Availability shortfall in {region}. Severity 2. Supplier "
        "confirms a shortfall against the agreed schedule. Owner: supply "
        "planning.",
    CauseKind.COMPETITOR_PROMO:
        "INC-{num}: Competitor pricing activity noted in {region}. Severity 3. "
        "Logged for commercial review; no operational fault.",
    CauseKind.PRICE_CHANGE:
        "INC-{num}: List price change applied mid-session in {region}. "
        "Severity 3. Owner: category management.",
}

# The final link, and the one that is genuinely a different document class:
# something from outside the company, or a formal record of what was done.
EXTERNAL_RECORDS: dict[CauseKind, str] = {
    CauseKind.INTERNAL_BUG:
        "Release note {release}: rollback of the card entry component applied "
        "to Android. Approved by the ecommerce lead. Checkout success rate "
        "recovering.",
    CauseKind.EXTERNAL_WEATHER:
        "Carrier notification, {region}: service suspended in affected "
        "postcodes until conditions permit. Consignments held at the depot. "
        "No revised ETA at this time.",
    CauseKind.STOCKOUT:
        "Supplier notification: allocation for {region} reduced against the "
        "agreed schedule following a production shortfall. Recovery expected "
        "in the next cycle.",
    CauseKind.COMPETITOR_PROMO:
        "Market intelligence note: competitor promotional pricing observed "
        "across the affected range in {region}.",
    CauseKind.PRICE_CHANGE:
        "Pricing change record: list price updated on the affected range. "
        "Approved by category management.",
}


def chain(
    kind: CauseKind,
    start: date,
    end: date,
    region: str,
    ticket_count: int,
    rng: random.Random,
    pack: VoicePack | None = None,
    release: str | None = None,
) -> list[Voice]:
    """The operational record of one event, as four documents in sequence.

    The order is the finding. Customers notice first, an agent sees the pattern
    across several contacts, the field or the supplier confirms it, and an
    incident record exists only once somebody has decided it is one thing rather
    than several. Emitting all four with the same timestamp would lose exactly
    the part worth showing.

    The closing record lands *after* the event ends, and that is not cosmetic. A
    rollback note is a shipped change like any other, so the candidate scanner
    picks it up; dated inside the window it correlates with the fall and gets
    verified as a cause of it. The first version of this did exactly that and
    the console reported the rollback as a reason revenue dropped, which is the
    fix being blamed for the fault. A remediation completes when the impact
    does, so dating it truthfully also stops it being mistaken for a cause.
    """
    pack = pack or RETAIL_VOICES
    release = release or pack.release_label
    out: list[Voice] = []
    day = datetime(start.year, start.month, start.day, tzinfo=UTC)

    if kind in pack.agent_summaries:
        out.append(Voice(
            "agent_note",
            pack.agent_summaries[kind].format(
                n=max(ticket_count // 3, 2), region=region
            ),
            day + timedelta(hours=13),
            region,
        ))

    if kind in pack.field_reports:
        out.append(Voice(
            "field_report",
            pack.field_reports[kind].format(region=region),
            day + timedelta(hours=17),
            region,
        ))

    if kind in pack.incidents:
        out.append(Voice(
            "incident",
            pack.incidents[kind].format(
                num=rng.randint(4000, 4999), region=region, release=release,
                n=max(ticket_count, 1), calls=max(ticket_count // 3, 1),
            ),
            day + timedelta(days=1, hours=9),
            region,
        ))

    if kind in pack.external_records:
        closed = datetime(end.year, end.month, end.day, tzinfo=UTC)
        out.append(Voice(
            "release_log" if kind == pack.release_kind else "external_notice",
            pack.external_records[kind].format(region=region, release=release),
            closed + timedelta(days=1, hours=15),
            region,
        ))

    return out


# Retail's pack, assembled from the tables above rather than restating them, so
# there is one place each phrase lives.
RETAIL_VOICES = VoicePack(
    openers=OPENERS,
    closers=CLOSERS,
    background=BACKGROUND,
    typos=TYPOS,
    in_vocabulary=IN_VOCABULARY,
    off_vocabulary=OFF_VOCABULARY,
    agent_summaries=AGENT_SUMMARIES,
    field_reports=FIELD_REPORTS,
    incidents=INCIDENTS,
    external_records=EXTERNAL_RECORDS,
    release_kind=CauseKind.INTERNAL_BUG,
    release_label="4.05",
)
