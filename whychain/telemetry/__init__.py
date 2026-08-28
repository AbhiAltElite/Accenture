"""What one diagnosis cost, and which part of it a model did.

The product's central claim is that the arithmetic is deterministic and the
model only reads and writes. A claim like that invites checking, so the run
records itself: every stage times itself and declares its method class, and the
receipt adds them up.

Two things this deliberately does not do.

It does not assert that two model calls happened. It reports how many did. An
assertion of `<= 2` passes silently when a call fails (BUGS.md T-01), and an
assertion of `== 2` written before the narrative stage exists would be a test
of nothing. The receipt states the count it observed, including zero, and names
what produced the narrative in that case.

It does not estimate. Tokens and cost are recorded by the stage that spent them
or they are absent, because a plausible number on a receipt is worse than a
blank line.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from whychain.evidence import MethodClass

# Rupees per thousand tokens, by direction. Declared here rather than inferred
# so a reader can see what the cost line is arithmetic over, and change it
# without touching the stages.
RATE_INR_PER_1K_IN = 0.26
RATE_INR_PER_1K_OUT = 1.30


@dataclass
class StageTrace:
    """One stage's cost. Mutable while it runs, read after."""

    stage: str
    method_class: MethodClass
    seconds: float = 0.0
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    note: str = ""

    @property
    def cost_inr(self) -> float:
        return (
            self.tokens_in / 1000 * RATE_INR_PER_1K_IN
            + self.tokens_out / 1000 * RATE_INR_PER_1K_OUT
        )

    @property
    def is_model(self) -> bool:
        return self.method_class is MethodClass.LLM


@dataclass
class Telemetry:
    """Collects stage traces for one run and renders the receipt."""

    run_id: str
    traces: list[StageTrace] = field(default_factory=list)

    @contextmanager
    def stage(
        self, name: str, method_class: MethodClass = MethodClass.DETERMINISTIC
    ) -> Iterator[StageTrace]:
        """Time a stage. The body may record model usage on the yielded trace."""
        trace = StageTrace(stage=name, method_class=method_class)
        started = time.perf_counter()
        try:
            yield trace
        finally:
            trace.seconds = time.perf_counter() - started
            self.traces.append(trace)

    @property
    def model_calls(self) -> int:
        return sum(t.model_calls for t in self.traces)

    @property
    def total_seconds(self) -> float:
        return sum(t.seconds for t in self.traces)

    @property
    def model_seconds(self) -> float:
        return sum(t.seconds for t in self.traces if t.is_model)

    @property
    def cost_inr(self) -> float:
        return sum(t.cost_inr for t in self.traces)

    def receipt(self) -> dict:
        """The run as a receipt: what ran, how long, what a model did.

        `deterministic_share` is the fraction of wall time spent outside a model
        call. It is the number that backs the architectural claim, so it is
        computed from the traces rather than stated.
        """
        total = self.total_seconds
        model_time = self.model_seconds
        calls = self.model_calls

        if calls == 0:
            narrative_by = (
                "deterministic template; no model call was made in this run"
            )
        else:
            narrative_by = f"{calls} model call(s)"

        return {
            "run_id": self.run_id,
            "stages": [
                {
                    "stage": t.stage,
                    "method_class": t.method_class.value,
                    "ms": round(t.seconds * 1000, 1),
                    "model_calls": t.model_calls,
                    "tokens_in": t.tokens_in or None,
                    "tokens_out": t.tokens_out or None,
                    "cost_inr": round(t.cost_inr, 4) if t.cost_inr else None,
                    "note": t.note or None,
                }
                for t in self.traces
            ],
            "totals": {
                "ms": round(total * 1000, 1),
                "model_ms": round(model_time * 1000, 1),
                "deterministic_ms": round((total - model_time) * 1000, 1),
                # Guard the divide: a run fast enough to time at zero should not
                # report a share of infinity.
                "deterministic_share": round(1 - model_time / total, 4) if total else None,
                "model_calls": calls,
                "tokens_in": sum(t.tokens_in for t in self.traces) or None,
                "tokens_out": sum(t.tokens_out for t in self.traces) or None,
                "cost_inr": round(self.cost_inr, 4),
            },
            "narrative_by": narrative_by,
        }


__all__ = ["RATE_INR_PER_1K_IN", "RATE_INR_PER_1K_OUT", "StageTrace", "Telemetry"]
