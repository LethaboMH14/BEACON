"""
Alert endpoints.
POST /v1/alerts                  — create alert (with cancel window)
POST /v1/alerts/{id}/ack         — operator acknowledges
POST /v1/alerts/{id}/cancel      — cancel within window

Contract from docs/01-ARCHITECTURE.md §5.
ADR-0002: every alert carries a cancel window; ack/cancel write to evidence_chain.
"""
from datetime import datetime, timedelta
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import Alert, Entity, Incident, EvidenceChain
from ..ws.manager import ws_manager
from ..api.entities import _write_evidence
from ..auth import require_operator_token

router = APIRouter()

# Cancel window: 30 seconds default (tunable via env later)
CANCEL_WINDOW_SECONDS = 30


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    alert_type: str = Field(
        ...,
        description="entity_flagged | hard_trigger | forecast_spike | suspicious_activity"
    )
    recipient_id: str = Field(..., description="Operator or member ID")
    recipient_type: str = Field(..., description="ops | member")
    message: str = Field(..., description="Human-readable alert message")
    severity: str = Field(..., description="low | medium | high | critical")
    entity_id: Optional[str] = Field(None)
    incident_id: Optional[str] = Field(None)
    camera_id: Optional[str] = Field(
        None,
        description="Camera that triggered alert (used for member room filtering)"
    )


class AlertResponse(BaseModel):
    id: str
    alert_type: str
    recipient_id: str
    recipient_type: str
    message: str
    severity: str
    status: str
    entity_id: Optional[str]
    incident_id: Optional[str]
    created_at: datetime
    cancel_window_expires: Optional[datetime]

    class Config:
        from_attributes = True


class AckPayload(BaseModel):
    operator_id: str = Field(..., description="Operator acknowledging the alert")
    note: Optional[str] = None


class CancelPayload(BaseModel):
    operator_id: str = Field(..., description="Operator cancelling the alert")
    reason: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_alert_exists(alert_id: str, db: Session) -> Alert:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert {alert_id} not found"
        )
    return alert


def _assert_not_terminal(alert: Alert) -> None:
    """Raise if the alert is already in a terminal state."""
    if alert.status in ("acked", "cancelled", "expired"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert is already {alert.status}"
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/alerts", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    """
    Create an alert and fan it out over WebSocket.

    A cancel window of 30 s is set on every new alert — operators can
    cancel within that window before the alert reaches the member.
    """
    # Validate FK references (optional fields)
    if payload.entity_id:
        if not db.query(Entity).filter(Entity.id == payload.entity_id).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity {payload.entity_id} not found"
            )
    if payload.incident_id:
        if not db.query(Incident).filter(Incident.id == payload.incident_id).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {payload.incident_id} not found"
            )

    now = datetime.utcnow()
    alert = Alert(
        id=f"alrt_{uuid.uuid4().hex[:16]}",
        alert_type=payload.alert_type,
        recipient_id=payload.recipient_id,
        recipient_type=payload.recipient_type,
        entity_id=payload.entity_id,
        incident_id=payload.incident_id,
        message=payload.message,
        severity=payload.severity,
        status="pending",
        created_at=now,
        cancel_window_expires=now + timedelta(seconds=CANCEL_WINDOW_SECONDS),
    )
    db.add(alert)

    await _write_evidence(
        db=db,
        action="alert_created",
        actor_id="system",
        target_type="alert",
        target_id=alert.id,
        details={
            "alert_type": payload.alert_type,
            "recipient_id": payload.recipient_id,
            "severity": payload.severity,
        },
    )

    db.commit()
    db.refresh(alert)

    # Fan-out to the correct room, with camera_id metadata for member filtering
    ws_event = {
        "event": "alert.new",
        "data": {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "entity_id": alert.entity_id,
            "recipient_id": alert.recipient_id,
            "ts": now.isoformat(),
            "camera_id": payload.camera_id,         # used by member WS filter
            "cancel_window_expires": alert.cancel_window_expires.isoformat(),
        },
    }

    await ws_manager.broadcast_to_ops(ws_event)

    if payload.recipient_type == "member":
        await ws_manager.broadcast_alert_to_member(
            message=ws_event,
            camera_id=payload.camera_id,
        )

    return alert


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(
    alert_id: str,
    payload: AckPayload,
    db: Session = Depends(get_db),
    x_operator_token: Optional[str] = Header(default=None, alias="X-Operator-Token"),
):
    """
    Acknowledge an alert.
    Writes WHO/WHEN to evidence_chain. Emits alert.acked WS event.
    operator_id is authenticated the same way as POST /v1/entities/{id}/verify
    (require_operator_token) — this endpoint writes the same kind of WHO-did-
    WHAT-WHEN evidence and had the identical unauthenticated-free-text gap.
    """
    require_operator_token(payload.operator_id, x_operator_token)

    alert = _assert_alert_exists(alert_id, db)
    _assert_not_terminal(alert)

    alert.status   = "acked"
    alert.acked_at = datetime.utcnow()
    alert.acked_by = payload.operator_id

    await _write_evidence(
        db=db,
        action="alert_acked",
        actor_id=payload.operator_id,
        target_type="alert",
        target_id=alert_id,
        details={"note": payload.note},
    )

    db.commit()

    await ws_manager.broadcast_to_ops({
        "event": "alert.acked",
        "data": {
            "id": alert_id,
            "acked_by": payload.operator_id,
            "ts": datetime.utcnow().isoformat(),
        },
    })

    return {"status": "acked", "alert_id": alert_id, "acked_by": payload.operator_id}


@router.post("/alerts/{alert_id}/cancel")
async def cancel_alert(
    alert_id: str,
    payload: CancelPayload,
    db: Session = Depends(get_db),
    x_operator_token: Optional[str] = Header(default=None, alias="X-Operator-Token"),
):
    """
    Cancel an alert — only valid within the cancel window (30 s).
    After the window expires the cancel is rejected; this enforces that
    an operator cannot silently suppress a live alert after the fact.
    Writes to evidence_chain regardless of outcome. operator_id is
    authenticated the same way as POST /v1/entities/{id}/verify.
    """
    require_operator_token(payload.operator_id, x_operator_token)

    alert = _assert_alert_exists(alert_id, db)
    _assert_not_terminal(alert)

    now = datetime.utcnow()

    # Cancel-window enforcement
    if alert.cancel_window_expires and now > alert.cancel_window_expires:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cancel window expired at "
                f"{alert.cancel_window_expires.isoformat()} — "
                f"alert cannot be cancelled after the window closes"
            ),
        )

    alert.status = "cancelled"

    await _write_evidence(
        db=db,
        action="alert_cancelled",
        actor_id=payload.operator_id,
        target_type="alert",
        target_id=alert_id,
        details={
            "reason": payload.reason,
            "cancelled_at": now.isoformat(),
        },
    )

    db.commit()

    await ws_manager.broadcast_to_ops({
        "event": "alert.cancelled",
        "data": {
            "id": alert_id,
            "cancelled_by": payload.operator_id,
            "ts": now.isoformat(),
        },
    })

    return {"status": "cancelled", "alert_id": alert_id}
