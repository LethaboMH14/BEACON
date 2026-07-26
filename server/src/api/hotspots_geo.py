"""
GET /v1/hotspots/geo — the map-ready view of Ndu's hotspot pipeline.

WHY A SECOND HOTSPOT ENDPOINT
`GET /v1/hotspots` (api/risk.py) answers "which hexes are riskiest at hour H",
returning hex_id + score. That's the operator/patrol question, and the OR-Tools
planner consumes it. It deliberately carries no coordinates or place names.

The member-facing map asks a different question: "draw me every suburb Discovery
has a claims history for, with enough detail to explain itself in a popup."
Rather than bloat the existing contract with fields the patrol planner would
never read, this is its own endpoint.

EVERYTHING HERE IS REAL, NOTHING IS DERIVED FOR DISPLAY
Rows come from the RiskCell table where model_version='ndu-hotspot-v1' — written
by scripts/load_hotspots.py straight out of hotspot_pipeline/hotspots_geocoded.csv
(709 suburbs, >=5 incidents each, Nominatim-geocoded). risk_score IS Ndu's
composite severity (0.5*frequency_norm + 0.5*cost_norm); we do not rescale it.
top_factors carries that suburb's own top_claim_type / incident_count /
peak_month / peak_day_of_week.

Coordinates and the human-readable suburb name are NOT on RiskCell (hex_id is a
hash of the suburb name — see load_hotspots.suburb_hex_id), so both are recovered
from the Claim rows in that hex, which load_hotspots.py backfilled with the same
CSV's lat/lon. One query, grouped in Python, not 709 queries.

HONESTY BOUNDARY (mirrors risk/forecast.py and ADR-0002's spirit)
One geocoded point per suburb, matched by name + "South Africa" with no province.
This is suburb-level claims history, NOT a street-level crime prediction, and the
response says so in `method` and `caveat` so a client cannot render it without
the caveat being available. Cost figures exclude the 81 anomalous claim amounts,
per the cleaning script's own rule.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import Claim, RiskCell

router = APIRouter()

NDU_MODEL_VERSION = "ndu-hotspot-v1"

METHOD = "suburb_centroid_from_claims_history"
CAVEAT = (
    "Suburb-level severity from historical Discovery claims, geocoded to one "
    "point per suburb. Not a street-level crime prediction."
)

# Marker rules copied verbatim from hotspot_pipeline/build_hotspots.py::build_map_html
# so the in-app map reproduces the standalone hotspot_map.html the client already
# approved. Do not "improve" these — matching the approved artifact is the point.
SEVERITY_HIGH = 0.66
SEVERITY_MEDIUM = 0.33
COLOR_HIGH = "#c0392b"
COLOR_MEDIUM = "#e67e22"
COLOR_LOW = "#f1c40f"


def marker_style(severity: float) -> tuple[str, float]:
    """(fillColor, radius) — build_hotspots.py's exact rules."""
    if severity >= SEVERITY_HIGH:
        color = COLOR_HIGH
    elif severity >= SEVERITY_MEDIUM:
        color = COLOR_MEDIUM
    else:
        color = COLOR_LOW
    return color, round(6 + (severity * 20), 1)


class HotspotGeo(BaseModel):
    hex_id: str
    suburb: str
    lat: float
    lng: float
    severity_score: float
    incident_count: Optional[int] = None
    top_claim_type: Optional[str] = None
    peak_hour: int
    peak_day_of_week: Optional[str] = None
    peak_month: Optional[str] = None
    total_claim_cost: float
    avg_claim_cost: float
    # presentation, server-side, so every client draws the approved map identically
    color: str
    radius: float


class HotspotsGeoRes(BaseModel):
    count: int
    total_claims_analysed: int
    method: str
    caveat: str
    model_version: str
    hotspots: list[HotspotGeo]


@router.get("/hotspots/geo", response_model=HotspotsGeoRes)
async def get_hotspots_geo(
    hour: Optional[int] = Query(None, ge=0, le=23, description="Only suburbs whose own peak hour is this"),
    day: Optional[str] = Query(None, description="Only suburbs whose own peak day is this, e.g. Friday"),
    peril: Optional[str] = Query(None, description="Only suburbs whose top claim type is this"),
    min_severity: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    cells = (
        db.query(RiskCell)
        .filter(RiskCell.model_version == NDU_MODEL_VERSION,
                RiskCell.risk_score >= min_severity)
        .all()
    )
    if not cells:
        return HotspotsGeoRes(
            count=0, total_claims_analysed=0, method=METHOD, caveat=CAVEAT,
            model_version=NDU_MODEL_VERSION, hotspots=[],
        )

    # One pass over the located claims in these hexes: coordinates, suburb name,
    # and the cost figures. Anomalous amounts were already excluded at load time
    # by the cleaning script, so a NULL/<=0 amount here is skipped rather than
    # dragging the average down.
    hex_ids = {c.hex_id for c in cells}
    rows = (
        db.query(Claim.hex_id, Claim.suburb, Claim.lat, Claim.lng, Claim.amount)
        .filter(Claim.hex_id.in_(hex_ids), Claim.lat.isnot(None))
        .all()
    )

    by_hex: dict[str, dict] = {}
    for hex_id, suburb, lat, lng, amount in rows:
        agg = by_hex.setdefault(hex_id, {"suburb": suburb, "lat": lat, "lng": lng,
                                         "cost": 0.0, "n_cost": 0, "n": 0})
        agg["n"] += 1
        if amount is not None and amount > 0:
            agg["cost"] += amount
            agg["n_cost"] += 1

    out: list[HotspotGeo] = []
    total_claims = 0
    for cell in cells:
        agg = by_hex.get(cell.hex_id)
        if agg is None:
            continue  # no located claim for this hex — can't place it, don't invent a point

        factors = cell.top_factors or {}
        if day and (factors.get("peak_day_of_week") or "").lower() != day.lower():
            continue
        if peril and (factors.get("top_claim_type") or "").lower() != peril.lower():
            continue
        if hour is not None and cell.hour != hour:
            continue

        severity = round(cell.risk_score, 4)
        color, radius = marker_style(severity)
        incident_count = factors.get("incident_count") or agg["n"]
        total_claims += incident_count

        out.append(HotspotGeo(
            hex_id=cell.hex_id,
            suburb=agg["suburb"],
            lat=agg["lat"],
            lng=agg["lng"],
            severity_score=severity,
            incident_count=incident_count,
            top_claim_type=factors.get("top_claim_type"),
            peak_hour=cell.hour,
            peak_day_of_week=factors.get("peak_day_of_week"),
            peak_month=factors.get("peak_month"),
            total_claim_cost=round(agg["cost"], 2),
            avg_claim_cost=round(agg["cost"] / agg["n_cost"], 2) if agg["n_cost"] else 0.0,
            color=color,
            radius=radius,
        ))

    out.sort(key=lambda h: h.severity_score, reverse=True)
    return HotspotsGeoRes(
        count=len(out),
        total_claims_analysed=total_claims,
        method=METHOD,
        caveat=CAVEAT,
        model_version=NDU_MODEL_VERSION,
        hotspots=out,
    )
