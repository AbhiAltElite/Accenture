"""Reading candidate causes out of the operational record.

Everything the business wrote down during the window is a candidate: a release
note, a promotion, a supplier email. The engine has no way to tell which of them
mattered, and deliberately does not try at this stage. Sorting real causes from
coincidences is what verification is for, and doing it earlier by intuition is
the failure the whole design exists to avoid.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from whychain.corroborate.extract import RETAIL_VOCABULARY, Vocabulary, _first_term
from whychain.verify.tests import Candidate


def _scope(text: str, vocabulary: Vocabulary = RETAIL_VOCABULARY) -> dict[str, str | None]:
    """Which slice of the business a note is about.

    Shares the extractor's vocabulary rather than keeping a second, smaller copy.
    Scope matters more than it looks: a competitor price cut described as
    affecting "personal care prices" must be tested against personal care alone.
    Measured across a whole region it is swamped by whatever else was happening,
    and a real cause gets rejected for the wrong reason.
    """
    return {
        dimension: _first_term(text, terms)
        for dimension, terms in vocabulary.scope_terms.items()
    }


def _identifier(text: str, doc_id: object) -> str:
    """The reference a reader would quote back, taken from the note itself.

    Notes are written two ways. Some lead with the identifier -- "TA-4411:
    Turnaround at the West refinery..." -- and some bury it in a sentence:
    "Operations circular OC-2026-14: West refinery unit returned to service."
    Splitting on the first token reads the second kind as `Operations`, which
    heads a decision card with a common noun and, worse, collides: every
    circular in the corpus becomes the same candidate.

    So the prefix before the first colon is searched for a token that actually
    looks like a reference, and the last one wins, because that is where the
    identifier sits in "Despatch circular DC-2026-31". Anything without one
    falls back to the old behaviour.
    """
    head, sep, _ = text.partition(":")
    if sep and len(head) <= 60:
        tokens = [t.strip(".,;") for t in head.split()]
        referenced = [t for t in tokens if any(ch.isdigit() for ch in t)]
        if referenced:
            return referenced[-1]
    first = re.split(r"[:\s]", text, maxsplit=1)[0]
    return first or f"doc-{doc_id}"


def _sku(text: str, skus: Iterable[str]) -> str | None:
    """The product a note names, if it names one the warehouse holds.

    Notes write codes the way people type them: "PC-1099", "pc1099", "PC 1099".
    The code is split into its letters and digits and matched with any
    separator between them, bounded so that "PC-10990" is not "PC-1099". Only
    codes present in the data are looked for, so a note cannot invent a scope.
    """
    for sku in sorted(set(skus), key=len, reverse=True):
        parts = re.findall(r"[A-Za-z]+|\d+", str(sku))
        if not parts:
            continue
        pattern = r"(?<![A-Za-z0-9])" + r"[-_ ]?".join(map(re.escape, parts)) + r"(?![A-Za-z0-9]*\d)"
        if re.search(pattern, text, flags=re.IGNORECASE):
            return str(sku)
    return None


# A note that undoes a change is the lever being pulled, not a new cause. Tested
# as one, the recovery it produced verified as a cause of the opposite sign and
# the finding abstained over a contradiction it had manufactured (B-057).
_REMEDIATION = re.compile(
    r"\b(roll(?:ed)?[- ]?back|revert(?:ed)?|hotfix(?:ed)?)\b", re.IGNORECASE
)


def is_remediation(text: str) -> bool:
    """Whether a note records a change being undone."""
    return bool(_REMEDIATION.search(str(text)))


def remediations(
    documents: pd.DataFrame, candidate_id: str, after: date, until: date | None = None
) -> list[dict]:
    """Notes that undo the change a candidate names, dated on or after it.

    Matched on the version the identifier carries ("rel-4.05" and "Release note
    4.05: rollback..."), so a remediation is linked to the release it reverses
    rather than to anything else that mentions a rollback.
    """
    if documents.empty:
        return []
    version = re.search(r"\d+(?:\.\d+)+|\d{2,}", candidate_id)
    if not version:
        return []
    token = re.compile(r"(?<![\d.])" + re.escape(version.group(0)) + r"(?![\d.]\d)")
    ts = pd.to_datetime(documents["ts"])
    rows = documents[
        documents["doc_type"].isin(["release_log", "ops_note"])
        & (ts.dt.date >= after)
        & ((ts.dt.date <= until) if until else True)
    ]
    out = []
    for _, row in rows.iterrows():
        text = str(row["text"])
        if is_remediation(text) and token.search(text):
            out.append({"doc_id": row["doc_id"], "on": pd.Timestamp(row["ts"]).date().isoformat(),
                        "text": text})
    return out


def from_operations(
    documents: pd.DataFrame,
    start: date,
    end: date,
    window_days: int = 10,
    vocabulary: Vocabulary = RETAIL_VOCABULARY,
    skus: Iterable[str] = (),
) -> list[Candidate]:
    """Candidates from release logs and operational notes.

    Remediations are left out: they are what the decision card reports as
    already done, not a hypothesis about why the metric moved.
    """
    if documents.empty:
        return []
    ts = pd.to_datetime(documents["ts"]).dt.date
    in_scope = documents[
        documents["doc_type"].isin(["release_log", "ops_note"])
        & (ts >= start - timedelta(days=window_days))
        & (ts <= end)
    ]

    out: list[Candidate] = []
    skus = tuple(skus)
    for _, row in in_scope.iterrows():
        text = str(row["text"])
        if is_remediation(text):
            continue
        identifier = _identifier(text, row["doc_id"])
        region = row["region"]
        scope = _scope(text, vocabulary)
        out.append(
            Candidate(
                candidate_id=identifier,
                kind=row["doc_type"],
                start=pd.Timestamp(row["ts"]).date(),
                end=end,
                exposed_regions=() if region in ("All", None) else (region,),
                description=text,
                channel=scope["channel"],
                device=scope["device"],
                category=scope["category"],
                sku=_sku(text, skus),
            )
        )
    return out


@dataclass(frozen=True)
class PlanSpec:
    """What the weekly planning extract calls its planned interventions.

    Every industry writes down things it intends to do to some of its regions
    for some weeks, and each one is a candidate that a movement in those weeks
    might be explained by. Retail calls them promotions; a fuel marketer calls
    them refinery turnarounds and price revision cycles; a generator calls them
    outage schedules. The shape is identical -- an id, an active flag, a set of
    exposed regions -- so only the column names and the wording differ, and both
    are facts about the source system rather than about the method.

    Defaults to retail's, so every existing caller is unaffected.
    """

    id_column: str = "promo_id"
    active_column: str = "promo_active"
    kind: str = "promotion"
    noun: str = "Promotion"


RETAIL_PLAN = PlanSpec()


def from_promotions(
    plan_ops: pd.DataFrame, start: date, end: date, spec: PlanSpec = RETAIL_PLAN
) -> list[Candidate]:
    """Candidates from the weekly plan: planned interventions and competitor activity.

    One that ran in several regions arrives here with all of them attached,
    which is what later makes exposure consistency testable.
    """
    if plan_ops.empty or spec.id_column not in plan_ops.columns:
        return []
    week = pd.to_datetime(plan_ops["week"]).dt.date
    active = plan_ops[
        plan_ops[spec.active_column].fillna(False)
        & (week >= start - timedelta(days=14))
        & (week <= end)
    ]
    if active.empty:
        return []

    out: list[Candidate] = []
    for plan_id, group in active.groupby(spec.id_column):
        weeks = pd.to_datetime(group["week"]).dt.date
        categories = group["category"].unique()
        out.append(
            Candidate(
                candidate_id=str(plan_id),
                kind=spec.kind,
                start=max(min(weeks), start - timedelta(days=14)),
                end=end,
                exposed_regions=tuple(sorted(group["region"].unique())),
                description=f"{spec.noun} {plan_id} active in "
                            f"{', '.join(sorted(group['region'].unique()))}",
                category=str(categories[0]) if len(categories) == 1 else None,
            )
        )
    return out
