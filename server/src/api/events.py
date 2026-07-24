"""
GET /v1/events/since?ts= — team/SBU.md backlog (2026-07-25).

Reconnection is currently client-side only with no replay: if a laptop's
WS drops mid-demo (docs/06's 3-house tunnel topology), the ops feed just
goes silent with no way to recover missed events. Rather than add a new
event-log table (invented infra for a single-shot demo), this reconstructs
the same event shapes ws_manager already broadcasts by re-querying the
tables that back them (sightings, entities, alerts) for rows created/
updated after `ts` — no server-side session state needed.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import Sighting, Entity, Alert

router = APIRouter()


class EventEntry(BaseModel):
    event: str
    ts: datetime
    data: dict


class EventsSinceRes(BaseModel):
    since: datetime
    events: list[EventEntry]


@router.get("/events/since", response_model=EventsSinceRes)
async def get_events_since(
    ts: datetime = Query(..., description="ISO timestamp of the last event this client saw"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    events: list[EventEntry] = []

    for s in db.query(Sighting).filter(Sighting.created_at > ts).order_by(Sighting.created_at.asc()).limit(limit):
        events.append(EventEntry(event="sighting.new", ts=s.created_at, data={
            "id": s.id, "camera_id": s.camera_id, "entity_id": s.entity_id,
            "hex_id": s.hex_id, "kind": s.kind, "confidence": s.confidence,
        }))

    for e in db.query(Entity).filter(Entity.state == "candidate", Entity.last_updated > ts).order_by(Entity.last_updated.asc()).limit(limit):
        events.append(EventEntry(event="entity.candidate", ts=e.last_updated, data={
            "entity_id": e.id, "base_score": e.base_score,
        }))

    for a in db.query(Alert).filter(Alert.created_at > ts).order_by(Alert.created_at.asc()).limit(limit):
        events.append(EventEntry(event="alert.new", ts=a.created_at, data={
            "id": a.id, "alert_type": a.alert_type, "severity": a.severity,
            "entity_id": a.entity_id, "incident_id": a.incident_id,
        }))

    events.sort(key=lambda ev: ev.ts)
    return EventsSinceRes(since=ts, events=events[:limit])
