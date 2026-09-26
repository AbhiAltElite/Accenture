"""What wraps every request: identity, entitlement, tracing, metrics, headers.

Pure ASGI rather than FastAPI's decorator, because enforcing entitlement means
rewriting the query string before the endpoint parses it, and only the raw
scope can do that. Endpoints stay in `api/main.py`; nothing here answers a
request on its own except the 401 below.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qsl, urlencode

from whychain import identity

log = logging.getLogger("whychain.access")

# Scripts and styles are inline in both console pages, so 'unsafe-inline' is
# required for them; everything else is locked to this origin. The fonts are
# served from here too since 25 Sep, so no font host is allowed any more. Framing is refused to every other origin; this one
# may frame itself, which the /uat page needs to load each scenario and read
# what it rendered. The interactive API docs load assets from a CDN and are exempt.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; "
       "font-src 'self' data:; img-src 'self' data:; "
       "connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
       "form-action 'self'")
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]
DOCS = ("/api/docs", "/openapi.json", "/docs/oauth2-redirect")
OPEN = ("/api/health", "/api/metrics")


class Metrics:
    """Request counts and latency by route and status, for /api/metrics.

    Each worker counts its own requests. With one worker that is the whole
    picture; with several, a scrape reached whichever worker answered and saw
    only its share, a different share each time (B-082). So when more than one
    worker runs, each writes a snapshot to a shared folder at most every two
    seconds, and rendering sums the snapshots of workers that are still alive.
    A worker that has exited drops out, which a scraper reads as a counter reset,
    as it would for a restarted process.
    """

    BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
    WRITE_EVERY = 2.0

    def __init__(self, directory: Path | None = None, pid: int | None = None,
                 alive=None) -> None:
        self._lock = Lock()
        self.count: dict[tuple[str, str, int], int] = defaultdict(int)
        self.seconds: dict[tuple[str, str], float] = defaultdict(float)
        self.buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self.started = time.time()
        self.pid = pid or os.getpid()
        self.directory = directory
        self._alive = alive or _process_alive
        self._written = 0.0
        self._dirty = False
        self._flusher: threading.Thread | None = None
        if directory is not None:
            # Present from the start, so a worker that has served nothing yet
            # still counts as a worker.
            self._write()

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.count[(method, route, status)] += 1
            self.seconds[(method, route)] += seconds
            for b in self.BUCKETS:
                if seconds <= b:
                    self.buckets[(method, route, b)] += 1
            self._dirty = True
        # Written by a background flush, not here: a burst's last requests
        # would otherwise sit unsaved until the next request reached this
        # worker, and a scrape answered by the other one missed them.
        if self.directory is not None and self._flusher is None:
            self._flusher = threading.Thread(target=self._flush_forever, daemon=True)
            self._flusher.start()

    def _flush_forever(self) -> None:
        while True:
            time.sleep(self.WRITE_EVERY / 2)
            if self._dirty:
                self._write()

    def _snapshot(self) -> dict:
        with self._lock:
            return {
                "pid": self.pid, "started": self.started,
                "count": [[m, r, s, n] for (m, r, s), n in self.count.items()],
                "seconds": [[m, r, v] for (m, r), v in self.seconds.items()],
                "buckets": [[m, r, b, n] for (m, r, b), n in self.buckets.items()],
            }

    def _write(self) -> None:
        self._written = time.time()
        self._dirty = False
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            final = self.directory / f"{self.pid}.json"
            part = final.with_suffix(".part")
            part.write_text(json.dumps(self._snapshot()), encoding="utf-8")
            os.replace(part, final)  # a reader sees the old snapshot or the new one
        except OSError:
            pass  # monitoring must never fail a request

    def _all(self) -> list[dict]:
        """This worker's counts, now, and every other live worker's last snapshot."""
        mine = self._snapshot()
        if self.directory is None:
            return [mine]
        self._write()
        out = [mine]
        for path in sorted(self.directory.glob("*.json")):
            try:
                pid = int(path.stem)
            except ValueError:
                continue
            if pid == self.pid:
                continue
            if not self._alive(pid):
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue  # half-written or removed between listing and reading
        return out

    def render(self) -> str:
        """Prometheus text exposition, summed across workers, so any scraper can read it."""
        count: dict[tuple, int] = defaultdict(int)
        seconds: dict[tuple, float] = defaultdict(float)
        buckets: dict[tuple, int] = defaultdict(int)
        snaps = self._all()
        for snap in snaps:
            for m, r, s, n in snap["count"]:
                count[(m, r, int(s))] += n
            for m, r, v in snap["seconds"]:
                seconds[(m, r)] += v
            for m, r, b, n in snap["buckets"]:
                buckets[(m, r, float(b))] += n
        lines = ["# TYPE whychain_requests_total counter"]
        for (m, r, s), n in sorted(count.items()):
            lines.append(f'whychain_requests_total{{method="{m}",route="{r}",status="{s}"}} {n}')
        lines.append("# TYPE whychain_request_seconds_sum counter")
        for (m, r), v in sorted(seconds.items()):
            lines.append(f'whychain_request_seconds_sum{{method="{m}",route="{r}"}} {v:.4f}')
        lines.append("# TYPE whychain_request_seconds_bucket counter")
        for (m, r, b), n in sorted(buckets.items()):
            lines.append(f'whychain_request_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {n}')
        lines.append("# TYPE whychain_workers gauge")
        lines.append(f"whychain_workers {len(snaps)}")
        lines.append(f"whychain_uptime_seconds {time.time() - min(s['started'] for s in snaps):.0f}")
        return "\n".join(lines) + "\n"


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def _metrics_directory() -> Path | None:
    """Shared only when several workers serve, which is when it matters."""
    try:
        workers = int(os.environ.get("WHYCHAIN_WORKERS", "1") or 1)
    except ValueError:
        workers = 1
    if workers <= 1:
        return None
    return Path(os.environ.get("WHYCHAIN_METRICS_DIR", "data/app/metrics"))


METRICS = Metrics(_metrics_directory())


def _route(path: str) -> str:
    """Collapse ids out of paths so metrics do not grow one series per document."""
    for prefix in ("/api/document/", "/kpi/", "/static/"):
        if path.startswith(prefix):
            return prefix + "{id}"
    return path


class EnterpriseMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        request_id = headers.get("x-request-id") or uuid.uuid4().hex[:16]
        client = (scope.get("client") or (None,))[0]
        who = identity.resolve(headers, client)
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                extra = [(b"x-request-id", request_id.encode()), *SECURITY_HEADERS]
                if not path.startswith(DOCS):
                    extra.append((b"content-security-policy", CSP.encode()))
                # Shared styles, fonts and the mark: checked with the server on
                # every load (a 304 when unchanged). Cached without asking, an
                # updated stylesheet was not picked up and a page rendered half
                # in yesterday's design.
                if path.startswith("/static/"):
                    extra.append((b"cache-control", b"no-cache"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        # Under single sign-on a request with no identity never reaches an
        # endpoint. The health check and metrics stay open for the platform.
        if who is None and not path.startswith(OPEN):
            detail = (identity.proxy_untrusted(headers, client)
                      or "sign in through the company's single sign-on")
            body = json.dumps({"detail": detail}).encode()
            await send_wrapped({"type": "http.response.start", "status": 401,
                                "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            self._log(scope, path, 401, started, request_id, who)
            return

        if who is not None:
            scope.setdefault("state", {})["identity"] = who
            # Entitlement from identity, before the endpoint reads the query.
            pairs = parse_qsl(scope.get("query_string", b"").decode("latin-1"),
                              keep_blank_values=True)
            requested = next((v for k, v in pairs if k == "entitled"), None)
            effective = identity.effective_entitlement(who, requested)
            if effective != requested:
                pairs = [(k, v) for k, v in pairs if k != "entitled"] + [("entitled", effective)]
                scope["query_string"] = urlencode(pairs).encode("latin-1")

        try:
            await self.app(scope, receive, send_wrapped)
        finally:
            self._log(scope, path, status_holder["status"], started, request_id, who)

    @staticmethod
    def _log(scope, path, status, started, request_id, who) -> None:
        seconds = time.perf_counter() - started
        METRICS.observe(scope.get("method", ""), _route(path), status, seconds)
        log.info(json.dumps({
            "request_id": request_id, "method": scope.get("method"), "path": path,
            "status": status, "ms": round(seconds * 1000, 1),
            "user": who.id if who else None, "identity": who.source if who else None,
        }))
