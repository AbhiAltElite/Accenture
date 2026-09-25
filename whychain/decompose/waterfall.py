"""The variance bridge: from the fortnight before to this window, cause by cause.

This is the picture a finance reader already uses for a variance: a starting
bar, one signed bar per driver, and an ending bar, so the steps can be read off
and added up. The engine had every number for it and drew none of them; the
reader was handed a list of causes whose figures, measured one at a time, add
up to more than the movement.

Two honest adjustments make the bars add up, and both are named on the result:

- **Overlap.** Each cause is measured against regions it did not touch, one at a
  time, so two causes that hit the same sales both count them. When the causes
  add to more than the movement, each is scaled by the same factor, so the
  bridge sums exactly and every cause keeps its share. The unscaled figure is
  kept beside it, because that is the one the tests produced.
- **The remainder.** Whatever the tested causes do not account for is its own
  bar, labelled as not explained. It is never folded into a cause.

Built from the movement *after* the reader's projection, so a cause withheld by
entitlement is already absent and its share falls into the remainder, which is
then labelled as possibly withheld rather than claimed to be unexplained.

The arithmetic is checked on the way out: start plus every step equals the end
to the paisa, or nothing is returned. A bridge that does not add up is worse
than no bridge.
"""

from __future__ import annotations

TOLERANCE_INR = 0.05


def cause_waterfall(movement: dict | None, labels: dict[str, str]) -> dict | None:
    """The bridge for one diagnosis, or None when there is nothing to bridge."""
    if not isinstance(movement, dict):
        return None
    base, current = movement.get("base_revenue"), movement.get("current_revenue")
    total = movement.get("total_change")
    if base is None or current is None or total is None:
        return None
    per_cause = {k: float(v) for k, v in (movement.get("per_cause") or {}).items() if v}
    withheld = int(movement.get("per_cause_withheld") or 0)

    gross = sum(per_cause.values())
    # Scale only when the causes, in the movement's direction, claim more than
    # happened. A cause pulling the other way is not overlap, so the test is on
    # the signed sum, not on the sum of sizes.
    scale = 1.0
    if total and gross and (gross / total) > 1.0:
        scale = total / gross

    steps = [
        {
            "kind": "cause",
            "id": cid,
            "label": labels.get(cid) or cid,
            "value": round(value * scale, 2),
            "measured": round(value, 2),
        }
        for cid, value in sorted(per_cause.items(), key=lambda kv: -abs(kv[1]))
    ]
    rest = round(total - sum(s["value"] for s in steps), 2)
    if abs(rest) >= 1.0:
        steps.append({
            "kind": "rest",
            "id": None,
            "label": ("Not shown to you, or not explained" if withheld
                      else "Not explained by a tested cause"),
            "value": rest,
            "measured": None,
        })

    end = round(base + sum(s["value"] for s in steps), 2)
    if abs(end - round(current, 2)) > TOLERANCE_INR:
        return None
    return {
        "start": {"label": "Fortnight before", "value": round(base, 2)},
        "steps": steps,
        "end": {"label": "This window", "value": round(current, 2)},
        "unit": "INR per day",
        "scaled_for_overlap": scale < 1.0,
        "overlap": round(1.0 / scale, 3) if scale < 1.0 else 1.0,
        "withheld": withheld,
    }
