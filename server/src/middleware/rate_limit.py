"""
Minimal in-process rate limiter (backend review backlog, 2026-07-25).

There was previously no rate limiting anywhere — POST /v1/sightings and
POST /v1/entities/{id}/verify could be hit as fast as a client wanted. Fine
for a hackathon demo behind a tunnel, but worth closing before this points
at the open internet. This is deliberately NOT a distributed limiter
(no Redis, no shared store) — a single Container Apps instance is the
actual demo/deploy target (ADR-0004), so an in-memory fixed-window counter
per client IP is honest about the deployment shape rather than adding
infra nobody asked for.

Only guards state-changing methods (POST/PUT/PATCH/DELETE) — GETs and the
WebSocket upgrade handshake (a GET, handled outside this middleware once
the connection is accepted) are left alone.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_window: int | None = None, window_seconds: int = 60):
        super().__init__(app)
        self.limit = requests_per_window or int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.method not in _STATE_CHANGING_METHODS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {self.limit} requests per {self.window_seconds}s"},
            )

        hits.append(now)
        return await call_next(request)
