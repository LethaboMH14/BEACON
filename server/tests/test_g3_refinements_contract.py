"""
Contract tests for the team/SBU.md G3 refinement backlog (2026-07-25):
route persistence, GET /v1/incidents/{id}/report, GET /v1/events/since,
GET /v1/cameras camera health.
"""
from datetime import datetime, timedelta

from src.db.models import Camera, Sighting, Entity, Incident, Alert, Route


def _make_claim_hex(db, hex_id, lat, lng, n=6):
    from src.db.models import Claim
    for i in range(n):
        db.add(Claim(
            claim_number=f"g3-{hex_id}-{i}", claim_type="Theft", suburb="Test",
            hex_id=hex_id, lat=lat, lng=lng,
            claim_date=datetime.utcnow() - timedelta(days=10), hour=0, hour_known=True,
            amount=8000.0,
        ))
    db.commit()


def test_routes_plan_persists_a_route_row_per_team(client, db_session):
    _make_claim_hex(db_session, "hex_rt_persist", -26.10, 28.05)
    res = client.post("/v1/routes/plan", json={
        "teams": 1, "shift_window_minutes": 240, "fuel_budget_km": 60,
        "depot_lat": -26.10, "depot_lng": 28.05, "hour": 0,
    })
    assert res.status_code == 200
    rows = db_session.query(Route).all()
    assert len(rows) == 1
    assert rows[0].status == "planned"
    assert rows[0].fuel_budget == 60


def test_incident_report_bundles_entity_sightings_alerts_evidence(client, db_session):
    camera = Camera(id="cam_rep", name="Report Cam", hex_id="hex_rep")
    db_session.add(camera)
    entity = Entity(id="ent_rep", kind="vehicle", plate_text="REP123GP")
    db_session.add(entity)
    db_session.commit()

    db_session.add(Sighting(
        camera_id="cam_rep", entity_id="ent_rep", ts=datetime.utcnow(),
        hex_id="hex_rep", kind="vehicle", modality="plate", confidence=0.9,
    ))
    incident = Incident(
        id="inc_rep", incident_type="suspicious", hex_id="hex_rep",
        occurred_at=datetime.utcnow(), severity="high", related_entity_id="ent_rep",
    )
    db_session.add(incident)
    db_session.add(Alert(
        id="alrt_rep", alert_type="entity_flagged", recipient_id="ops",
        recipient_type="ops", entity_id="ent_rep", incident_id="inc_rep",
        message="test", severity="high", status="pending", created_at=datetime.utcnow(),
    ))
    db_session.commit()

    res = client.get("/v1/incidents/inc_rep/report")
    assert res.status_code == 200
    body = res.json()
    assert body["entity_id"] == "ent_rep"
    assert len(body["sightings"]) == 1
    assert len(body["alerts"]) == 1


def test_incident_report_404_for_unknown_incident(client, db_session):
    res = client.get("/v1/incidents/inc_nope/report")
    assert res.status_code == 404


def test_events_since_returns_only_events_after_the_given_ts(client, db_session):
    cutoff = datetime.utcnow()
    camera = Camera(id="cam_ev", name="Event Cam")
    db_session.add(camera)
    db_session.commit()
    db_session.add(Sighting(
        camera_id="cam_ev", ts=datetime.utcnow(), hex_id="hex_ev",
        kind="vehicle", modality="yolo", confidence=0.8,
        created_at=datetime.utcnow() + timedelta(seconds=1),
    ))
    db_session.commit()

    res = client.get("/v1/events/since", params={"ts": cutoff.isoformat()})
    assert res.status_code == 200
    body = res.json()
    assert any(e["event"] == "sighting.new" for e in body["events"])

    res2 = client.get("/v1/events/since", params={"ts": (datetime.utcnow() + timedelta(hours=1)).isoformat()})
    assert res2.json()["events"] == []


def test_cameras_health_online_vs_offline(client, db_session):
    db_session.add(Camera(id="cam_online", name="Online", last_seen_at=datetime.utcnow()))
    db_session.add(Camera(id="cam_offline", name="Offline", last_seen_at=datetime.utcnow() - timedelta(minutes=10)))
    db_session.add(Camera(id="cam_never", name="Never seen", last_seen_at=None))
    db_session.commit()

    res = client.get("/v1/cameras")
    assert res.status_code == 200
    by_id = {c["id"]: c for c in res.json()["cameras"]}
    assert by_id["cam_online"]["online"] is True
    assert by_id["cam_offline"]["online"] is False
    assert by_id["cam_never"]["online"] is False


def test_sighting_ingest_bumps_camera_last_seen_at(client, db_session):
    db_session.add(Camera(id="cam_bump", name="Bump Cam", last_seen_at=None))
    db_session.commit()

    res = client.post("/v1/sightings", json={
        "camera_id": "cam_bump", "ts": datetime.utcnow().isoformat(),
        "hex_id": "hex_bump", "kind": "vehicle", "modality": "yolo", "confidence": 0.7,
    })
    assert res.status_code == 201

    cam = db_session.query(Camera).filter(Camera.id == "cam_bump").first()
    db_session.refresh(cam)
    assert cam.last_seen_at is not None
