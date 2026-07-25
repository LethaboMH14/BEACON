"""
POST /v1/routes/safest — score member route options by claims exposure.

Sits beside POST /v1/routes/plan (api/routes.py) but answers the opposite
question; see routing/safest.py's header for why the two must not be merged.

CONTRACT SHAPE, AND WHY GEOMETRY IS AN INPUT
The caller sends one or more candidate routes as polylines. We do not fetch
road geometry: that needs a routing provider (OpenRouteService), whose key is
not in this repo. Making geometry an input rather than a TODO means the honest
version ships today — the exposure maths, which is the actual contribution, runs
on real claims data right now — and wiring a provider later is a change in the
caller, not here.

Each route carries its own `geometry_source` string, echoed back on the response
unmodified, so a client physically cannot render an approximated line as though
it came from a road network. Use "ors" for provider geometry, "approx" for a
straight-line placeholder.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import Claim, RiskCell
from ..routing.safest import (
    EXPOSURE_RADIUS_KM,
    HotspotPoint,
    compare_routes,
    score_route,
)

router = APIRouter()

NDU_MODEL_VERSION = "ndu-hotspot-v1"

METHOD_NOTE = (
    "Exposure is a distance-weighted sum of suburb-level claims severity within "
    f"{EXPOSURE_RADIUS_KM} km of the route, weighted by time of day. It compares "
    "routes against each other. It is not a probability of being a victim."
)


class CandidateRoute(BaseModel):
    id: str
    label: str
    # [[lat, lng], ...] — order matters, it is a path not a set
    polyline: list[tuple[float, float]] = Field(..., min_length=2)
    duration_minutes: Optional[float] = None
    geometry_source: Literal["ors", "approx"] = Field(
        ...,
        description="'ors' = real road geometry. 'approx' = straight-line placeholder; "
                    "the client MUST label it as approximate.",
    )


class SafestRouteReq(BaseModel):
    routes: list[CandidateRoute] = Field(..., min_length=1)
    depart_hour: Optional[int] = Field(None, ge=0, le=23, description="Defaults to current local hour")


class SuburbExposureRes(BaseModel):
    suburb: str
    hex_id: str
    severity: float
    top_claim_type: Optional[str]
    incident_count: Optional[int]
    exposed_metres: int
    at_peak_hour: bool
    contribution: float


class ScoredRouteRes(BaseModel):
    id: str
    label: str
    geometry_source: str
    distance_km: float
    duration_minutes: Optional[float]
    exposure_score: float
    recommended: bool
    # one plain-language line the UI can show without composing copy itself,
    # which is how "advice" text drifts away from the numbers behind it
    advice: Optional[str]
    suburbs: list[SuburbExposureRes]


class SafestRouteRes(BaseModel):
    depart_hour: int
    routes: list[ScoredRouteRes]
    exposure_reduction_pct: Optional[float]
    hotspots_considered: int
    method: str
    model_version: str


def _load_hotspot_points(db: Session) -> list[HotspotPoint]:
    """
    RiskCell has severity + peak hour but no name/coords (hex_id is an md5 of the
    suburb — see scripts/load_hotspots.suburb_hex_id), so coordinates come from
    the Claim rows in each hex. Two queries total, not one per suburb.
    """
    cells = db.query(RiskCell).filter(RiskCell.model_version == NDU_MODEL_VERSION).all()
    if not cells:
        return []

    hex_ids = {c.hex_id for c in cells}
    located: dict[str, tuple[str, float, float]] = {}
    for hex_id, suburb, lat, lng in (
        db.query(Claim.hex_id, Claim.suburb, Claim.lat, Claim.lng)
        .filter(Claim.hex_id.in_(hex_ids), Claim.lat.isnot(None))
        .all()
    ):
        located.setdefault(hex_id, (suburb, lat, lng))

    points: list[HotspotPoint] = []
    for cell in cells:
        loc = located.get(cell.hex_id)
        if loc is None:
            continue  # ungeocoded suburb — cannot place it, so it cannot be on a route
        suburb, lat, lng = loc
        factors = cell.top_factors or {}
        points.append(HotspotPoint(
            hex_id=cell.hex_id,
            suburb=suburb,
            lat=lat,
            lng=lng,
            severity=cell.risk_score,
            peak_hour=cell.hour,
            top_claim_type=factors.get("top_claim_type"),
            incident_count=factors.get("incident_count"),
        ))
    return points


def _advice_for(worst, is_recommended: bool) -> Optional[str]:
    """
    Advice is generated from the top contributor only. Listing every suburb a
    route touches produces a wall of warnings that members learn to ignore —
    the alert-fatigue failure mode. One specific, checkable sentence instead.
    """
    if worst is None:
        return "No suburb with significant claims history on this route." if is_recommended else None

    peril = (worst.top_claim_type or "claims").lower()
    when = " around this hour" if worst.at_peak_hour else ""
    km = worst.exposed_metres / 1000
    return (
        f"Passes {km:.1f} km through {worst.suburb.title()}, which has "
        f"{worst.incident_count or 'several'} Discovery claims on record, "
        f"mostly {peril}{when}."
    )


@router.post("/routes/safest", response_model=SafestRouteRes)
async def score_safest_route(req: SafestRouteReq, db: Session = Depends(get_db)):
    hotspots = _load_hotspot_points(db)
    if not hotspots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hotspot data loaded. Run server/scripts/load_hotspots.py.",
        )

    depart_hour = req.depart_hour if req.depart_hour is not None else datetime.now().hour

    scored = [(r, score_route(r.polyline, hotspots, depart_hour)) for r in req.routes]
    best_id = min(scored, key=lambda pair: pair[1].exposure_score)[0].id

    out: list[ScoredRouteRes] = []
    for route, sc in scored:
        recommended = route.id == best_id
        out.append(ScoredRouteRes(
            id=route.id,
            label=route.label,
            geometry_source=route.geometry_source,
            distance_km=sc.distance_km,
            duration_minutes=route.duration_minutes,
            exposure_score=sc.exposure_score,
            recommended=recommended,
            advice=_advice_for(sc.worst, recommended),
            # Cap the per-route list: beyond the top few, contributions are
            # rounding noise and the payload triples for no decision value.
            suburbs=[SuburbExposureRes(**vars(s)) for s in sc.suburbs[:5]],
        ))

    out.sort(key=lambda r: (not r.recommended, r.exposure_score))
    return SafestRouteRes(
        depart_hour=depart_hour,
        routes=out,
        exposure_reduction_pct=compare_routes([sc for _, sc in scored]),
        hotspots_considered=len(hotspots),
        method=METHOD_NOTE,
        model_version=NDU_MODEL_VERSION,
    )
