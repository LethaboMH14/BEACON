"""
POST /v1/sightings — accept detection events from vision agents.
Contract from docs/01-ARCHITECTURE.md §5.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db, Sighting, Camera, Entity
from ..ws.manager import ws_manager
import uuid

router = APIRouter()


class BoundingBox(BaseModel):
    """Bounding box coordinates."""
    x: float
    y: float
    w: float
    h: float


class SightingCreate(BaseModel):
    """Sighting creation request."""
    camera_id: str = Field(..., description="Camera identifier")
    ts: datetime = Field(..., description="Timestamp of detection")
    hex_id: Optional[str] = Field(None, description="H3 hex ID (res 8/9)")
    kind: str = Field(..., description="Detection kind: person, vehicle, weapon")
    modality: str = Field(..., description="Detection modality: face, plate, yolo, audio")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence [0,1]")
    bbox: Optional[BoundingBox] = Field(None, description="Bounding box")
    embedding_ref: Optional[str] = Field(None, description="Reference to embedding storage")
    plate_text: Optional[str] = Field(None, description="Normalized plate text")
    plate_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="Plate match quality")
    clip_ref: Optional[str] = Field(None, description="Short clip reference for escalation")


class SightingBatchCreate(BaseModel):
    """Batch sighting creation (vision agents can batch)."""
    sightings: List[SightingCreate]


class SightingResponse(BaseModel):
    """Sighting response."""
    id: int
    camera_id: str
    entity_id: Optional[str]
    ts: datetime
    hex_id: Optional[str]
    kind: str
    modality: str
    confidence: float
    created_at: datetime
    
    class Config:
        from_attributes = True


@router.post("/sightings", response_model=SightingResponse, status_code=status.HTTP_201_CREATED)
async def create_sighting(
    sighting_data: SightingCreate,
    db: Session = Depends(get_db)
):
    """
    Create a single sighting from a camera detection event.
    
    Vision agents POST here when they detect faces, plates, weapons, etc.
    The sighting is stored, linked to an entity (if resolvable), and a 
    WebSocket event is emitted to connected ops clients.
    """
    # Verify camera exists
    camera = db.query(Camera).filter(Camera.id == sighting_data.camera_id).first()
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {sighting_data.camera_id} not found"
        )
    
    # Entity resolution (simplified for G0 — full logic in suspicion/)
    entity_id = None
    if sighting_data.plate_text:
        # Try to find existing entity by plate
        entity = db.query(Entity).filter(
            Entity.plate_text == sighting_data.plate_text
        ).first()
        
        if not entity:
            # Create new entity
            entity = Entity(
                id=f"ent_{uuid.uuid4().hex[:16]}",
                kind=sighting_data.kind,
                plate_text=sighting_data.plate_text,
                embedding_ref=sighting_data.embedding_ref,
                first_seen=sighting_data.ts,
                last_seen=sighting_data.ts,
                sighting_count=1
            )
            db.add(entity)
            db.flush()
        else:
            # Update existing entity
            entity.last_seen = sighting_data.ts
            entity.sighting_count += 1
            entity.last_updated = datetime.utcnow()
        
        entity_id = entity.id
    
    # Create sighting
    sighting = Sighting(
        camera_id=sighting_data.camera_id,
        entity_id=entity_id,
        ts=sighting_data.ts,
        hex_id=sighting_data.hex_id or camera.hex_id,
        kind=sighting_data.kind,
        modality=sighting_data.modality,
        confidence=sighting_data.confidence,
        bbox=sighting_data.bbox.dict() if sighting_data.bbox else None,
        embedding_ref=sighting_data.embedding_ref,
        plate_text=sighting_data.plate_text,
        plate_quality=sighting_data.plate_quality,
        clip_ref=sighting_data.clip_ref,
        created_at=datetime.utcnow()
    )
    
    db.add(sighting)
    db.commit()
    db.refresh(sighting)
    
    # Fan-out WebSocket event (≤300ms budget)
    await ws_manager.broadcast_to_ops({
        "event": "sighting.new",
        "data": {
            "id": sighting.id,
            "camera_id": sighting.camera_id,
            "entity_id": entity_id,
            "kind": sighting.kind,
            "confidence": sighting.confidence,
            "ts": sighting.ts.isoformat(),
            "hex_id": sighting.hex_id
        }
    })
    
    return sighting


@router.post("/sightings/batch", status_code=status.HTTP_201_CREATED)
async def create_sightings_batch(
    batch: SightingBatchCreate,
    db: Session = Depends(get_db)
):
    """
    Create multiple sightings in a single request.
    Vision agents can batch detections for efficiency.
    """
    created = []
    
    for sighting_data in batch.sightings:
        # Verify camera exists
        camera = db.query(Camera).filter(Camera.id == sighting_data.camera_id).first()
        if not camera:
            continue  # Skip invalid camera
        
        # Entity resolution (simplified)
        entity_id = None
        if sighting_data.plate_text:
            entity = db.query(Entity).filter(
                Entity.plate_text == sighting_data.plate_text
            ).first()
            
            if not entity:
                entity = Entity(
                    id=f"ent_{uuid.uuid4().hex[:16]}",
                    kind=sighting_data.kind,
                    plate_text=sighting_data.plate_text,
                    embedding_ref=sighting_data.embedding_ref,
                    first_seen=sighting_data.ts,
                    last_seen=sighting_data.ts,
                    sighting_count=1
                )
                db.add(entity)
            else:
                entity.last_seen = sighting_data.ts
                entity.sighting_count += 1
                entity.last_updated = datetime.utcnow()
            
            db.flush()
            entity_id = entity.id
        
        # Create sighting
        sighting = Sighting(
            camera_id=sighting_data.camera_id,
            entity_id=entity_id,
            ts=sighting_data.ts,
            hex_id=sighting_data.hex_id or camera.hex_id,
            kind=sighting_data.kind,
            modality=sighting_data.modality,
            confidence=sighting_data.confidence,
            bbox=sighting_data.bbox.dict() if sighting_data.bbox else None,
            embedding_ref=sighting_data.embedding_ref,
            plate_text=sighting_data.plate_text,
            plate_quality=sighting_data.plate_quality,
            clip_ref=sighting_data.clip_ref,
            created_at=datetime.utcnow()
        )
        
        db.add(sighting)
        created.append(sighting)
    
    db.commit()
    
    # Emit batch event
    await ws_manager.broadcast_to_ops({
        "event": "sighting.batch",
        "data": {
            "count": len(created),
            "camera_ids": list(set(s.camera_id for s in created))
        }
    })
    
    return {
        "created": len(created),
        "skipped": len(batch.sightings) - len(created)
    }
