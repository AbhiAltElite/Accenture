"""Which bone of a cause-and-effect diagram each candidate belongs on.

A fishbone (Ishikawa) diagram is how operations and quality teams already lay out
root-cause analysis: the effect at the head, categories of cause as bones, and
every hypothesis written on its bone. What they usually hold is a brainstorm.
Here every entry on a bone has been tested, so the diagram shows which
hypotheses survived, which were rejected and why, and which bones had nothing in
the record at all, which is itself worth seeing.

The categories are the manufacturing 6M adapted to a commercial metric, and
they are the same for every industry so a reader who has learnt the diagram
once can read it anywhere. Placement is deterministic, from the candidate's own
record: its kind, the slice it was recorded against, and its description. No
model decides where a cause sits, and the rule that placed it is returned so a
reader can disagree with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Bone:
    id: str
    label: str
    words: tuple[str, ...]


# Order matters: the first bone whose words appear wins. Competition is before
# price because "competitor cut prices" is about the competitor; external is
# before supply because "rain closed stores" is about the rain.
BONES: tuple[Bone, ...] = (
    Bone("competition", "Competition", ("competitor", "rival", "market share")),
    Bone("external", "External conditions",
         ("weather", "rain", "flood", "storm", "cyclone", "heat", "monsoon", "strike",
          "bandh", "curfew", "regulation", "regulatory", "tax", "gst", "holiday", "election")),
    Bone("platform", "Platform and process",
         ("release", "app ", "checkout", "payment", "gateway", "bug", "outage of", "system",
          "website", "card entry", "login", "software", "it outage")),
    Bone("price", "Price and product",
         ("price", "pricing", "discount", "tariff", "sku", "launch", "introductory", "mrp",
          "pack size", "assortment", "realisation")),
    Bone("demand", "Demand and marketing",
         ("promotion", "promo", "campaign", "marketing", "media", "advert", "sale ", "festival",
          "footfall")),
    Bone("supply", "Supply and logistics",
         ("stock", "supply", "carrier", "delivery", "fleet", "tanker", "refinery", "turnaround",
          "allocation", "indent", "plant", "outage", "grid", "transmission", "warehouse",
          "depot", "gantry", "shipment", "logistics")),
)
OTHER = Bone("other", "Other", ())

# A candidate's kind decides its bone before any words are read, where the kind
# is unambiguous about it.
_BY_KIND = {"release_log": "platform", "promotion": "demand"}


def _mentions(text: str, word: str) -> bool:
    """A word, or the start of one: "rain" finds "rainfall" and not "training".

    A trailing space in the table asks for the whole word only, so "app" does
    not find "apply" and "sale" does not find "wholesale".
    """
    whole = word.endswith(" ")
    pattern = r"\b" + re.escape(word.strip()) + (r"\b" if whole else "")
    return re.search(pattern, text) is not None


def bone_for(kind: str | None, description: str | None) -> dict[str, str]:
    """The bone a candidate sits on, and the rule that put it there."""
    if kind in _BY_KIND:
        bone = next(b for b in BONES if b.id == _BY_KIND[kind])
        return {"id": bone.id, "label": bone.label, "because": f"recorded as a {kind.replace('_', ' ')}"}
    # The record prefix ("rel-4.05:") is an address, not a description.
    text = " " + re.sub(r"^[^:\s]{1,32}:\s*", "", (description or "")).lower() + " "
    for bone in BONES:
        for word in bone.words:
            if _mentions(text, word):
                return {"id": bone.id, "label": bone.label, "because": f"mentions {word.strip()!r}"}
    return {"id": OTHER.id, "label": OTHER.label, "because": "no category word in the record"}


def bones() -> list[dict[str, str]]:
    """Every bone, in drawing order, so an empty one is drawn and not omitted."""
    return [{"id": b.id, "label": b.label} for b in (*BONES, OTHER)]
