"""
BEACON server (docs/01 §2.2, §5) — FastAPI + WebSocket hub.
G0: in-memory store, /v1/sightings ingest, /ws/ops fan-out.
G2: wires in brain/ (entity resolution + Sighting Graph F1 + human gate,
docs/01 §3-4, ADR-0002) so plate sightings actually accumulate into entities
and cross the machine-ceiling into watch_candidate — not just relayed.
Swap in Postgres + pgvector + H3 at G3 (CLAUDE.md D4).

Run: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brain.entity_resolution import resolve_plate_entity  # noqa: E402
from brain.fusion import Entity, human_verify, recompute  # noqa: E402
from brain.fusion import STATE_WATCH_CANDIDATE  # noqa: E402

app = FastAPI(title="BEACON server", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---- in-memory store (G0/G2 only — docs/01 §2.2 lists the real schema) ----
SIGHTINGS: list[dict[str, Any]] = []
ENTITIES: dict[str, Entity] = {}
AUDIO_CUES: list[dict[str, Any]] = []
WHITELIST_PLATES: set[str] = set()  # street whitelist (docs/01 §4 F1) — empty at G2, UI to manage it is G3


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


class AudioCue(BaseModel):
    cue_id: str | None = None
    node_id: str
    ts: str
    hex: str
    label: Literal["gunshot", "glass_break", "scream", "raised_voices"]
    confidence: float


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


def _entity_dict(entity: Entity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "plate_text": entity.plate_text,
        "sightings": entity.sightings,
        "state": entity.state,
        "score": round(entity.score, 3),
        "factors": entity.factors,
    }


@app.post("/v1/sightings")
async def post_sighting(sighting: Sighting) -> dict[str, Any]:
    record = sighting.model_dump()
    record["sighting_id"] = record["sighting_id"] or str(uuid.uuid4())
    record["received_at"] = datetime.now(timezone.utc).isoformat()
    SIGHTINGS.append(record)
    await ops_hub.broadcast("sighting.new", record)

    # Sighting Graph (docs/01 §3-4): only plate-bearing sightings resolve to
    # an entity at G2 — face/vehicle-embedding matching needs vision/ Tier 2
    # crops this repo doesn't produce yet.
    if record["plate_text"]:
        known_plates = {eid: e.plate_text for eid, e in ENTITIES.items() if e.plate_text}
        entity_id, _quality = resolve_plate_entity(record["plate_text"], known_plates)
        if entity_id is None:
            entity_id = str(uuid.uuid4())
            ENTITIES[entity_id] = Entity(entity_id=entity_id, plate_text=record["plate_text"])

        entity = ENTITIES[entity_id]
        entity.sightings.append(record)
        was_below_ceiling = entity.state != STATE_WATCH_CANDIDATE
        is_whitelisted = record["plate_text"].upper() in WHITELIST_PLATES
        recompute(entity, is_whitelisted=is_whitelisted, audio_cues=AUDIO_CUES)

        if entity.state == STATE_WATCH_CANDIDATE and was_below_ceiling:
            await ops_hub.broadcast("entity.candidate", _entity_dict(entity))

    return {"ok": True, "sighting_id": record["sighting_id"]}


@app.post("/v1/audio-cues")
async def post_audio_cue(cue: AudioCue) -> dict[str, Any]:
    """docs/01 §4 F6 — independent-channel corroboration. YAMNet (vision/audio_agent.py)
    posts here; never posts raw audio, label + confidence only (privacy-at-source)."""
    record = cue.model_dump()
    record["cue_id"] = record["cue_id"] or str(uuid.uuid4())
    record["received_at"] = datetime.now(timezone.utc).isoformat()
    AUDIO_CUES.append(record)
    await ops_hub.broadcast("audio.cue", record)

    # Re-check every non-decided entity — a cue can corroborate an existing
    # sighting and push it over the ceiling without a new camera detection.
    for entity in ENTITIES.values():
        was_below_ceiling = entity.state != STATE_WATCH_CANDIDATE
        is_whitelisted = bool(entity.plate_text) and entity.plate_text.upper() in WHITELIST_PLATES
        recompute(entity, is_whitelisted=is_whitelisted, audio_cues=AUDIO_CUES)
        if entity.state == STATE_WATCH_CANDIDATE and was_below_ceiling:
            await ops_hub.broadcast("entity.candidate", _entity_dict(entity))

    return {"ok": True, "cue_id": record["cue_id"]}


@app.get("/v1/entities/{entity_id}")
def get_entity(entity_id: str) -> dict[str, Any]:
    entity = ENTITIES.get(entity_id)
    if entity is None:
        return {"entity_id": entity_id, "sightings": [], "state": "unknown"}
    return _entity_dict(entity)


@app.post("/v1/entities/{entity_id}/verify")
async def verify_entity(entity_id: str, action: VerifyAction) -> dict[str, Any]:
    entity = ENTITIES.setdefault(entity_id, Entity(entity_id=entity_id))
    human_verify(entity, action.action, action.operator_id)
    payload = _entity_dict(entity)
    await ops_hub.broadcast("entity.flagged" if action.action == "flag" else "entity.updated", payload)
    return payload


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
