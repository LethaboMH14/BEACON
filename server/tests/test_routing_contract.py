"""
Contract tests for POST /v1/routes/plan.
Contract from docs/01-ARCHITECTURE.md §5, ADR D8 (team-orienteering,
Koper-dosed patrol). Distance is haversine — real road-network (OSRM)
deferred per team/SBU.md's feasibility nitpick.
"""
from datetime import datetime, timedelta

import pytest

from src.db.models import Claim
from src.routing.planner import plan_routes


def _make_claim(db, hex_id, lat, lng, hour=0, claim_number=None):
    c = Claim(
        claim_number=claim_number or f"C-{hex_id}-{lat}-{lng}",
        claim_type="Theft", suburb="Test Suburb",
        hex_id=hex_id, lat=lat, lng=lng,
        claim_date=datetime.utcnow() - timedelta(days=10),
        hour=hour, hour_known=True, amount=8000.0,
    )
    db.add(c)
    db.commit()
    return c


def test_no_candidates_returns_empty_routes_not_an_error(db_session):
    plan = plan_routes(hour=5, db=db_session, depot_lat=-26.1, depot_lng=28.0, num_teams=2)
    assert len(plan.routes) == 2
    assert all(r.stops == [] for r in plan.routes)
    assert plan.dropped_hexes == []


def test_visits_nearby_high_value_hex_over_far_low_value_one(db_session):
    for i in range(8):
        _make_claim(db_session, "hex_near_high", -26.10, 28.05, claim_number=f"nh-{i}")
    _make_claim(db_session, "hex_far_low", -26.20, 28.20, claim_number="fl-0")

    plan = plan_routes(
        hour=0, db=db_session, depot_lat=-26.10, depot_lng=28.05,
        num_teams=1, fuel_budget_km=100, shift_window_minutes=240,
    )
    visited = {s.hex_id for r in plan.routes for s in r.stops}
    assert "hex_near_high" in visited
    assert "hex_far_low" in plan.dropped_hexes


def test_fuel_budget_is_respected(db_session):
    # Two hexes far enough apart that visiting both exceeds a tiny fuel budget.
    _make_claim(db_session, "hex_1", -26.10, 28.05, claim_number="f1")
    _make_claim(db_session, "hex_2", -26.50, 28.50, claim_number="f2")  # ~55km away

    plan = plan_routes(
        hour=0, db=db_session, depot_lat=-26.10, depot_lng=28.05,
        num_teams=1, fuel_budget_km=10.0, shift_window_minutes=240,
    )
    for r in plan.routes:
        assert r.total_distance_km <= 10.0 + 0.01  # small float tolerance
    # Can't visit both within a 10km budget when they're ~55km apart.
    visited = {s.hex_id for r in plan.routes for s in r.stops}
    assert not {"hex_1", "hex_2"}.issubset(visited)


def test_hex_with_no_located_claims_is_unlocatable_not_silently_skipped(db_session):
    # A RiskCell-only hex (no Claim rows -> no real centroid) should be reported,
    # not just vanish from the plan with no explanation.
    from src.db.models import RiskCell
    db_session.add(RiskCell(
        hex_id="hex_no_claims", forecast_date=datetime.utcnow(), hour=0,
        risk_score=0.9, model_version="ndu-v1",
    ))
    db_session.commit()

    plan = plan_routes(hour=0, db=db_session, depot_lat=-26.1, depot_lng=28.0, num_teams=1)
    assert "hex_no_claims" in plan.unlocatable_hexes


def test_dwell_time_counts_against_the_time_budget(db_session):
    # A single, very close stop: travel time is near-zero, so the time budget
    # is dominated by the 12-minute dwell. A budget shorter than the dwell
    # itself must drop the stop even though it's essentially free to reach.
    _make_claim(db_session, "hex_close", -26.1001, 28.0001, claim_number="close-0")

    plan = plan_routes(
        hour=0, db=db_session, depot_lat=-26.10, depot_lng=28.00,
        num_teams=1, fuel_budget_km=100, shift_window_minutes=5,  # < 12min dwell
    )
    visited = {s.hex_id for r in plan.routes for s in r.stops}
    assert "hex_close" not in visited
    assert "hex_close" in plan.dropped_hexes


def test_invalid_inputs_rejected(db_session):
    with pytest.raises(ValueError):
        plan_routes(hour=0, db=db_session, depot_lat=0, depot_lng=0, num_teams=0)
    with pytest.raises(ValueError):
        plan_routes(hour=0, db=db_session, depot_lat=0, depot_lng=0, fuel_budget_km=0)
    with pytest.raises(ValueError):
        plan_routes(hour=0, db=db_session, depot_lat=0, depot_lng=0, shift_window_minutes=0)


def test_endpoint_shape(client, db_session):
    for i in range(5):
        _make_claim(db_session, "hex_ep_route", -26.10, 28.05, claim_number=f"ep-{i}")

    res = client.post("/v1/routes/plan", json={
        "teams": 1, "shift_window_minutes": 240, "fuel_budget_km": 60,
        "depot_lat": -26.10, "depot_lng": 28.05, "hour": 0,
    })
    assert res.status_code == 200
    body = res.json()
    assert "routes" in body and isinstance(body["routes"], list)
    assert len(body["routes"]) == 1
    assert "dwell_minutes" in body
    assert body["dwell_minutes"] == 12


def test_endpoint_rejects_zero_teams(client, db_session):
    res = client.post("/v1/routes/plan", json={
        "teams": 0, "shift_window_minutes": 240, "fuel_budget_km": 60,
        "depot_lat": -26.10, "depot_lng": 28.05,
    })
    assert res.status_code == 422
