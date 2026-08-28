"""Looking for independent support in the company's own words.

Statistics can establish that a movement happened in a particular slice at a
particular time. They cannot tell you that customers were unable to pay. For
that the engine reads what people wrote at the time: tickets, rep notes, the
release log.

Corroboration never promotes a candidate on its own. A verified cause with
supporting tickets is better evidenced than one without, and that difference
belongs in the confidence score rather than in the verdict. Text agreeing with a
number is not proof that the number was caused by what the text describes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

import pandas as pd

from whychain.corroborate.documents import Document
from whychain.corroborate.extract import Extraction, IssueType, RuleExtractor, summarise
from whychain.corroborate.quarantine import quarantine
from whychain.corroborate.retriever import NumpyRetriever
from whychain.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceStore,
    MethodClass,
    Provenance,
    Unit,
)

if TYPE_CHECKING:
    from whychain.corroborate.extract import Extractor
    from whychain.corroborate.retriever import Retriever
    from whychain.verify.tests import Candidate

# Which complaints would corroborate which cause. A checkout regression should
# produce checkout complaints; if it produced only delivery complaints, the
# tickets are describing something else entirely.
RELATED_ISSUES: dict[IssueType, tuple[IssueType, ...]] = {
    IssueType.CHECKOUT_FAILURE: (IssueType.CHECKOUT_FAILURE, IssueType.PAYMENT_FAILURE),
    IssueType.PAYMENT_FAILURE: (IssueType.PAYMENT_FAILURE, IssueType.CHECKOUT_FAILURE),
    IssueType.DELIVERY_DELAY: (IssueType.DELIVERY_DELAY, IssueType.STOCKOUT),
    IssueType.STOCKOUT: (IssueType.STOCKOUT, IssueType.DELIVERY_DELAY),
    IssueType.PRICING: (IssueType.PRICING,),
    IssueType.QUALITY: (IssueType.QUALITY,),
    IssueType.OTHER: (),
}

# Terms that describe a cause but never appear in a customer complaint. A
# customer writes about a broken payment page, not about a release identifier.
_NOT_IN_COMPLAINTS = (
    "release", "deployment", "rollout", "competitor", "supplier", "carrier",
    "distribution centre", "sop", "process", "planning",
)


@dataclass(frozen=True)
class Corroboration:
    """What the record says about one candidate."""

    candidate_id: str
    supporting: tuple[Extraction, ...]
    unrelated: tuple[Extraction, ...]
    flagged: tuple[Extraction, ...]      # documents containing instruction-like text
    searched: int

    @property
    def support_count(self) -> int:
        return len(self.supporting)

    @property
    def summary(self) -> dict[str, int]:
        return summarise([*self.supporting, *self.unrelated])


def _complaint_query(description: str) -> str:
    """Turn a note about a cause into words a customer might have used.

    Two things are dropped. The leading identifier, because an event id appears
    in no ticket and dominates a short query. And internal vocabulary: nobody
    writes in to complain about a deployment, so leaving those words in pulls
    retrieval away from the complaints that would corroborate the cause.
    """
    body = description.split(":", 1)[-1] if ":" in description[:40] else description
    words = [
        w.strip(".,;")
        for w in body.lower().split()
        if len(w) > 3
        and not any(term in w for term in _NOT_IN_COMPLAINTS)
        and not re.search(r"[\d_]|-\w+-", w)   # identifiers, not language
    ]
    return " ".join(words) or body


def corroborate(
    candidate: Candidate,
    documents: pd.DataFrame,
    *,
    retriever: Retriever | None = None,
    extractor: Extractor | None = None,
    k: int = 12,
) -> Corroboration:
    """Search the window for text that supports this candidate.

    Only tickets are searched. Release logs and ops notes are where candidates
    came from in the first place, and letting a candidate corroborate itself
    would turn one record into two pieces of evidence.
    """
    retriever = retriever or NumpyRetriever()
    extractor = extractor or RuleExtractor()

    tickets = documents[documents["doc_type"] == "support_ticket"]
    if tickets.empty:
        return Corroboration(candidate.candidate_id, (), (), (), 0)

    # What the note describing this candidate is actually about. Searching on the
    # candidate's kind alone retrieves whatever complaint type is most common in
    # the window, which is how a weather event ends up corroborated by pricing
    # complaints. Searching on what the note says retrieves what it describes.
    described = extractor.extract([quarantine(candidate.candidate_id, candidate.description)])
    subject = described[0].issue if described else IssueType.OTHER
    expected = RELATED_ISSUES.get(subject, ())

    corpus = [
        Document(
            doc_id=str(row["doc_id"]), source_id="voice_ops",
            text=str(row["text"]),
            ts=pd.Timestamp(row["ts"]).to_pydatetime().replace(tzinfo=UTC),
            metadata={"region": str(row["region"])},
        )
        for _, row in tickets.iterrows()
    ]
    retriever.index(corpus)

    window = (
        datetime.combine(candidate.start, time.min, tzinfo=UTC),
        datetime.combine(candidate.end, time.max, tzinfo=UTC),
    )
    query = _complaint_query(candidate.description)
    matches = retriever.search(query, k=k, window=window, min_score=0.15)

    by_id = {d.doc_id: d for d in corpus}
    quarantined = [quarantine(m.doc_id, by_id[m.doc_id].text) for m in matches]
    extractions = extractor.extract(quarantined)

    supporting = tuple(e for e in extractions if e.issue in expected)
    unrelated = tuple(e for e in extractions if e.issue not in expected)
    flagged = tuple(e for e in extractions if e.flags)

    return Corroboration(
        candidate_id=candidate.candidate_id,
        supporting=supporting,
        unrelated=unrelated,
        flagged=flagged,
        searched=len(matches),
    )


def record_corroboration(
    corroboration: Corroboration, store: EvidenceStore, top_n: int = 4
) -> list[Evidence]:
    """Write supporting passages as evidence, each citing its own span."""
    out: list[Evidence] = []
    for extraction in corroboration.supporting[:top_n]:
        out.append(
            store.add(
                Evidence(
                    id=store.next_id(),
                    kind=EvidenceKind.CORROBORATION,
                    claim=(
                        f"A customer reported {extraction.issue.value.replace('_', ' ')}"
                        + (f" on {extraction.channel}" if extraction.channel else "")
                        + " during the window."
                    ),
                    value=None,
                    unit=Unit.NONE,
                    method="retrieval",
                    method_class=MethodClass.RETRIEVAL,
                    confidence=extraction.confidence,
                    provenance=Provenance(
                        source_id="voice_ops",
                        doc_id=extraction.doc_id,
                        span=extraction.span,
                        quote=extraction.quote,
                    ),
                    run_id=store.run_id,
                    extra={
                        "issue": extraction.issue.value,
                        "candidate_id": corroboration.candidate_id,
                        # Carried through so a reader can see the source contained
                        # instruction-like text, even though it was treated as data.
                        "injection_flags": list(extraction.flags),
                    },
                )
            )
        )
    return out
