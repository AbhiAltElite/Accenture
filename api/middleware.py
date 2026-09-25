"""What wraps every request: identity, entitlement, tracing, metrics, headers.

Pure ASGI rather than FastAPI's decorator, because enforcing entitlement means
rewriting the query string before the endpoint parses it, and only the raw
scope can do that. Endpoints stay in `api/main.py`; nothing here answers a
request on its own except the 401 below.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
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
    """Request counts and latency by route and status, for /api/metrics."""

    BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

    def __init__(self) -> None:
        self._lock = Lock()
        self.count: dict[tuple[str, str, int], int] = defaultdict(int)
        self.seconds: dict[tuple[str, str], float] = defaultdict(float)
        self.buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self.started = time.time()

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.count[(method, route, status)] += 1
            self.seconds[(method, route)] += seconds
            for b in self.BUCKETS:
                if seconds <= b:
                    self.buckets[(method, route, b)] += 1

    def render(self) -> str:
        """Prometheus text exposition, so any scraper can read it."""
        lines = ["# TYPE whychain_requests_total counter"]
        with self._lock:
            for (m, r, s), n in sorted(self.count.items()):
                lines.append(f'whychain_requests_total{{method="{m}",route="{r}",status="{s}"}} {n}')
            lines.append("# TYPE whychain_request_seconds_sum counter")
            for (m, r), s in sorted(self.seconds.items()):
                lines.append(f'whychain_request_seconds_sum{{method="{m}",route="{r}"}} {s:.4f}')
            lines.append("# TYPE whychain_request_seconds_bucket counter")
            for (m, r, b), n in sorted(self.buckets.items()):
                lines.append(f'whychain_request_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {n}')
        lines.append(f"whychain_uptime_seconds {time.time() - self.started:.0f}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()


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
        who = identity.resolve(headers)
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
            body = json.dumps({"detail": "sign in through the company's single sign-on"}).encode()
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
