"""
GET /v1/incidents/{id}/report — team/SBU.md backlog (2026-07-25).

docs/01 honesty ledger claims BEACON's evidence trail is "structured to
support a case", but the only thing exposed was a yes/no chain-intact
check (GET /v1/evidence/integrity). This bundles the actual case file:
the incident, its linked entity, that entity's sighting timeline, and
every evidence_chain event naming this incident or its entity — so the
claim is a real deliverable, not just a true-but-unproven statement.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import get_db
from ..db.models import Incident, Entity, Sighting, EvidenceChain, Alert

router = APIRouter()


class SightingEntry(BaseModel):
    id: int
    camera_id: str
    ts: datetime
    hex_id: Optional[str]
    kind: str
    confidence: float


class EvidenceEntry(BaseModel):
    id: int
    action: str
    actor_id: str
    ts: datetime
    details: Optional[dict]


class AlertEntry(BaseModel):
    id: str
    alert_type: str
    severity: str
    status: str
    created_at: datetime


class IncidentReportRes(BaseModel):
    incident_id: str
    incident_type: str
    hex_id: str
    occurred_at: datetime
    severity: str
    status: str
    description: Optional[str]
    entity_id: Optional[str]
    entity_kind: Optional[str]
    entity_plate_text: Optional[str]
    sightings: list[SightingEntry]
    alerts: list[AlertEntry]
    evidence_trail: list[EvidenceEntry]


@router.get("/incidents/{incident_id}/report", response_model=IncidentReportRes)
async def get_incident_report(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {incident_id} not found")

    entity: Optional[Entity] = None
    sightings: list[Sighting] = []
    if incident.related_entity_id:
        entity = db.query(Entity).filter(Entity.id == incident.related_entity_id).first()
        sightings = (
            db.query(Sighting)
            .filter(Sighting.entity_id == incident.related_entity_id)
            .order_by(Sighting.ts.asc())
            .all()
        )

    alerts = db.query(Alert).filter(Alert.incident_id == incident_id).order_by(Alert.created_at.asc()).all()

    conditions = [EvidenceChain.target_id == incident_id]
    if incident.related_entity_id:
        conditions.append(EvidenceChain.target_id == incident.related_entity_id)
    evidence = (
        db.query(EvidenceChain)
        .filter(or_(*conditions))
        .order_by(EvidenceChain.id.asc())
        .all()
    )

    return IncidentReportRes(
        incident_id=incident.id,
        incident_type=incident.incident_type,
        hex_id=incident.hex_id,
        occurred_at=incident.occurred_at,
        severity=incident.severity,
        status=incident.status,
        description=incident.description,
        entity_id=entity.id if entity else None,
        entity_kind=entity.kind if entity else None,
        entity_plate_text=entity.plate_text if entity else None,
        sightings=[
            SightingEntry(id=s.id, camera_id=s.camera_id, ts=s.ts, hex_id=s.hex_id, kind=s.kind, confidence=s.confidence)
            for s in sightings
        ],
        alerts=[
            AlertEntry(id=a.id, alert_type=a.alert_type, severity=a.severity, status=a.status, created_at=a.created_at)
            for a in alerts
        ],
        evidence_trail=[
            EvidenceEntry(id=e.id, action=e.action, actor_id=e.actor_id, ts=e.ts, details=e.details)
            for e in evidence
        ],
    )
