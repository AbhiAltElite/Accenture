"""Turning retrieved text into structured, citable claims.

Retrieval finds documents that look relevant. Extraction decides what they
actually say: what kind of problem is described, which part of the business it
touches, and which words support that reading.

Two implementations behind one protocol. The rule-based extractor is the default
and runs offline, so the whole pipeline works without an API key and produces
identical output on repeated runs. A model-based extractor reads the same
quarantined text and returns the same shape; it reads prose the vocabulary
misses, which is what a real deployment needs.

Every extraction carries the span it came from. An extraction without a span is
an opinion, and the narrative layer has no way to show a reader an opinion.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from whychain.corroborate.documents import sentence_spans
from whychain.corroborate.quarantine import Quarantined


class IssueType(StrEnum):
    CHECKOUT_FAILURE = "checkout_failure"
    PAYMENT_FAILURE = "payment_failure"
    DELIVERY_DELAY = "delivery_delay"
    STOCKOUT = "stockout"
    PRICING = "pricing"
    QUALITY = "quality"
    OTHER = "other"


@dataclass(frozen=True)
class Extraction:
    """One structured reading of one passage."""

    doc_id: str
    issue: IssueType
    span: tuple[int, int]
    quote: str
    channel: str | None = None
    device: str | None = None
    category: str | None = None
    flags: tuple[str, ...] = ()          # carried from quarantine, for the audit trail
    confidence: float = 1.0


@runtime_checkable
class Extractor(Protocol):
    def extract(self, documents: Sequence[Quarantined]) -> list[Extraction]: ...


# Vocabulary. Ordered most specific first, because "payment page will not load"
# is a checkout failure rather than a generic payment complaint.
_ISSUE_TERMS: tuple[tuple[IssueType, tuple[str, ...]], ...] = (
    (IssueType.CHECKOUT_FAILURE,
     ("checkout fails", "checkout broken", "cannot complete checkout", "card entry",
      "card form", "card page", "unable to complete purchase", "cannot complete",
      "checkout flow", "payment page will not load", "payment page")),
    (IssueType.PAYMENT_FAILURE,
     ("payment step", "cannot pay", "payment failed", "crashes at payment",
      "card declined", "transaction failed")),
    (IssueType.DELIVERY_DELAY,
     ("delivery delayed", "arrived late", "delivery was late", "shipment stuck",
      "courier", "roads are closed", "no update for", "could not collect",
      # Customers experience weather as a closure or a delay, not as weather.
      "rainfall", "flooding", "flood", "storm", "store was shut", "footfall",
      "distribution centre", "closed because")),
    (IssueType.STOCKOUT,
     ("out of stock", "unavailability", "cannot find the product", "sold out",
      "no stock", "availability")),
    (IssueType.PRICING,
     ("cheaper elsewhere", "price went up", "price of this item changed",
      "introductory offer", "price cut", "prices across", "cut personal care prices",
      "discount", "promotion")),
    (IssueType.QUALITY,
     ("damaged", "packaging was torn", "quality was", "defective", "broken item")),
)

# Words that place a document on a channel, device or category. This is what
# lets a candidate inherit the scope of the note describing it, rather than being
# measured across a whole region where other things were also happening.
_SCOPE_TERMS: dict[str, dict[str, str]] = {
    "channel": {
        "app": "app", "mobile app": "app", "android": "app", "ios": "app",
        "website": "web", "web": "web", "browser": "web", "desktop site": "web",
        "store": "store", "outlet": "store", "shop": "store", "footfall": "store",
    },
    "device": {
        "android": "mobile", "iphone": "mobile", "mobile": "mobile",
        "desktop": "desktop", "laptop": "desktop", "tablet": "tablet",
    },
    "category": {
        "personal care": "personal_care", "packaged food": "packaged_foods",
        "home care": "home_care", "beverage": "beverages", "snack": "snacks",
    },
}


def _first_term(text: str, terms: dict[str, str]) -> str | None:
    """Longest match wins, so 'mobile app' beats 'app'."""
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for phrase, value in terms.items():
        if phrase in lowered and (best is None or len(phrase) > best[0]):
            best = (len(phrase), value)
    return best[1] if best else None


class RuleExtractor:
    """Vocabulary matching over quarantined text.

    Deterministic and offline. It reads what it recognises and nothing else,
    which is a real limitation: a complaint phrased in a way the vocabulary does
    not cover reads as `other`. That is visible in the output rather than being
    smoothed over, and it is the gap a model-based extractor closes.
    """

    def extract(self, documents: Sequence[Quarantined]) -> list[Extraction]:
        out: list[Extraction] = []
        for doc in documents:
            classified = self._classify(doc)
            if classified is not None:
                out.append(classified)
        return out

    def _classify(self, doc: Quarantined) -> Extraction | None:
        text = doc.text
        spans = sentence_spans(text)

        for issue, terms in _ISSUE_TERMS:
            for term in terms:
                match = re.search(re.escape(term), text, re.IGNORECASE)
                if not match:
                    continue
                # Cite the sentence the phrase sits in, not the phrase alone: a
                # reader needs enough context to judge the claim.
                span = next(
                    (s for s in spans if s[0] <= match.start() < s[1]), (0, len(text))
                )
                return Extraction(
                    doc_id=doc.doc_id,
                    issue=issue,
                    span=span,
                    quote=text[span[0]:span[1]],
                    channel=_first_term(text, _SCOPE_TERMS["channel"]),
                    device=_first_term(text, _SCOPE_TERMS["device"]),
                    category=_first_term(text, _SCOPE_TERMS["category"]),
                    flags=doc.flags,
                    # A vocabulary match is a weaker reading than a model's, and
                    # saying so keeps the confidence layer honest.
                    confidence=0.7,
                )

        span = spans[0]
        return Extraction(
            doc_id=doc.doc_id, issue=IssueType.OTHER, span=span,
            quote=text[span[0]:span[1]],
            channel=_first_term(text, _SCOPE_TERMS["channel"]),
            device=_first_term(text, _SCOPE_TERMS["device"]),
            category=_first_term(text, _SCOPE_TERMS["category"]),
            flags=doc.flags, confidence=0.3,
        )


def summarise(extractions: Sequence[Extraction]) -> dict[str, int]:
    """How many documents support each kind of issue."""
    counts: dict[str, int] = {}
    for e in extractions:
        counts[e.issue.value] = counts.get(e.issue.value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
