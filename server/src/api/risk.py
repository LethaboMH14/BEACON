"""
GET /v1/risk, GET /v1/hotspots — docs/01-ARCHITECTURE.md §5.
See src/risk/forecast.py's module header for the honesty boundary: these serve
a real claims-derived fallback today, and will pass through Ndu's real model
untouched once it lands in the RiskCell table — no contract change needed.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import RiskCell
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


class RiskCellIn(BaseModel):
    hex_id: str
    forecast_date: datetime
    hour: int = Field(..., ge=0, le=23)
    risk_score: float = Field(..., ge=0.0, le=1.0)
    top_factors: Optional[dict] = None
    model_version: str


class RiskCellsIngestReq(BaseModel):
    cells: list[RiskCellIn] = Field(..., min_length=1)


class RiskCellsIngestRes(BaseModel):
    inserted: int


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


@router.post("/risk-cells", response_model=RiskCellsIngestRes, status_code=status.HTTP_201_CREATED)
async def post_risk_cells(body: RiskCellsIngestReq, db: Session = Depends(get_db)):
    """
    Write path for Ndu's forecast pipeline (team/SBU.md 2026-07-25 backlog):
    /v1/risk and /v1/hotspots already read the latest RiskCell row per
    (hex_id, hour) — see src/risk/forecast.py — but until now nothing could
    write one outside of tests. Real model output lands here; the fallback
    in forecast.py is superseded automatically per-hex/hour the moment a
    row exists, no contract change needed.
    """
    rows = [
        RiskCell(
            hex_id=c.hex_id, forecast_date=c.forecast_date, hour=c.hour,
            risk_score=c.risk_score, top_factors=c.top_factors,
            model_version=c.model_version,
        )
        for c in body.cells
    ]
    db.add_all(rows)
    db.commit()
    return RiskCellsIngestRes(inserted=len(rows))
