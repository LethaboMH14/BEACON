"""
GET /v1/cameras — camera/sensor health (team/SBU.md backlog, 2026-07-25).

Auto-registration (G2) creates a Camera row on first sighting, but nothing
ever exposed whether a node had gone quiet. A camera counts online if it's
been heard from within STALE_AFTER_SECONDS; otherwise offline — a laptop's
webcam or mic agent silently dying mid-demo now has a visible signal.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import Camera

router = APIRouter()

STALE_AFTER_SECONDS = 60


class CameraStatusEntry(BaseModel):
    id: str
    name: str
    hex_id: str | None
    last_seen_at: datetime | None
    online: bool


class CamerasRes(BaseModel):
    cameras: list[CameraStatusEntry]


@router.get("/cameras", response_model=CamerasRes)
async def get_cameras(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=STALE_AFTER_SECONDS)
    cameras = db.query(Camera).all()
    return CamerasRes(cameras=[
        CameraStatusEntry(
            id=c.id, name=c.name, hex_id=c.hex_id, last_seen_at=c.last_seen_at,
            online=bool(c.last_seen_at and c.last_seen_at >= cutoff),
        )
        for c in cameras
    ])
