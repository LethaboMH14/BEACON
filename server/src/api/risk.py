"""
GET /v1/risk, GET /v1/hotspots — docs/01-ARCHITECTURE.md §5.
See src/risk/forecast.py's module header for the honesty boundary: these serve
a real claims-derived fallback today, and will pass through Ndu's real model
untouched once it lands in the RiskCell table — no contract change needed.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..risk import estimate_hex_risk, rank_hotspots

router = APIRouter()


class RiskRes(BaseModel):
    hex_id: str
    hour: int
    risk_score: float
    label: str
    source: str
    top_factors: Optional[dict] = None
    model_version: Optional[str] = None


class HotspotEntry(BaseModel):
    hex_id: str
    risk_score: float
    label: str
    source: str


class HotspotsRes(BaseModel):
    hour: int
    hotspots: list[HotspotEntry]


def _current_hour_or(hour: Optional[int]) -> int:
    return hour if hour is not None else datetime.utcnow().hour


@router.get("/risk", response_model=RiskRes)
async def get_risk(
    hex: str = Query(..., description="H3 hex ID"),
    hour: Optional[int] = Query(None, ge=0, le=23, description="Hour 0-23; defaults to current UTC hour"),
    db: Session = Depends(get_db),
):
    resolved_hour = _current_hour_or(hour)
    try:
        estimate = estimate_hex_risk(hex, resolved_hour, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return RiskRes(
        hex_id=estimate.hex_id, hour=estimate.hour, risk_score=estimate.risk_score,
        label=estimate.label, source=estimate.source,
        top_factors=estimate.top_factors, model_version=estimate.model_version,
    )


@router.get("/hotspots", response_model=HotspotsRes)
async def get_hotspots(
    window: Optional[int] = Query(None, ge=0, le=23, description="Hour 0-23; defaults to current UTC hour"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    resolved_hour = _current_hour_or(window)
    try:
        estimates = rank_hotspots(resolved_hour, db, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return HotspotsRes(
        hour=resolved_hour,
        hotspots=[
            HotspotEntry(hex_id=e.hex_id, risk_score=e.risk_score, label=e.label, source=e.source)
            for e in estimates
        ],
    )
