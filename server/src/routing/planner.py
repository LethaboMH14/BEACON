"""
BEACON patrol route planner (docs/01-ARCHITECTURE.md §5, ADR D8) — POST /v1/routes/plan.

Team-orienteering formulation, per D8: maximize risk-weighted coverage under a
fuel/time budget, with a fixed dwell (Koper dose) at every visited stop —
NOT plain shortest-path TSP, which would just visit everything in the cheapest
order regardless of value.

Candidate stops come from `risk.rank_hotspots` (reuses the same tiering —
real model row if Ndu's forecast exists, else the honest claims fallback; see
risk/forecast.py's module header). Distance is haversine (straight-line), per
the OSRM feasibility nitpick already recorded in team/SBU.md — real
road-network routing is real infra, not a library import, and standing up
OSRM mid-hackathon isn't worth blocking route planning on. Each stop's
coordinates are the real centroid (mean lat/lng) of the Claim rows in that
hex — NOT derived from hex_id via H3 math, because the hex_id strings already
used across this repo's fixtures/seed data are not valid H3 cell indices
(`h3.cell_to_latlng` rejects them) — using real claim coordinates is honest
and doesn't depend on that being fixed first.

OR-Tools modelling: a vehicle-routing problem with OPTIONAL visits
(`AddDisjunction`), where skipping a stop costs a penalty proportional to its
risk score — the standard "team orienteering via VRP + disjunction penalties"
pattern. Two capacity dimensions per team: cumulative haversine distance
(fuel budget) and cumulative time = travel time + a fixed dwell per stop
visited (shift window budget, D8's 12-min Koper dose).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from sqlalchemy.orm import Session

from ..db.models import Claim
from ..risk import rank_hotspots

# ── tunables (design choices, not fitted — flagged, not hidden) ─────────────
KOPER_DWELL_MINUTES = 12          # D8: 11-15 min dose; midpoint
AVG_PATROL_SPEED_KMH = 35.0       # city-driving assumption for the time budget
RISK_REWARD_SCALE = 100_000       # penalty units per unit of risk_score (0..1)
DEFAULT_MAX_CANDIDATES = 12       # keeps the solve trivially fast for a demo
SOLVE_TIME_LIMIT_SECONDS = 5


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line great-circle distance in km. Mirrors suspicion/scorer.py's
    _haversine_km (kept local rather than cross-imported to avoid coupling two
    otherwise-independent modules over a five-line function; both are OSRM
    stand-ins per the same G0 nitpick and should move to a shared geo util if
    a third caller ever needs it)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


@dataclass
class RouteStop:
    hex_id: str
    lat: float
    lng: float
    risk_score: float
    label: str
    arrival_offset_minutes: float   # minutes after shift start


@dataclass
class TeamRoute:
    team_id: int
    stops: list[RouteStop]
    total_distance_km: float
    total_time_minutes: float


@dataclass
class RoutePlan:
    routes: list[TeamRoute]
    dropped_hexes: list[str]          # candidates the solver couldn't fit in budget
    unlocatable_hexes: list[str]      # candidates with no real coordinates on record
    total_risk_covered: float
    fuel_budget_km: float
    shift_window_minutes: float
    dwell_minutes: int = KOPER_DWELL_MINUTES


def _hex_centroid(hex_id: str, db: Session) -> Optional[tuple[float, float]]:
    """Real centroid from actual Claim rows in this hex — None if we have no
    located claims for it (can't invent a coordinate)."""
    rows = (
        db.query(Claim.lat, Claim.lng)
        .filter(Claim.hex_id == hex_id, Claim.lat.isnot(None), Claim.lng.isnot(None))
        .all()
    )
    if not rows:
        return None
    lats = [r[0] for r in rows]
    lngs = [r[1] for r in rows]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def plan_routes(
    hour: int,
    db: Session,
    depot_lat: float,
    depot_lng: float,
    num_teams: int = 1,
    fuel_budget_km: float = 60.0,
    shift_window_minutes: float = 240.0,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> RoutePlan:
    if num_teams < 1:
        raise ValueError("num_teams must be >= 1")
    if fuel_budget_km <= 0 or shift_window_minutes <= 0:
        raise ValueError("fuel_budget_km and shift_window_minutes must be > 0")

    candidates = rank_hotspots(hour, db, limit=max_candidates)

    located: list[tuple] = []       # (estimate, lat, lng)
    unlocatable: list[str] = []
    for est in candidates:
        centroid = _hex_centroid(est.hex_id, db)
        if centroid is None:
            unlocatable.append(est.hex_id)
            continue
        located.append((est, centroid[0], centroid[1]))

    if not located:
        return RoutePlan(
            routes=[TeamRoute(team_id=i, stops=[], total_distance_km=0.0, total_time_minutes=0.0)
                     for i in range(num_teams)],
            dropped_hexes=[], unlocatable_hexes=unlocatable,
            total_risk_covered=0.0,
            fuel_budget_km=fuel_budget_km, shift_window_minutes=shift_window_minutes,
        )

    # Node 0 = depot; nodes 1..N = candidate stops.
    coords = [(depot_lat, depot_lng)] + [(lat, lng) for _, lat, lng in located]
    n = len(coords)

    dist_km = [[_haversine_km(*coords[i], *coords[j]) for j in range(n)] for i in range(n)]
    dist_m = [[int(round(km * 1000)) for km in row] for row in dist_km]

    def travel_minutes(i: int, j: int) -> int:
        return int(round((dist_km[i][j] / AVG_PATROL_SPEED_KMH) * 60))

    manager = pywrapcp.RoutingIndexManager(n, num_teams, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
        return dist_m[i][j]

    distance_cb_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(distance_cb_index)

    def time_callback(from_index, to_index):
        i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
        dwell = KOPER_DWELL_MINUTES if i != 0 else 0  # dwell happens AT a real stop before leaving it
        return travel_minutes(i, j) + dwell

    time_cb_index = routing.RegisterTransitCallback(time_callback)

    routing.AddDimension(
        distance_cb_index, 0, int(fuel_budget_km * 1000), True, "Distance"
    )
    routing.AddDimension(
        time_cb_index, 0, int(shift_window_minutes), True, "Time"
    )

    # Every non-depot node is optional; skipping it costs its risk value.
    for node_idx, (est, _, _) in enumerate(located, start=1):
        penalty = int(round(est.risk_score * RISK_REWARD_SCALE)) or 1
        routing.AddDisjunction([manager.NodeToIndex(node_idx)], penalty)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.FromSeconds(SOLVE_TIME_LIMIT_SECONDS)

    solution = routing.SolveWithParameters(search_params)

    if solution is None:
        # Infeasible even with everything droppable (shouldn't happen — dropping
        # all nodes is always a valid solution — but fail loudly, not silently).
        raise RuntimeError("OR-Tools found no feasible solution, including the drop-everything case")

    routes: list[TeamRoute] = []
    visited_node_indices: set[int] = set()
    time_dim = routing.GetDimensionOrDie("Time")

    for vehicle_id in range(num_teams):
        index = routing.Start(vehicle_id)
        stops: list[RouteStop] = []
        route_distance_m = 0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                visited_node_indices.add(node)
                est, lat, lng = located[node - 1]
                arrival_min = solution.Value(time_dim.CumulVar(index))
                stops.append(RouteStop(
                    hex_id=est.hex_id, lat=lat, lng=lng,
                    risk_score=est.risk_score, label=est.label,
                    arrival_offset_minutes=float(arrival_min),
                ))
            next_index = solution.Value(routing.NextVar(index))
            if not routing.IsEnd(next_index):
                route_distance_m += dist_m[node][manager.IndexToNode(next_index)]
            else:
                route_distance_m += dist_m[node][0]
            index = next_index

        total_time = solution.Value(time_dim.CumulVar(routing.End(vehicle_id)))
        routes.append(TeamRoute(
            team_id=vehicle_id, stops=stops,
            total_distance_km=round(route_distance_m / 1000.0, 2),
            total_time_minutes=float(total_time),
        ))

    dropped = [
        located[i - 1][0].hex_id
        for i in range(1, n)
        if i not in visited_node_indices
    ]
    total_risk_covered = sum(
        s.risk_score for r in routes for s in r.stops
    )

    return RoutePlan(
        routes=routes, dropped_hexes=dropped, unlocatable_hexes=unlocatable,
        total_risk_covered=round(total_risk_covered, 3),
        fuel_budget_km=fuel_budget_km, shift_window_minutes=shift_window_minutes,
    )
