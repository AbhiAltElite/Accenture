"""The engine served by several processes at once (B-077).

One process tops out at about five diagnoses a second whatever the load, so
production runs several workers (`WHYCHAIN_WORKERS`). Anything a request writes
must then hold across processes, not only across threads. Each test here runs
the writers as real separate processes, the way uvicorn's workers are.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from whychain.audit import AuditLog
from whychain.feedback.store import Feedback, FeedbackStore, Judgement

posix = pytest.mark.skipif(sys.platform == "win32", reason="the launcher runs one process there")


def _append_many(path: str, worker: int, n: int, start) -> None:
    log = AuditLog(Path(path))
    start.wait()
    for i in range(n):
        log.append("finding_signed", {"id": f"w{worker}"}, {"kpi_id": "net_revenue"}, {"i": i})


@posix
def test_the_audit_chain_holds_with_several_workers_signing_at_once(tmp_path):
    path = tmp_path / "audit.jsonl"
    ctx = mp.get_context("spawn")
    start = ctx.Event()
    workers = [ctx.Process(target=_append_many, args=(str(path), w, 25, start)) for w in range(4)]
    for p in workers:
        p.start()
    start.set()
    for p in workers:
        p.join(60)
        assert p.exitcode == 0
    log = AuditLog(path)
    entries = log.entries()
    assert len(entries) == 100
    assert [e["seq"] for e in entries] == list(range(1, 101)), "two workers wrote the same seq"
    assert log.verify()["intact"]


def _judgement(i: int) -> Feedback:
    return Feedback(feedback_id=f"fb-{i}", run_id="run-1", kpi_id="net_revenue",
                    persona="cfo", judgement=next(iter(Judgement)), submitted_by="finance.director",
                    submitted_at=datetime(2026, 9, 26, tzinfo=UTC))


def test_a_judgement_recorded_by_one_worker_is_seen_by_the_others(tmp_path):
    path = tmp_path / "feedback.jsonl"
    first, second = FeedbackStore(path), FeedbackStore(path)
    assert second.all() == ()  # the second worker has read the empty log
    first.record(_judgement(1))
    assert len(second.all()) == 1
    second.record(_judgement(2))
    assert {f.feedback_id for f in first.all()} == {"fb-1", "fb-2"}
    assert len(second.all()) == 2, "recorded once, counted once"


def test_a_demo_reset_in_one_worker_empties_the_others(tmp_path):
    path = tmp_path / "feedback.jsonl"
    first, second = FeedbackStore(path), FeedbackStore(path)
    first.record(_judgement(1))
    assert len(second.all()) == 1
    path.replace(tmp_path / "archived.jsonl")  # what /api/demo/reset does
    assert second.all() == ()
