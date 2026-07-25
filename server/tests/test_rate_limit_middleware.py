"""
Unit tests for src/middleware/rate_limit.py (backend review backlog, 2026-07-25).

Built against a minimal standalone Starlette app rather than the real
src.main app — the real limit is read from RATE_LIMIT_PER_MINUTE at import
time, which would race against pytest's module import order. Testing the
middleware in isolation with an explicit low limit is more direct anyway.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.middleware.rate_limit import RateLimitMiddleware


async def _echo(request):
    return JSONResponse({"ok": True})


def _make_app(limit: int, window_seconds: int = 60):
    app = Starlette(routes=[
        Route("/thing", _echo, methods=["POST"]),
        Route("/thing", _echo, methods=["GET"]),
    ])
    app.add_middleware(RateLimitMiddleware, requests_per_window=limit, window_seconds=window_seconds)
    return TestClient(app)


def test_requests_within_limit_all_succeed():
    client = _make_app(limit=5)
    for _ in range(5):
        assert client.post("/thing").status_code == 200


def test_request_over_limit_gets_429():
    client = _make_app(limit=3)
    for _ in range(3):
        assert client.post("/thing").status_code == 200
    res = client.post("/thing")
    assert res.status_code == 429
    assert "rate limit" in res.json()["detail"].lower()


def test_get_requests_are_never_limited():
    client = _make_app(limit=1)
    client.post("/thing")  # consume the only POST slot
    for _ in range(10):
        assert client.get("/thing").status_code == 200


def test_limit_is_per_path_not_global():
    app = Starlette(routes=[
        Route("/a", _echo, methods=["POST"]),
        Route("/b", _echo, methods=["POST"]),
    ])
    app.add_middleware(RateLimitMiddleware, requests_per_window=1, window_seconds=60)
    client = TestClient(app)

    assert client.post("/a").status_code == 200
    assert client.post("/a").status_code == 429
    assert client.post("/b").status_code == 200  # different path, own bucket
