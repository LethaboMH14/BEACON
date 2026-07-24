"""
BEACON database models.
Schema v0: cameras, sightings, entities, whitelist, watchlist, claims, 
risk_cells, incidents, alerts, routes, evidence_chain.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, DateTime, Boolean, Text, JSON,
    ForeignKey, Index, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Camera(Base):
    """Camera/sensor registration."""
    __tablename__ = "cameras"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hex_id: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)  # H3 hex res 8/9
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, offline, maintenance
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # member ID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sightings: Mapped[list["Sighting"]] = relationship(back_populates="camera")


class Entity(Base):
    """Resolved identity (face/plate/vehicle embedding cluster)."""
    __tablename__ = "entities"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # person, vehicle, unknown
    embedding_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Reference to embedding storage
    plate_text: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # Normalized plate
    
    # Suspicion tracking (lazy decay at read-time)
    base_score: Mapped[float] = mapped_column(Float, default=0.0)  # Log-odds base score
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    state: Mapped[str] = mapped_column(String(32), default="observed")  # observed, candidate, flagged
    
    # Metadata
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sighting_count: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sightings: Mapped[list["Sighting"]] = relationship(back_populates="entity")
    
    __table_args__ = (
        Index("idx_entities_state", "state"),
        Index("idx_entities_plate", "plate_text"),
    )


class Sighting(Base):
    """Single camera detection event."""
    __tablename__ = "sightings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(64), ForeignKey("cameras.id"), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("entities.id"), nullable=True)
    
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    hex_id: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # person, vehicle, weapon
    modality: Mapped[str] = mapped_column(String(32), nullable=False)  # face, plate, yolo, audio
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Detection details
    bbox: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {x, y, w, h}
    embedding_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plate_text: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    plate_quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clip_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Short clip on escalation
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    camera: Mapped["Camera"] = relationship(back_populates="sightings")
    entity: Mapped[Optional["Entity"]] = relationship(back_populates="sightings")
    
    __table_args__ = (
        Index("idx_sightings_ts", "ts"),
        Index("idx_sightings_hex", "hex_id", "ts"),
        Index("idx_sightings_entity", "entity_id", "ts"),
    )


class Whitelist(Base):
    """Residents/regulars known to a street — kills recurrence false positives."""
    __tablename__ = "whitelist"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(64), ForeignKey("entities.id"), nullable=False)
    hex_id: Mapped[str] = mapped_column(String(15), nullable=False)  # Street/area
    
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # resident, worker, delivery, visitor
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Human-readable label
    
    added_by: Mapped[str] = mapped_column(String(64), nullable=False)  # Operator/member ID
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # For visitors
    
    __table_args__ = (
        Index("idx_whitelist_entity_hex", "entity_id", "hex_id"),
    )


class Watchlist(Base):
    """Flagged entities (human-verified only)."""
    __tablename__ = "watchlist"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(64), ForeignKey("entities.id"), nullable=False, unique=True)
    
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    verified_by: Mapped[str] = mapped_column(String(64), nullable=False)  # Operator ID
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Claim(Base):
    """Discovery insurance claims (Gradhack_Insure_Data.xlsx ingested)."""
    __tablename__ = "claims"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)  # Theft, Burglary, Hijack, etc.
    suburb: Mapped[str] = mapped_column(String(255), nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hex_id: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    
    claim_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hour_known: Mapped[bool] = mapped_column(Boolean, default=False)
    
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_claims_hex_date", "hex_id", "claim_date"),
        Index("idx_claims_type", "claim_type"),
    )


class RiskCell(Base):
    """Per-hex, per-hour risk forecast."""
    __tablename__ = "risk_cells"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hex_id: Mapped[str] = mapped_column(String(15), nullable=False)
    
    forecast_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # Calibrated probability
    top_factors: Mapped[dict] = mapped_column(JSON, nullable=True)  # Explainability
    
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_risk_hex_time", "hex_id", "forecast_date", "hour"),
        CheckConstraint("hour >= 0 AND hour < 24", name="check_hour_range"),
    )


class Incident(Base):
    """Verified security incident."""
    __tablename__ = "incidents"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)  # burglary, theft, panic, suspicious
    
    hex_id: Mapped[str] = mapped_column(String(15), nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, resolved, false_alarm
    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # low, medium, high, critical
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("entities.id"), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_incidents_hex_time", "hex_id", "occurred_at"),
    )


class Alert(Base):
    """Alert sent to operators/members (with cancel window)."""
    __tablename__ = "alerts"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)  # entity_flagged, hard_trigger, forecast_spike
    
    recipient_id: Mapped[str] = mapped_column(String(64), nullable=False)  # Operator or member ID
    recipient_type: Mapped[str] = mapped_column(String(32), nullable=False)  # ops, member
    
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("entities.id"), nullable=True)
    incident_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("incidents.id"), nullable=True)
    
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, acked, cancelled, expired
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acked_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    cancel_window_expires: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_alerts_recipient", "recipient_id", "status"),
        Index("idx_alerts_created", "created_at"),
    )


class Route(Base):
    """Koper-dosed patrol route (12-min stops)."""
    __tablename__ = "routes"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    shift_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    shift_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    stops: Mapped[list] = mapped_column(JSON, nullable=False)  # [{hex_id, dwell_min, arrive_at, risk_score}]
    
    fuel_budget: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)  # % of top-risk hexes covered
    
    status: Mapped[str] = mapped_column(String(32), default="planned")  # planned, active, completed
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_routes_team_shift", "team_id", "shift_start"),
    )


class EvidenceChain(Base):
    """Hash-chained audit log (ported from VUKA)."""
    __tablename__ = "evidence_chain"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # verify, flag, dismiss, alert_send, alert_ack
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # entity, alert, incident
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    details: Mapped[dict] = mapped_column(JSON, nullable=True)
    
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    __table_args__ = (
        Index("idx_evidence_target", "target_type", "target_id"),
    )
