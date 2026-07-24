"""
BEACON — end-to-end latency harness (docs/01 §6, "the referee numbers").

Measures the spine's only hop that matters for the demo: a sighting posted
by a vision agent to the server, arriving on an ops dashboard's WS feed.
Budget: <=2.0s p95 (CLAUDE.md-equivalent budget, docs/01 §6).

This is the SERVER hop only — one machine, loopback. Real camera-agent
inference time and tunnel latency can only be measured on the day with real
hardware (docs/06 demo plan). Use this script as the regression harness that
catches the server itself getting slow, same role as VUKA's scripts/e2e_latency.py.

Run (server must already be running, e.g. `uvicorn main:app` in server/):
    python scripts/latency.py --url http://localhost:8000 --n 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx
import websockets

BUDGET_S = 2.0


async def wait_for_own_sighting(ws, sighting_id: str, timeout_s: float) -> dict:
    """Drain WS frames until OUR sighting.new arrives, matched by sighting_id
    (not just event name) so a concurrent probe or a real camera agent running
    at the same time can't be mistaken for this round's result."""
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
        msg = json.loads(raw)
        if msg.get("event") == "sighting.new" and msg.get("payload", {}).get("sighting_id") == sighting_id:
            return msg


async def one_round_trip(base_url: str, ws_url: str) -> float:
    sighting_id = str(uuid.uuid4())
    async with websockets.connect(f"{ws_url}/ws/ops") as ws:
        async with httpx.AsyncClient() as client:
            t0 = time.perf_counter()
            await client.post(f"{base_url}/v1/sightings", json={
                "sighting_id": sighting_id,
                "camera_id": "latency-probe",
                "ts": "2026-07-24T00:00:00Z",
                "hex": "sim_hex_0",
                "kind": "person",
                "confidence": 0.9,
                "bbox": [0, 0, 10, 10],
            })
            await wait_for_own_sighting(ws, sighting_id, timeout_s=BUDGET_S * 3)
            return time.perf_counter() - t0


def _print_stats(label: str, samples: list[float]) -> bool:
    s = sorted(samples)
    n = len(s)
    p50 = s[n // 2]
    p95 = s[min(n - 1, int(n * 0.95))]
    mean = statistics.mean(s)
    verdict = "PASS" if p95 <= BUDGET_S else "FAIL"
    print(f"\n{label}")
    print(f"  n={n}  mean={mean*1000:.1f}ms  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms  budget={BUDGET_S*1000:.0f}ms")
    print(f"  {verdict}: p95 {'<=' if verdict == 'PASS' else '>'} budget")
    return verdict == "PASS"


async def main(base_url: str, n: int) -> None:
    ws_url = base_url.replace("http", "ws", 1)

    print("sighting POST -> ops WS sighting.new")
    samples: list[float] = []
    for i in range(n):
        latency = await one_round_trip(base_url, ws_url)
        samples.append(latency)
        print(f"  run {i + 1:>2}/{n}: {latency * 1000:.1f} ms")

    ok = _print_stats("sighting -> ops feed", samples)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000", help="server base URL")
    parser.add_argument("--n", type=int, default=20, help="number of round trips")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.n))
