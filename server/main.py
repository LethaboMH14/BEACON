"""
BEACON server (docs/01 §2.2, §5) — FastAPI + WebSocket hub.
G0: in-memory store, /v1/sightings ingest, /ws/ops fan-out. Enough for the
vision-agent -> server -> dashboard spine to talk end-to-end (team/LETHABO.md).
Swap in Postgres + pgvector + H3 at G2 (CLAUDE.md D4).

Run: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="BEACON server", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---- in-memory store (G0 only — docs/01 §2.2 lists the real schema) ----
SIGHTINGS: list[dict[str, Any]] = []
ENTITIES: dict[str, dict[str, Any]] = {}


class Sighting(BaseModel):
    sighting_id: str | None = None
    camera_id: str
    ts: str
    hex: str
    kind: Literal["person", "vehicle", "weapon"]
    bbox: list[int] | None = None
    confidence: float
    embedding_ref: str | None = None
    plate_text: str | None = None
    plate_quality: float | None = None
    clip_ref: str | None = None


class VerifyAction(BaseModel):
    action: Literal["flag", "dismiss", "whitelist"]
    operator_id: str
    note: str | None = None


# ---- WS fan-out (docs/01 §5) ----
class OpsHub:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.discard(ws)

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json({"event": event, "payload": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ops_hub = OpsHub()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "beacon-server"}


@app.post("/v1/sightings")
async def post_sighting(sighting: Sighting) -> dict[str, Any]:
    record = sighting.model_dump()
    record["sighting_id"] = record["sighting_id"] or str(uuid.uuid4())
    record["received_at"] = datetime.now(timezone.utc).isoformat()
    SIGHTINGS.append(record)

    # G0: no Sighting Graph yet (brain/ lands at G2, docs/01 §4) — just relay
    # so the dashboard can prove the spine end-to-end. F1-F6 scoring, the
    # human-gate ladder, and conflict gate replace this broadcast at G2.
    await ops_hub.broadcast("sighting.new", record)
    return {"ok": True, "sighting_id": record["sighting_id"]}


@app.get("/v1/entities/{entity_id}")
def get_entity(entity_id: str) -> dict[str, Any]:
    return ENTITIES.get(entity_id, {"entity_id": entity_id, "sightings": [], "state": "unknown"})


@app.post("/v1/entities/{entity_id}/verify")
async def verify_entity(entity_id: str, action: VerifyAction) -> dict[str, Any]:
    entity = ENTITIES.setdefault(entity_id, {"entity_id": entity_id, "sightings": [], "state": "observed"})
    entity["state"] = {"flag": "flagged", "dismiss": "dismissed", "whitelist": "whitelisted"}[action.action]
    await ops_hub.broadcast("entity.flagged" if action.action == "flag" else "entity.updated", entity)
    return entity


@app.get("/v1/hotspots")
def get_hotspots() -> dict[str, Any]:
    # G0 stub — real forecast lands with data/ (docs/02 §5)
    return {"hexes": []}


@app.websocket("/ws/ops")
async def ws_ops(websocket: WebSocket) -> None:
    await ops_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # ops clients are read-mostly at G0
    except WebSocketDisconnect:
        ops_hub.disconnect(websocket)
