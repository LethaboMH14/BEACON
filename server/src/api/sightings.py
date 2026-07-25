"""
POST /v1/sightings — accept detection events from vision agents.
Contract from docs/01-ARCHITECTURE.md §5.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..db import get_db, Sighting, Camera, Entity, FaceEmbedding
from ..ws.manager import ws_manager
from ..suspicion import score_entity
from ..suspicion.entity_resolution import resolve_plate_entity
from ..suspicion.plate_text import clean_plate_text
from ..suspicion.face_resolution import (
    MAX_EMBEDDINGS_PER_ENTITY,
    is_valid_embedding,
    normalize,
    resolve_face_entity,
)
import uuid

router = APIRouter()

# Safety cap on the plate-matching candidate pool (see entity_resolution.py's
# length-prefilter docstring for the algorithmic side of this fix). Most
# recently-seen entities first — a plate reappearing after months is rare
# enough that missing it isn't worse than scanning every entity ever created
# on every single sighting.
KNOWN_PLATES_QUERY_LIMIT = 2000

# Same cap, same reasoning, for the face-embedding candidate pool. Counted in
# stored VIEWS not entities (an entity holds up to MAX_EMBEDDINGS_PER_ENTITY),
# so this is ~200+ distinct people — well beyond a demo's population, and the
# comparison itself is one vectorized matmul regardless.
KNOWN_FACES_QUERY_LIMIT = 2000


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
    embedding: Optional[List[float]] = Field(
        None,
        description=(
            "512-d face embedding (InsightFace buffalo_l). Only used when "
            "modality='face'; drives face entity resolution. A descriptor, not "
            "an image — see server/src/suspicion/face_resolution.py."
        ),
    )
    plate_text: Optional[str] = Field(None, description="Normalized plate text")
    plate_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="Plate match quality")
    clip_ref: Optional[str] = Field(None, description="Short clip reference for escalation")

    @field_validator("plate_text")
    @classmethod
    def _sanitize_plate_text(cls, v: Optional[str]) -> Optional[str]:
        """
        Normalize, or drop entirely if the OCR string can't be a plate.

        Applied at the boundary rather than at each call site so the single and
        batch paths cannot disagree. Implausible reads become None — the
        sighting is still recorded (it IS a real detection of a plate-shaped
        object), it just doesn't get to mint an identity. See plate_text.py for
        the observed OCR failures that motivated this.
        """
        return clean_plate_text(v)


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


class SightingDetail(SightingResponse):
    """
    Full sighting record for the ops Live AI Camera view.

    Adds the fields that were written on POST but had no GET route to read them
    back — bbox, plate_text, plate_quality — which is why that screen carried
    three "no backing endpoint yet" placeholders instead of real detections.
    modality is inherited from SightingResponse and was likewise stored but not
    surfaced by the events endpoint the screen was using.
    """
    bbox: Optional[BoundingBox] = None
    plate_text: Optional[str] = None
    plate_quality: Optional[float] = None
    clip_ref: Optional[str] = None
    embedding_ref: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/sightings", response_model=List[SightingDetail])
async def list_sightings(
    camera_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    modality: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Recent sightings with their full detection detail, newest first.

    Exists so the ops Live AI Camera screen can draw real bounding boxes and
    real plate reads instead of placeholders. Filterable by camera (one lens),
    entity (this person/vehicle's history), modality (face/plate/yolo/audio)
    and time.
    """
    limit = max(1, min(limit, 500))

    query = db.query(Sighting)
    if camera_id:
        query = query.filter(Sighting.camera_id == camera_id)
    if entity_id:
        query = query.filter(Sighting.entity_id == entity_id)
    if modality:
        query = query.filter(Sighting.modality == modality)
    if since:
        query = query.filter(Sighting.ts >= since)

    return query.order_by(Sighting.ts.desc()).limit(limit).all()


def _get_or_register_camera(sighting_data: SightingCreate, db: Session) -> Camera:
    """
    Auto-register unknown sensors (camera or mic node) on first sighting —
    there is no separate registration endpoint yet, and rejecting a
    never-seen-before node_id would silently drop every audio/vision agent
    started against a fresh DB.
    """
    camera = db.query(Camera).filter(Camera.id == sighting_data.camera_id).first()
    if not camera:
        camera = Camera(
            id=sighting_data.camera_id,
            name=sighting_data.camera_id,
            hex_id=sighting_data.hex_id,
            status="active",
        )
        db.add(camera)
        db.flush()
    camera.last_seen_at = sighting_data.ts  # G3 camera health
    return camera


def _resolve_plate_entity_row(sighting_data: SightingCreate, db: Session) -> Entity:
    """
    Confusion-aware plate match (docs/01 §3) — an OCR misread like "0" vs "O"
    still resolves to the same car, not a new entity.
    """
    known_plates = dict(
        db.query(Entity.id, Entity.plate_text)
        .filter(Entity.plate_text.isnot(None))
        .order_by(Entity.last_seen.desc())
        .limit(KNOWN_PLATES_QUERY_LIMIT)
        .all()
    )
    matched_id, _quality = resolve_plate_entity(sighting_data.plate_text, known_plates)
    entity = db.query(Entity).filter(Entity.id == matched_id).first() if matched_id else None

    if not entity:
        entity = Entity(
            id=f"ent_{uuid.uuid4().hex[:16]}",
            kind=sighting_data.kind,
            plate_text=sighting_data.plate_text,
            embedding_ref=sighting_data.embedding_ref,
            first_seen=sighting_data.ts,
            last_seen=sighting_data.ts,
            sighting_count=1,
        )
        db.add(entity)
        db.flush()
    else:
        entity.last_seen = sighting_data.ts
        entity.sighting_count += 1
        entity.last_updated = datetime.utcnow()

    return entity


def _resolve_face_entity_row(sighting_data: SightingCreate, db: Session) -> tuple[Entity, bool]:
    """
    Cosine-similarity face match against previously stored embeddings.
    Returns (entity, should_store_this_view).

    Until this existed, a face sighting stored entity_id=NULL — no entity, no
    suspicion score, no "seen here before". Plates were tracked and people
    weren't, which is exactly backwards from what the product claims to do.

    A view is stored when the entity is new, or when it still has room under
    MAX_EMBEDDINGS_PER_ENTITY. Not every view: a person loitering in frame for
    a minute would otherwise write hundreds of near-identical vectors and
    crowd every other face out of the candidate pool.
    """
    rows = (
        db.query(FaceEmbedding.entity_id, FaceEmbedding.vector)
        .order_by(FaceEmbedding.created_at.desc())
        .limit(KNOWN_FACES_QUERY_LIMIT)
        .all()
    )
    known: dict[str, list[list[float]]] = {}
    for entity_id, vector in rows:
        known.setdefault(entity_id, []).append(vector)

    matched_id, _similarity = resolve_face_entity(sighting_data.embedding, known)
    entity = db.query(Entity).filter(Entity.id == matched_id).first() if matched_id else None

    if not entity:
        entity = Entity(
            id=f"ent_{uuid.uuid4().hex[:16]}",
            kind=sighting_data.kind,
            embedding_ref=sighting_data.embedding_ref,
            first_seen=sighting_data.ts,
            last_seen=sighting_data.ts,
            sighting_count=1,
        )
        db.add(entity)
        db.flush()
        return entity, True

    entity.last_seen = sighting_data.ts
    entity.sighting_count += 1
    entity.last_updated = datetime.utcnow()

    stored_views = (
        db.query(FaceEmbedding).filter(FaceEmbedding.entity_id == entity.id).count()
    )
    return entity, stored_views < MAX_EMBEDDINGS_PER_ENTITY


def _resolve_entity(sighting_data: SightingCreate, db: Session) -> tuple[Optional[str], bool]:
    """
    Route a sighting to an entity by whichever modality carries identity.
    Returns (entity_id, should_store_face_view).

    Plate first: an OCR'd plate is a far stronger identifier than an
    uncalibrated face similarity, so when a detection somehow carries both, the
    plate decides and the face embedding is not used to override it.
    """
    if sighting_data.plate_text:
        return _resolve_plate_entity_row(sighting_data, db).id, False

    if sighting_data.modality == "face" and is_valid_embedding(sighting_data.embedding):
        entity, should_store = _resolve_face_entity_row(sighting_data, db)
        return entity.id, should_store

    # No identity-bearing signal (e.g. a weapon detection): a real sighting with
    # no entity, stored as such rather than invented one.
    return None, False


def _store_face_view(sighting: Sighting, sighting_data: SightingCreate, db: Session) -> None:
    """Persist the L2-normalized view and point both refs at it."""
    embedding = FaceEmbedding(
        entity_id=sighting.entity_id,
        sighting_id=sighting.id,
        vector=[float(v) for v in normalize(sighting_data.embedding)],
        dim=len(sighting_data.embedding),
        det_score=sighting_data.confidence,
    )
    db.add(embedding)
    db.flush()

    ref = f"face:{embedding.id}"
    sighting.embedding_ref = ref
    entity = db.query(Entity).filter(Entity.id == sighting.entity_id).first()
    if entity is not None and not entity.embedding_ref:
        entity.embedding_ref = ref


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
    camera = _get_or_register_camera(sighting_data, db)

    # Entity resolution — plate (confusion-aware) or face (cosine similarity)
    entity_id, should_store_face = _resolve_entity(sighting_data, db)

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
    db.flush()

    if should_store_face:
        _store_face_view(sighting, sighting_data, db)

    db.commit()
    db.refresh(sighting)

    # Run suspicion scorer for entities with a resolvable identity
    if entity_id:
        result = score_entity(entity_id, db)
        db.commit()

        # Emit entity.candidate if the scorer promoted the state
        if result.new_state == "candidate":
            await ws_manager.broadcast_to_ops({
                "event": "entity.candidate",
                "data": {
                    "entity_id": entity_id,
                    "base_score": result.base_score,
                    "factors": result.factors,
                    "conflict_gate_fired": result.conflict_gate_fired,
                    "ts": datetime.utcnow().isoformat(),
                }
            })

    # Fan-out sighting event (≤300ms budget)
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
        # Identical resolution to the single-sighting path — shared helpers
        # rather than a second copy that drifts (the plate logic was previously
        # duplicated here, so the face path would have been too).
        camera = _get_or_register_camera(sighting_data, db)
        entity_id, should_store_face = _resolve_entity(sighting_data, db)

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
        db.flush()

        if should_store_face:
            _store_face_view(sighting, sighting_data, db)

        created.append(sighting)

    db.commit()

    # Run scorer for all entities that appeared in this batch
    entity_ids_to_score = {s.entity_id for s in created if s.entity_id}
    for eid in entity_ids_to_score:
        result = score_entity(eid, db)
        db.commit()
        if result.new_state == "candidate":
            await ws_manager.broadcast_to_ops({
                "event": "entity.candidate",
                "data": {
                    "entity_id": eid,
                    "base_score": result.base_score,
                    "factors": result.factors,
                    "conflict_gate_fired": result.conflict_gate_fired,
                    "ts": datetime.utcnow().isoformat(),
                }
            })

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
