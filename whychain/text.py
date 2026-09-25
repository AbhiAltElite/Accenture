"""Words a reader sees, formed the same way everywhere.

Receipts, notices, reasons and approval requests were assembled in a dozen
modules, each with its own habits: `9 warning(s)`, `net_revenue and
finance_ledger`, `Requires approval from ecommerce_lead`, and a sentence ending
`earlier.. Lever`. None was wrong on its own; together they read as log output on
the one surface that has to be signed by a finance director.

The identifiers themselves stay in the structured fields (`owner`, `driver`,
`source`), where code reads them. Only prose goes through here.
"""

from __future__ import annotations

import re


def plural(n: int, one: str, many: str | None = None) -> str:
    """`1 warning`, `9 warnings`. Never `9 warning(s)`."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def label(identifier: str | None) -> str:
    """`net_revenue` as a reader says it: `net revenue`."""
    return (identifier or "").replace("_", " ").strip()


def role(identifier: str | None) -> str:
    """A role id as a person's title: `ecommerce_lead` -> `the ecommerce lead`."""
    text = label(identifier)
    return f"the {text}" if text else "the metric owner"


def plain(description: str | None) -> str:
    """A cause without its record prefix or trailing full stop.

    Candidates arrive as `rel-4.05: Release 4.05 broke card entry.`; the prefix
    is how the evidence store addresses the row, and the full stop doubled up
    wherever the description was placed mid-sentence.
    """
    text = (description or "").strip()
    head, sep, tail = text.partition(": ")
    if sep and len(head) <= 32 and " " not in head:
        text = tail.strip()
    return text.rstrip(".").strip()


def sentence_case(text: str) -> str:
    """Upper-case the first letter and leave the rest alone.

    `str.capitalize()` lower-cases everything after the first character, which
    turned "Apply pricing for West" into "for west" and "no lever. The response"
    into "the response".
    """
    return text[:1].upper() + text[1:] if text else text


def action_text(action: str | None) -> str:
    """The engine's action as a reader says it.

    "Apply release rollback for channel app, device mobile" is how the card
    addresses the slice, and it reached the written summary unchanged, as did
    "for device tank_truck" in petroleum. One wording, used by the prose, the
    Teams card and the page alike.
    """
    text = re.sub(r"for channel (\w+), device (\w+)", r"for the \1 channel on \2 devices", action or "")
    text = re.sub(r"for device (\w+)", r"for \1", text)
    text = re.sub(r"for channel (\w+)", r"for the \1 channel", text).replace("_", " ")
    return sentence_case(text)
