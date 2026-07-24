"""
Contract tests for GET /v1/entities/{id} and POST /v1/entities/{id}/verify.
Tests lazy suspicion-score decay and human verification gate.
Contract from docs/01-ARCHITECTURE.md §5, ADR-0002.
"""
import pytest
from datetime import datetime, timedelta


def test_get_entity_with_decay(client, sample_camera, db_session):
    """
    Test GET /v1/entities/{id} computes lazy decay.
    Contract: score_now = base_score * 0.5^(days_elapsed/7)
    """
    from src.db.models import Entity
    
    # Create entity with base_score set 7 days ago (one half-life)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    entity = Entity(
        id="ent_test_001",
        kind="vehicle",
        plate_text="TEST123GP",
        base_score=1.0,
        last_updated=seven_days_ago,
        state="candidate",
        first_seen=seven_days_ago,
        last_seen=seven_days_ago,
        sighting_count=3
    )
    db_session.add(entity)
    db_session.commit()
    
    # Get entity via API
    response = client.get(f"/v1/entities/{entity.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Contract: response shape
    assert data["id"] == entity.id
    assert data["kind"] == "vehicle"
    assert data["plate_text"] == "TEST123GP"
    assert data["state"] == "candidate"
    assert data["base_score"] == 1.0
    
    # Contract: lazy decay (7 days = one half-life, score should be ~0.5)
    assert "current_score" in data
    assert 0.45 <= data["current_score"] <= 0.55  # Allow small floating point variance
    
    # Contract: metadata fields
    assert "first_seen" in data
    assert "last_seen" in data
    assert data["sighting_count"] == 3
    
    # Contract: factors and sightings
    assert "factors" in data
    assert "recent_sightings" in data
    assert isinstance(data["recent_sightings"], list)


def test_get_entity_no_decay(client, db_session):
    """
    Test entity with recent update has minimal decay.
    Contract: current_score ≈ base_score for recent updates.
    """
    from src.db.models import Entity
    
    # Create entity with recent update
    entity = Entity(
        id="ent_test_002",
        kind="person",
        base_score=0.8,
        last_updated=datetime.utcnow(),
        state="observed",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=1
    )
    db_session.add(entity)
    db_session.commit()
    
    response = client.get(f"/v1/entities/{entity.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    # Contract: minimal decay for recent update
    assert abs(data["current_score"] - data["base_score"]) < 0.01


def test_get_entity_not_found(client):
    """
    Test GET /v1/entities/{id} with non-existent entity.
    Contract: 404 Not Found.
    """
    response = client.get("/v1/entities/ent_nonexistent")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_verify_entity_flag(client, db_session):
    """
    Test POST /v1/entities/{id}/verify with action=flag.
    Contract: promotes to flagged, adds to watchlist, writes evidence.
    """
    from src.db.models import Entity, Watchlist, EvidenceChain
    
    # Create candidate entity
    entity = Entity(
        id="ent_test_003",
        kind="vehicle",
        plate_text="FLAG123GP",
        base_score=0.6,
        last_updated=datetime.utcnow(),
        state="candidate",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=4
    )
    db_session.add(entity)
    db_session.commit()
    
    # Verify with flag action
    verify_payload = {
        "action": "flag",
        "operator_id": "op_001",
        "note": "Suspicious behaviour confirmed"
    }
    
    response = client.post(f"/v1/entities/{entity.id}/verify", json=verify_payload)
    
    # Contract: 200 OK with status
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "flagged"
    assert data["entity_id"] == entity.id
    
    # Contract: entity state updated
    db_session.refresh(entity)
    assert entity.state == "flagged"
    
    # Contract: watchlist entry created
    watchlist_entry = db_session.query(Watchlist).filter(
        Watchlist.entity_id == entity.id
    ).first()
    assert watchlist_entry is not None
    assert watchlist_entry.verified_by == "op_001"
    assert watchlist_entry.active is True
    
    # Contract: evidence chain entry
    evidence = db_session.query(EvidenceChain).filter(
        EvidenceChain.target_id == entity.id,
        EvidenceChain.action == "verify_flag"
    ).first()
    assert evidence is not None
    assert evidence.actor_id == "op_001"


def test_verify_entity_dismiss(client, db_session):
    """
    Test POST /v1/entities/{id}/verify with action=dismiss.
    Contract: resets score, returns to observed state.
    """
    from src.db.models import Entity
    
    entity = Entity(
        id="ent_test_004",
        kind="vehicle",
        base_score=0.5,
        last_updated=datetime.utcnow(),
        state="candidate",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=2
    )
    db_session.add(entity)
    db_session.commit()
    
    verify_payload = {
        "action": "dismiss",
        "operator_id": "op_002",
        "note": "False positive"
    }
    
    response = client.post(f"/v1/entities/{entity.id}/verify", json=verify_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "dismissed"
    
    # Contract: score reset
    db_session.refresh(entity)
    assert entity.state == "observed"
    assert entity.base_score == 0.0


def test_verify_entity_whitelist(client, db_session):
    """
    Test POST /v1/entities/{id}/verify with action=whitelist.
    Contract: adds to whitelist, resets score, requires hex_id.
    """
    from src.db.models import Entity, Whitelist
    
    entity = Entity(
        id="ent_test_005",
        kind="vehicle",
        plate_text="WHITE123GP",
        base_score=0.4,
        last_updated=datetime.utcnow(),
        state="candidate",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=3
    )
    db_session.add(entity)
    db_session.commit()
    
    verify_payload = {
        "action": "whitelist",
        "operator_id": "op_003",
        "note": "Confirmed resident",
        "hex_id": "881f1d4a9ffffff"
    }
    
    response = client.post(f"/v1/entities/{entity.id}/verify", json=verify_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "whitelisted"
    assert data["hex_id"] == "881f1d4a9ffffff"
    
    # Contract: whitelist entry created
    whitelist_entry = db_session.query(Whitelist).filter(
        Whitelist.entity_id == entity.id
    ).first()
    assert whitelist_entry is not None
    assert whitelist_entry.hex_id == "881f1d4a9ffffff"
    assert whitelist_entry.added_by == "op_003"
    
    # Contract: score reset
    db_session.refresh(entity)
    assert entity.state == "observed"
    assert entity.base_score == 0.0


def test_verify_entity_whitelist_missing_hex(client, db_session):
    """
    Test whitelist action without hex_id fails.
    Contract: 400 Bad Request if hex_id missing.
    """
    from src.db.models import Entity
    
    entity = Entity(
        id="ent_test_006",
        kind="vehicle",
        base_score=0.3,
        last_updated=datetime.utcnow(),
        state="candidate",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=1
    )
    db_session.add(entity)
    db_session.commit()
    
    verify_payload = {
        "action": "whitelist",
        "operator_id": "op_004"
        # Missing hex_id
    }
    
    response = client.post(f"/v1/entities/{entity.id}/verify", json=verify_payload)
    
    # Contract: 400 Bad Request
    assert response.status_code == 400
    assert "hex_id required" in response.json()["detail"].lower()


def test_verify_entity_invalid_action(client, db_session):
    """
    Test verify with invalid action fails.
    Contract: 400 for invalid action.
    """
    from src.db.models import Entity
    
    entity = Entity(
        id="ent_test_007",
        kind="vehicle",
        base_score=0.2,
        last_updated=datetime.utcnow(),
        state="observed",
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        sighting_count=1
    )
    db_session.add(entity)
    db_session.commit()
    
    verify_payload = {
        "action": "invalid_action",
        "operator_id": "op_005"
    }
    
    response = client.post(f"/v1/entities/{entity.id}/verify", json=verify_payload)
    
    # Contract: 400 Bad Request
    assert response.status_code == 400
    assert "invalid action" in response.json()["detail"].lower()
