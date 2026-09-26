"""A tamper-evident record of what people did with a finding.

Corrections already have a store (`whychain.feedback`). This is for the acts
that carry accountability: signing a finding, and accepting, modifying or
rejecting a decision card. Each entry names who acted, where the identity came
from, and a fingerprint of the evidence they acted on.

**Append-only and hash-chained.** Every entry carries the hash of the one before
it, so editing or deleting any past line breaks every hash after it, and
`verify()` says exactly where. This is the property an auditor asks for; it is
not encryption and does not stop someone with file access from rewriting the
whole chain, which is why the enterprise form of this store is an append-only
table in the client's own database, exported to their SIEM.

**The evidence fingerprint** is a hash over the deterministic part of a run:
the movement, the verified causes and their test outcomes, the confidence, the
reconciliation and the signal-gap verdicts. It excludes the run id and anything
the model wrote, so the same data always produces the same fingerprint. Re-run
the diagnosis later and compare: if the fingerprint differs, the data under a
signed finding has changed since it was signed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_PATH = Path("data/audit/audit.jsonl")
GENESIS = "0" * 64

try:  # POSIX: the container and the Mac
    import fcntl
except ImportError:  # Windows, where the launcher runs one process
    fcntl = None

EVENTS = frozenset({"finding_signed", "decision_accepted", "decision_modified",
                    "decision_rejected", "card_dispatched", "ticket_raised",
                    "target_adjusted", "rows_exported"})


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str)


def _digest(obj: object) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def evidence_fingerprint(diagnosis: dict) -> str:
    """A hash of what a run found, independent of when it ran and of the prose.

    Only fields computed deterministically are included. The narrative is left
    out on purpose: the same evidence written up by a different model is the
    same evidence.
    """
    verified = [
        {
            "candidate_id": v.get("candidate_id"),
            "contribution": round(float(v.get("contribution") or 0.0), 2),
            "tests": sorted((t.get("name"), t.get("outcome")) for t in v.get("tests", [])),
        }
        for v in diagnosis.get("verified") or []
    ]
    movement = diagnosis.get("movement") or {}
    confidence = diagnosis.get("confidence") or {}
    basis = {
        "kpi_id": diagnosis.get("kpi_id"),
        "region": diagnosis.get("region"),
        "slice": diagnosis.get("slice"),
        "window": diagnosis.get("window"),
        "verdict": diagnosis.get("verdict"),
        "movement": {k: round(float(movement[k]), 2) for k in
                     ("base_revenue", "current_revenue", "total_change")
                     if isinstance(movement.get(k), (int, float))},
        "verified": sorted(verified, key=lambda v: str(v["candidate_id"])),
        "probability": confidence.get("probability"),
        "reconciliation": (diagnosis.get("reconciliation") or {}).get("state"),
        "signal_gap": (diagnosis.get("signal_gap") or {}).get("verdict"),
    }
    return _digest(basis)


@dataclass
class AuditLog:
    """The chain on disk, appended to by every process serving the engine.

    Each entry links to the one before, so reading the head and writing the next
    entry must happen as one step. A thread lock only covers one process: with
    several workers two of them read the same head and write the same `seq`, and
    the chain reports itself broken (B-077). `locked()` holds both.
    """

    path: Path = DEFAULT_PATH
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        """Exclusive over the chain, across threads and processes."""
        with self._lock:
            if fcntl is None:
                yield
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # A lock file beside the log, not the log itself: a demo reset moves
            # the log away, and a lock on a moved file protects nothing.
            with (self.path.parent / (self.path.name + ".lock")).open("a") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append(self, event: str, actor: dict, subject: dict, payload: dict) -> dict:
        if event not in EVENTS:
            raise ValueError(f"unknown audit event {event!r}")
        with self.locked():
            chain = self.entries()
            entry = {
                "seq": len(chain) + 1,
                "at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "event": event,
                "actor": actor,
                "subject": subject,
                "payload": payload,
                "prev": chain[-1]["hash"] if chain else GENESIS,
            }
            entry["hash"] = _digest(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(_canonical(entry) + "\n")
            return entry

    def verify(self) -> dict:
        """Recompute the chain. Names the first entry that does not hold."""
        prev = GENESIS
        chain = self.entries()
        for entry in chain:
            body = {k: v for k, v in entry.items() if k != "hash"}
            if entry.get("prev") != prev:
                return {"intact": False, "entries": len(chain), "broken_at": entry.get("seq"),
                        "reason": "links to a different previous entry"}
            if _digest(body) != entry.get("hash"):
                return {"intact": False, "entries": len(chain), "broken_at": entry.get("seq"),
                        "reason": "contents do not match their hash"}
            prev = entry["hash"]
        return {"intact": True, "entries": len(chain), "head": prev}

    def for_subject(self, **match: object) -> list[dict]:
        return [e for e in self.entries()
                if all(e.get("subject", {}).get(k) == v for k, v in match.items())]
