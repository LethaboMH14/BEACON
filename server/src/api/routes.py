"""
POST /v1/routes/plan — docs/01-ARCHITECTURE.md §5.
See src/routing/planner.py's module header for the full modelling rationale
(team-orienteering VRP with disjunction penalties, haversine not OSRM,
real-claim centroids not H3 math).
"""
from datetime import datetime, timedelta
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..db.models import Route
from ..routing import plan_routes

router = APIRouter()


class RoutePlanReq(BaseModel):
    teams: int = Field(..., ge=1, description="Number of patrol teams/vehicles")
    shift_window_minutes: float = Field(..., gt=0)
    fuel_budget_km: float = Field(..., gt=0)
    depot_lat: float
    depot_lng: float
    hour: Optional[int] = Field(None, ge=0, le=23, description="Defaults to current UTC hour")
    max_candidates: int = Field(12, ge=1, le=50)


class RouteStopRes(BaseModel):
    hex_id: str
    lat: float
    lng: float
    risk_score: float
    label: str
    arrival_offset_minutes: float


class TeamRouteRes(BaseModel):
    team_id: int
    stops: list[RouteStopRes]
    total_distance_km: float
    total_time_minutes: float


class RoutePlanRes(BaseModel):
    routes: list[TeamRouteRes]
    dropped_hexes: list[str]
    unlocatable_hexes: list[str]
    total_risk_covered: float
    fuel_budget_km: float
    shift_window_minutes: float
    dwell_minutes: int


@router.post("/routes/plan", response_model=RoutePlanRes)
async def post_routes_plan(body: RoutePlanReq, db: Session = Depends(get_db)):
    resolved_hour = body.hour if body.hour is not None else datetime.utcnow().hour

    try:
        plan = plan_routes(
            hour=resolved_hour,
            db=db,
            depot_lat=body.depot_lat,
            depot_lng=body.depot_lng,
            num_teams=body.teams,
            fuel_budget_km=body.fuel_budget_km,
            shift_window_minutes=body.shift_window_minutes,
            max_candidates=body.max_candidates,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Route persistence (team/SBU.md backlog, 2026-07-25): plan_routes() only
    # returned a plan, never wrote the Route row the schema already has —
    # fine for a single-shot demo, but nothing else could ever look a plan
    # up afterwards. Persist one Route row per team.
    now = datetime.utcnow()
    shift_end = now + timedelta(minutes=body.shift_window_minutes)
    total_candidates = len(plan.dropped_hexes) + sum(len(r.stops) for r in plan.routes)
    for r in plan.routes:
        coverage_pct = (len(r.stops) / total_candidates * 100.0) if total_candidates else 0.0
        db.add(Route(
            id=f"rt_{uuid.uuid4().hex[:16]}",
            team_id=str(r.team_id),
            shift_start=now,
            shift_end=shift_end,
            stops=[
                {"hex_id": s.hex_id, "lat": s.lat, "lng": s.lng,
                 "risk_score": s.risk_score, "arrival_offset_minutes": s.arrival_offset_minutes}
                for s in r.stops
            ],
            fuel_budget=body.fuel_budget_km,
            coverage_pct=coverage_pct,
            status="planned",
        ))
    db.commit()

    return RoutePlanRes(
        routes=[
            TeamRouteRes(
                team_id=r.team_id,
                stops=[
                    RouteStopRes(
                        hex_id=s.hex_id, lat=s.lat, lng=s.lng,
                        risk_score=s.risk_score, label=s.label,
                        arrival_offset_minutes=s.arrival_offset_minutes,
                    )
                    for s in r.stops
                ],
                total_distance_km=r.total_distance_km,
                total_time_minutes=r.total_time_minutes,
            )
            for r in plan.routes
        ],
        dropped_hexes=plan.dropped_hexes,
        unlocatable_hexes=plan.unlocatable_hexes,
        total_risk_covered=plan.total_risk_covered,
        fuel_budget_km=plan.fuel_budget_km,
        shift_window_minutes=plan.shift_window_minutes,
        dwell_minutes=plan.dwell_minutes,
    )
