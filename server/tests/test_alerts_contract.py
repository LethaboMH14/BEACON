"""
Contract tests for alerts ack/cancel with cancel-window enforcement.
VUKA style: validate exact shapes and state machine.
Contract from docs/01-ARCHITECTURE.md §5, ADR-0002.

Uses conftest.py's shared db/client fixtures (StaticPool in-memory SQLite) —
local fixture copies were removed; they shadowed conftest with a broken pool
that gave the app thread an empty database.
"""
from datetime import datetime, timedelta

import pytest

from src.db.models import Camera, Entity


@pytest.fixture
def sample_camera(db_session):
    cam = Camera(
        id="cam_alert_001",
        name="Alert Test Camera",
        hex_id="881f1d4a9ffffff",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(cam)
    db_session.commit()
    return cam


@pytest.fixture
def sample_entity(db_session):
    ent = Entity(
        id="ent_alert_001",
        kind="vehicle",
        plate_text="ALERT01",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    db_session.add(ent)
    db_session.commit()
    return ent


def test_create_alert_minimal(client, sample_entity):
    """POST /v1/alerts creates alert with cancel window."""
    payload = {
        "alert_type": "entity_flagged",
        "recipient_id": "op_001",
        "recipient_type": "ops",
        "message": "Entity flagged for suspicious behaviour",
        "severity": "high",
        "entity_id": "ent_alert_001",
        "camera_id": "cam_alert_001",
    }

    response = client.post("/v1/alerts", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["alert_type"] == "entity_flagged"
    assert data["recipient_id"] == "op_001"
    assert data["status"] == "pending"
    assert "cancel_window_expires" in data
    assert data["cancel_window_expires"] is not None


def test_ack_alert(client, sample_entity):
    """POST /v1/alerts/{id}/ack acknowledges and writes evidence."""
    # Create alert first
    create_payload = {
        "alert_type": "hard_trigger",
        "recipient_id": "op_002",
        "recipient_type": "ops",
        "message": "Panic button pressed",
        "severity": "critical",
        "camera_id": "cam_alert_001",
    }
    create_resp = client.post("/v1/alerts", json=create_payload)
    alert_id = create_resp.json()["id"]

    # Ack it
    ack_payload = {"operator_id": "op_002", "note": "On scene, false alarm"}
    ack_resp = client.post(f"/v1/alerts/{alert_id}/ack", json=ack_payload)

    assert ack_resp.status_code == 200
    data = ack_resp.json()
    assert data["status"] == "acked"
    assert data["acked_by"] == "op_002"


def test_cancel_alert_within_window(client, sample_entity):
    """Cancel succeeds when within the 30s window."""
    create_payload = {
        "alert_type": "forecast_spike",
        "recipient_id": "op_003",
        "recipient_type": "ops",
        "message": "Risk spike predicted",
        "severity": "medium",
    }
    create_resp = client.post("/v1/alerts", json=create_payload)
    alert_id = create_resp.json()["id"]

    cancel_payload = {"operator_id": "op_003", "reason": "Duplicate"}
    cancel_resp = client.post(f"/v1/alerts/{alert_id}/cancel", json=cancel_payload)

    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["status"] == "cancelled"


def test_cancel_alert_after_window_rejected(client, sample_entity, db_session):
    """
    Cancel rejected after window expires.
    We manually set cancel_window_expires to the past to simulate expiry.
    """
    from src.db.models import Alert

    # Create alert
    create_payload = {
        "alert_type": "suspicious_activity",
        "recipient_id": "op_004",
        "recipient_type": "ops",
        "message": "Suspicious vehicle",
        "severity": "low",
    }
    create_resp = client.post("/v1/alerts", json=create_payload)
    alert_id = create_resp.json()["id"]

    # Manually expire the cancel window in DB
    alert = db_session.query(Alert).filter(Alert.id == alert_id).first()
    alert.cancel_window_expires = datetime.utcnow() - timedelta(seconds=10)
    db_session.commit()

    # Try to cancel
    cancel_payload = {"operator_id": "op_004", "reason": "Too late"}
    cancel_resp = client.post(f"/v1/alerts/{alert_id}/cancel", json=cancel_payload)

    # Contract: 409 Conflict — cancel window expired
    assert cancel_resp.status_code == 409
    assert "expired" in cancel_resp.json()["detail"].lower()


def test_cancel_already_acked_rejected(client, sample_entity):
    """Cannot cancel an already-acked alert."""
    create_payload = {
        "alert_type": "entity_flagged",
        "recipient_id": "op_005",
        "recipient_type": "ops",
        "message": "Flagged entity",
        "severity": "high",
    }
    create_resp = client.post("/v1/alerts", json=create_payload)
    alert_id = create_resp.json()["id"]

    # Ack first
    client.post(f"/v1/alerts/{alert_id}/ack", json={"operator_id": "op_005"})

    # Try to cancel
    cancel_resp = client.post(f"/v1/alerts/{alert_id}/cancel", json={"operator_id": "op_005"})

    # Contract: 409 Conflict — already in terminal state
    assert cancel_resp.status_code == 409


def test_alert_not_found(client):
    """Ack/cancel on non-existent alert returns 404."""
    ack_resp = client.post("/v1/alerts/nonexistent/ack", json={"operator_id": "op_x"})
    cancel_resp = client.post("/v1/alerts/nonexistent/cancel", json={"operator_id": "op_x"})

    assert ack_resp.status_code == 404
    assert cancel_resp.status_code == 404


def test_alert_create_with_invalid_entity(client):
    """Alert with non-existent entity_id fails."""
    payload = {
        "alert_type": "entity_flagged",
        "recipient_id": "op_006",
        "recipient_type": "ops",
        "message": "Test",
        "severity": "medium",
        "entity_id": "ent_nonexistent",
    }

    response = client.post("/v1/alerts", json=payload)
    assert response.status_code == 404
