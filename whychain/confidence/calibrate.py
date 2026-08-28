"""Turning a comparable score into a probability, and refusing to before it can.

The confidence score is a weighted sum of four things a reader can check. It
orders diagnoses correctly, which is what it was designed to do. It is not a
probability, and printing `0.86` invites a reader to treat it as one: to think
that of every hundred diagnoses scoring 0.86, roughly eighty-six were right.

That claim has to be earned against labelled outcomes, and the uncalibrated
score does not earn it. Measured over the benchmark population, scores between
0.8 and 1.0 averaged 0.908 and were right 74% of the time. Sixteen points of
overconfidence, in the direction that matters, on the number a reader uses to
decide whether to act.

Isotonic regression fixes the direction of that error without assuming a shape
for it. It fits a monotone step function from raw score to observed frequency,
so a higher score still means "more likely right" (the ordering the engine
earned is preserved) while the *level* is pulled onto the outcomes actually
observed.

Three rules govern its use here, and each exists because of a specific way
calibration goes wrong.

**It is fitted on a held-out split and never re-fitted after seeing the test
results** (BUGS.md T-13). A calibration fitted on the cases it is then scored
against reports its own training error, which is always excellent.

**The raw score is never overwritten.** `Confidence` carries both, and the
console can show the working. A calibrated number that cannot be traced back
to the arithmetic under it is exactly the opaque figure this project objects to
in other products.

**An unfitted calibrator returns nothing rather than guessing.** With no
calibration on disk, `probability` is `None` and the reader is shown a score
labelled as a score. Reporting an uncalibrated number as a probability because
it is more convenient is the failure this file exists to prevent.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PATH = Path("data/calibration.json")

# Below this many labelled outcomes an isotonic fit is memorising the sample
# rather than learning its shape, and the resulting curve is worse than the raw
# score it replaces.
MIN_OUTCOMES = 40


@dataclass(frozen=True)
class Calibration:
    """A fitted monotone map from raw score to observed frequency of being right."""

    thresholds: tuple[float, ...]
    probabilities: tuple[float, ...]
    fitted_on: int
    fitted_at: str
    split: str
    brier_before: float
    brier_after: float

    @property
    def improved(self) -> bool:
        """Whether calibrating actually helped, measured rather than assumed."""
        return self.brier_after <= self.brier_before

    def probability(self, score: float) -> float:
        """Interpolate the fitted curve. Monotone in, monotone out."""
        if not self.thresholds:
            return score
        if score <= self.thresholds[0]:
            return self.probabilities[0]
        if score >= self.thresholds[-1]:
            return self.probabilities[-1]
        for i in range(1, len(self.thresholds)):
            lo, hi = self.thresholds[i - 1], self.thresholds[i]
            if score <= hi:
                span = hi - lo
                if span <= 0:
                    return self.probabilities[i]
                t = (score - lo) / span
                return (
                    self.probabilities[i - 1]
                    + t * (self.probabilities[i] - self.probabilities[i - 1])
                )
        return self.probabilities[-1]

    def as_dict(self) -> dict:
        return {
            "thresholds": list(self.thresholds),
            "probabilities": list(self.probabilities),
            "fitted_on": self.fitted_on,
            "fitted_at": self.fitted_at,
            "split": self.split,
            "brier_before": round(self.brier_before, 5),
            "brier_after": round(self.brier_after, 5),
            "improved": self.improved,
        }

    def save(self, path: Path = DEFAULT_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> Calibration | None:
        """The fitted curve, or None. Absence is a valid, reported state."""
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                thresholds=tuple(raw["thresholds"]),
                probabilities=tuple(raw["probabilities"]),
                fitted_on=int(raw["fitted_on"]),
                fitted_at=str(raw["fitted_at"]),
                split=str(raw["split"]),
                brier_before=float(raw["brier_before"]),
                brier_after=float(raw["brier_after"]),
            )
        except (KeyError, ValueError, TypeError):
            # A malformed file is not a reason to invent a calibration.
            return None


def _brier(scores: Sequence[float], correct: Sequence[bool]) -> float:
    """Mean squared error of a probabilistic forecast. Lower is better."""
    if not scores:
        return 0.0
    return sum((s - float(c)) ** 2 for s, c in zip(scores, correct, strict=True)) / len(
        scores
    )


def fit(
    scores: Sequence[float],
    correct: Sequence[bool],
    *,
    split: str = "held-out",
) -> Calibration | None:
    """Fit the curve, and refuse when there is not enough to fit it on.

    Returns None rather than a weak calibration: an engine reporting a
    probability derived from thirty cases is making a stronger claim than one
    reporting a score, not a weaker one.
    """
    if len(scores) < MIN_OUTCOMES or len(set(correct)) < 2:
        return None

    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    fitted = model.fit_transform(list(scores), [float(c) for c in correct])

    pairs = sorted(zip(scores, fitted, strict=True))
    thresholds: list[float] = []
    probabilities: list[float] = []
    for x, y in pairs:
        if thresholds and abs(x - thresholds[-1]) < 1e-9:
            probabilities[-1] = y
            continue
        thresholds.append(float(x))
        probabilities.append(float(y))

    calibration = Calibration(
        thresholds=tuple(thresholds),
        probabilities=tuple(probabilities),
        fitted_on=len(scores),
        fitted_at=datetime.now(UTC).isoformat(),
        split=split,
        brier_before=_brier(scores, correct),
        brier_after=_brier([float(y) for y in fitted], correct),
    )
    # A calibration that makes the forecast worse on its own training data is
    # broken, not subtle.
    return calibration if calibration.improved else None


def expected_calibration_error(
    scores: Sequence[float], correct: Sequence[bool], bins: int = 5
) -> float:
    """The gap between claimed confidence and observed frequency, size-weighted."""
    if not scores:
        return 0.0
    total = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        chunk = [
            (s, c)
            for s, c in zip(scores, correct, strict=True)
            if (lo <= s < hi) or (i == bins - 1 and s == 1.0)
        ]
        if not chunk:
            continue
        mean_score = sum(s for s, _ in chunk) / len(chunk)
        accuracy = sum(1 for _, c in chunk if c) / len(chunk)
        total += len(chunk) / len(scores) * abs(mean_score - accuracy)
    return round(total, 4)
