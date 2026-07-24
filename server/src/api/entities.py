"""
GET /v1/entities/{id} — entity details with lazy suspicion-score decay.
POST /v1/entities/{id}/verify — human verification gate.
Contract from docs/01-ARCHITECTURE.md §5, ADR-0002.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db, Entity, Sighting, Whitelist, Watchlist, EvidenceChain
from ..db.models import Incident, Alert
from ..db.evidence_integrity import verify_chain
from ..ws.manager import ws_manager
from ..suspicion import score_entity
from ..auth import require_operator_token
import hashlib
import json
import uuid

router = APIRouter()


def compute_current_score(base_score: float, last_updated: datetime) -> float:
    """
    Lazy suspicion-score decay at read-time.
    score_now = base_score * 0.5^(days_elapsed/7)
    
    No cron job needed — computed on demand (Sbu's feasibility note).
    """
    days_elapsed = (datetime.utcnow() - last_updated).total_seconds() / 86400.0
    decay_factor = 0.5 ** (days_elapsed / 7.0)
    return base_score * decay_factor


class SightingBrief(BaseModel):
    """Brief sighting for timeline."""
    id: int
    camera_id: str
    ts: datetime
    hex_id: Optional[str]
    kind: str
    confidence: float


class EntityFactors(BaseModel):
    """Suspicion factors (explainable)."""
    recurrence: Optional[float] = None
    time_anomaly: Optional[float] = None
    crime_correlation: Optional[float] = None
    casing_behaviour: Optional[float] = None
    territory_roaming: Optional[float] = None
    modal_corroboration: Optional[float] = None


class EntityResponse(BaseModel):
    """Entity details with current (decayed) score."""
    id: str
    kind: str
    plate_text: Optional[str]
    state: str  # observed, candidate, flagged
    
    base_score: float
    current_score: float  # Decayed
    last_updated: datetime
    
    first_seen: datetime
    last_seen: datetime
    sighting_count: int
    
    factors: EntityFactors
    recent_sightings: List[SightingBrief]


class VerifyAction(BaseModel):
    """Human verification action."""
    action: str = Field(..., description="flag, dismiss, or whitelist")
    operator_id: str = Field(..., description="Operator performing verification")
    note: Optional[str] = Field(None, description="Human note")
    hex_id: Optional[str] = Field(None, description="Hex for whitelist action")


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: str,
    db: Session = Depends(get_db)
):
    """
    Get entity details with current (lazily decayed) suspicion score.
    
    Suspicion decay: score_now = base_score * 0.5^(days_elapsed/7)
    Half-life of ~7 days, computed at read-time (no cron job).
    """
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found"
        )
    
    # Compute current score with lazy decay
    current_score = compute_current_score(entity.base_score, entity.last_updated)

    # Get recent sightings (last 10)
    recent_sightings = db.query(Sighting).filter(
        Sighting.entity_id == entity_id
    ).order_by(Sighting.ts.desc()).limit(10).all()

    # Re-run scorer to get live factors (read-only — scorer result not committed here)
    from ..suspicion.scorer import score_entity as _score
    try:
        result = _score(entity_id, db)
        db.rollback()   # discard the _persist_score write — GET is read-only
        factors = EntityFactors(
            recurrence=result.factors.get("F1_recurrence"),
            time_anomaly=result.factors.get("F2_time_anomaly"),
            crime_correlation=result.factors.get("F3_crime_corr"),
            casing_behaviour=result.factors.get("F4_casing"),
            territory_roaming=result.factors.get("F5_roaming"),
            modal_corroboration=result.factors.get("F6_modal_corrob"),
        )
    except Exception:
        db.rollback()
        factors = EntityFactors()
    
    return EntityResponse(
        id=entity.id,
        kind=entity.kind,
        plate_text=entity.plate_text,
        state=entity.state,
        base_score=entity.base_score,
        current_score=current_score,
        last_updated=entity.last_updated,
        first_seen=entity.first_seen,
        last_seen=entity.last_seen,
        sighting_count=entity.sighting_count,
        factors=factors,
        recent_sightings=[
            SightingBrief(
                id=s.id,
                camera_id=s.camera_id,
                ts=s.ts,
                hex_id=s.hex_id,
                kind=s.kind,
                confidence=s.confidence
            ) for s in recent_sightings
        ]
    )


@router.post("/entities/{entity_id}/verify")
async def verify_entity(
    entity_id: str,
    verify_data: VerifyAction,
    db: Session = Depends(get_db),
    x_operator_token: Optional[str] = Header(default=None, alias="X-Operator-Token"),
):
    """
    Human verification gate (ADR-0002).

    Actions:
    - flag: promote candidate → flagged (pre-arm cameras, route patrols)
    - dismiss: mark as not suspicious, reset score
    - whitelist: add to street whitelist (kills recurrence false positives)

    Every verification writes to evidence_chain (WHO verified WHAT WHEN).
    operator_id is only trustworthy because require_operator_token rejects
    any caller whose X-Operator-Token doesn't match the claimed operator_id
    (team/SBU.md backlog, 2026-07-25) — without this, anyone could write
    any operator name into the permanent hash-chained evidence record.
    """
    require_operator_token(verify_data.operator_id, x_operator_token)

    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found"
        )
    
    action = verify_data.action.lower()
    
    if action == "flag":
        # Promote to flagged state
        entity.state = "flagged"
        
        # Add to watchlist
        watchlist_entry = Watchlist(
            entity_id=entity_id,
            reason=verify_data.note or "Flagged by operator",
            verified_by=verify_data.operator_id,
            verified_at=datetime.utcnow(),
            active=True
        )
        db.add(watchlist_entry)

        # BLOCKER FIX (Lethabo, team/SBU.md 2026-07-25): flag never created an
        # Incident, but POST /v1/alerts hard-requires an existing incident_id —
        # there was no live route from operator-flags-entity to an alert firing,
        # the exact Act 1 beat the demo depends on. Create the Incident here,
        # from the entity's most recent sighting (hex/lat/lng/ts), then create
        # the Alert directly against it.
        last_sighting = db.query(Sighting).filter(
            Sighting.entity_id == entity_id
        ).order_by(Sighting.ts.desc()).first()
        incident_hex = last_sighting.hex_id if last_sighting else None
        incident_ts = last_sighting.ts if last_sighting else datetime.utcnow()

        incident = Incident(
            id=f"inc_{uuid.uuid4().hex[:16]}",
            incident_type="suspicious",
            hex_id=incident_hex or "unknown",
            occurred_at=incident_ts,
            severity="high",
            description=verify_data.note or f"Entity {entity_id} flagged by operator",
            related_entity_id=entity_id,
        )
        db.add(incident)
        db.flush()  # need incident.id populated before the Alert FK references it

        now = datetime.utcnow()
        alert = Alert(
            id=f"alrt_{uuid.uuid4().hex[:16]}",
            alert_type="entity_flagged",
            recipient_id="ops",
            recipient_type="ops",
            entity_id=entity_id,
            incident_id=incident.id,
            message=f"Entity {entity_id} flagged: {verify_data.note or 'no note'}",
            severity="high",
            status="pending",
            created_at=now,
            cancel_window_expires=now + timedelta(seconds=30),
        )
        db.add(alert)

        # Write to evidence chain
        await _write_evidence(
            db=db,
            action="verify_flag",
            actor_id=verify_data.operator_id,
            target_type="entity",
            target_id=entity_id,
            details={
                "note": verify_data.note,
                "state_transition": "candidate → flagged",
                "incident_id": incident.id,
                "alert_id": alert.id,
            }
        )

        # Emit WebSocket event
        await ws_manager.broadcast_to_ops({
            "event": "entity.flagged",
            "data": {
                "entity_id": entity_id,
                "incident_id": incident.id,
                "alert_id": alert.id,
                "operator_id": verify_data.operator_id,
                "ts": datetime.utcnow().isoformat()
            }
        })

        db.commit()
        return {
            "status": "flagged",
            "entity_id": entity_id,
            "incident_id": incident.id,
            "alert_id": alert.id,
        }
    
    elif action == "dismiss":
        # Reset suspicion
        entity.state = "observed"
        entity.base_score = 0.0
        entity.last_updated = datetime.utcnow()
        
        await _write_evidence(
            db=db,
            action="verify_dismiss",
            actor_id=verify_data.operator_id,
            target_type="entity",
            target_id=entity_id,
            details={"note": verify_data.note}
        )
        
        db.commit()
        return {"status": "dismissed", "entity_id": entity_id}
    
    elif action == "whitelist":
        # Add to whitelist
        if not verify_data.hex_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="hex_id required for whitelist action"
            )
        
        whitelist_entry = Whitelist(
            entity_id=entity_id,
            hex_id=verify_data.hex_id,
            kind="resident",  # Could be parameterized
            label=verify_data.note,
            added_by=verify_data.operator_id,
            added_at=datetime.utcnow()
        )
        db.add(whitelist_entry)
        
        # Reset suspicion
        entity.state = "observed"
        entity.base_score = 0.0
        entity.last_updated = datetime.utcnow()
        
        await _write_evidence(
            db=db,
            action="verify_whitelist",
            actor_id=verify_data.operator_id,
            target_type="entity",
            target_id=entity_id,
            details={"hex_id": verify_data.hex_id, "note": verify_data.note}
        )
        
        db.commit()
        return {"status": "whitelisted", "entity_id": entity_id, "hex_id": verify_data.hex_id}
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action: {action}. Must be flag, dismiss, or whitelist"
        )


async def _write_evidence(
    db: Session,    action: str,
    actor_id: str,
    target_type: str,
    target_id: str,
    details: Optional[Dict] = None
) -> None:
    """
    Write to hash-chained evidence_chain.
    
    Every human verification action is recorded with:
    - WHO (actor_id)
    - WHAT (action, target)
    - WHEN (ts)
    - Hash-chain for integrity (prev_hash → event_hash)
    """
    # Get last event hash for chain
    last_event = db.query(EvidenceChain).order_by(EvidenceChain.id.desc()).first()
    prev_hash = last_event.event_hash if last_event else None

    # BUG FIX (found reviewing this against evidence_integrity.py's verifier):
    # ts must be computed exactly ONCE and reused for both the hash input and
    # the stored column. The previous version called datetime.utcnow() twice —
    # once to build event_data["ts"], again for the stored `ts=` field — so the
    # hash was computed over a timestamp that was never actually persisted.
    # verify_chain() recomputes the hash from the STORED row, so every row
    # written this way failed its own integrity check on the very next read —
    # confirmed by writing one real row and calling verify_chain() on it before
    # this fix (is_intact: False). This is the load-bearing "who verified what
    # when" evidence for the ethics pitch; it must be intact by construction.
    ts = datetime.utcnow()

    # Compute event hash
    event_data = {
        "action": action,
        "actor_id": actor_id,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "ts": ts.isoformat(),
        "prev_hash": prev_hash
    }
    event_hash = hashlib.sha256(json.dumps(event_data, sort_keys=True).encode()).hexdigest()

    # Create evidence entry
    evidence = EvidenceChain(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ts=ts,
        prev_hash=prev_hash,
        event_hash=event_hash
    )

    db.add(evidence)


@router.get("/evidence/integrity")
async def evidence_integrity(db: Session = Depends(get_db)):
    """
    Verify the hash-chain integrity of the evidence_chain table.
    Returns is_intact, total_events, and the first broken link if any.
    Ops-only in production; unrestricted for the demo.
    """
    result = verify_chain(db)
    return {
        "is_intact":     result.is_intact,
        "total_events":  result.total_events,
        "broken_at_id":  result.broken_at_id,
        "broken_at_seq": result.broken_at_seq,
        "detail":        result.detail,
    }
