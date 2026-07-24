"""
Contract tests for POST /v1/sightings.
VUKA style: validate exact shapes, not just status codes.
Contract from docs/01-ARCHITECTURE.md §5.
"""
import pytest
from datetime import datetime


def test_health_check(client):
    """Sanity check: server responds."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert "websocket" in data


def test_create_sighting_minimal(client, sample_camera):
    """
    Test POST /v1/sightings with minimal valid payload.
    Contract: camera_id, ts, kind, modality, confidence required.
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "person",
        "modality": "yolo",
        "confidence": 0.87
    }
    
    response = client.post("/v1/sightings", json=payload)
    
    # Contract: 201 Created
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    
    data = response.json()
    
    # Contract: response shape
    assert "id" in data
    assert isinstance(data["id"], int)
    assert data["camera_id"] == sample_camera.id
    assert data["entity_id"] is None  # No plate/face, so no entity
    assert data["kind"] == "person"
    assert data["modality"] == "yolo"
    assert data["confidence"] == 0.87
    assert "ts" in data
    assert "created_at" in data


def test_create_sighting_with_plate(client, sample_camera):
    """
    Test sighting with plate creates/links entity.
    Contract: plate_text triggers entity resolution.
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "vehicle",
        "modality": "plate",
        "confidence": 0.92,
        "plate_text": "ABC123GP",
        "plate_quality": 0.95
    }
    
    response = client.post("/v1/sightings", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    
    # Contract: entity_id assigned
    assert data["entity_id"] is not None
    assert data["entity_id"].startswith("ent_")
    
    # Second sighting with same plate should link to same entity
    payload2 = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "vehicle",
        "modality": "plate",
        "confidence": 0.88,
        "plate_text": "ABC123GP"
    }
    
    response2 = client.post("/v1/sightings", json=payload2)
    assert response2.status_code == 201
    data2 = response2.json()
    
    # Contract: same entity_id
    assert data2["entity_id"] == data["entity_id"]


def test_create_sighting_plate_confusion_aware_match(client, sample_camera):
    """
    Test that an OCR-noisy plate reading resolves to the same entity as the
    original, not a new one — confusion-aware matching (docs/01 §3), ported
    into server/src/suspicion/entity_resolution.py after server/main.py (the
    original home of this logic, via brain/entity_resolution.py) was retired.
    "0" and "O" are OCR-confusable, so "CA0123456" and "CAO123456" must match.
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "vehicle",
        "modality": "plate",
        "confidence": 0.9,
        "plate_text": "CA0123456",
    }
    response = client.post("/v1/sightings", json=payload)
    assert response.status_code == 201
    entity_id = response.json()["entity_id"]
    assert entity_id is not None

    # Same plate, but OCR misread "0" as "O" this time
    payload2 = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "vehicle",
        "modality": "plate",
        "confidence": 0.9,
        "plate_text": "CAO123456",
    }
    response2 = client.post("/v1/sightings", json=payload2)
    assert response2.status_code == 201

    # Contract: OCR-confusable variant resolves to the SAME entity, not a new one
    assert response2.json()["entity_id"] == entity_id


def test_create_sighting_with_bbox(client, sample_camera):
    """
    Test sighting with bounding box.
    Contract: bbox is optional, stored as JSON.
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "person",
        "modality": "yolo",
        "confidence": 0.91,
        "bbox": {
            "x": 120.5,
            "y": 200.0,
            "w": 150.0,
            "h": 300.5
        }
    }
    
    response = client.post("/v1/sightings", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["kind"] == "person"


def test_create_sighting_unknown_camera_auto_registers(client):
    """
    Test sighting with a never-seen-before camera_id auto-registers it as a
    new sensor rather than failing — there is no separate registration
    endpoint, and rejecting an unseen node_id would silently drop every
    freshly-started vision/audio agent against a new DB.
    """
    payload = {
        "camera_id": "cam_nonexistent",
        "ts": datetime.utcnow().isoformat(),
        "kind": "person",
        "modality": "yolo",
        "confidence": 0.85
    }

    response = client.post("/v1/sightings", json=payload)

    assert response.status_code == 201
    assert response.json()["camera_id"] == "cam_nonexistent"


def test_create_sighting_missing_required_field(client, sample_camera):
    """
    Test sighting without required field fails.
    Contract: 422 for validation errors.
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        # Missing: kind, modality, confidence
    }
    
    response = client.post("/v1/sightings", json=payload)
    
    # Contract: 422 Unprocessable Entity
    assert response.status_code == 422


def test_create_sighting_invalid_confidence(client, sample_camera):
    """
    Test sighting with out-of-range confidence fails.
    Contract: confidence must be [0, 1].
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "person",
        "modality": "yolo",
        "confidence": 1.5  # Invalid: > 1.0
    }
    
    response = client.post("/v1/sightings", json=payload)
    
    # Contract: 422 validation error
    assert response.status_code == 422


def test_create_sightings_batch(client, sample_camera):
    """
    Test POST /v1/sightings/batch with multiple sightings.
    Contract: accepts array, returns created/skipped counts.
    """
    payload = {
        "sightings": [
            {
                "camera_id": sample_camera.id,
                "ts": datetime.utcnow().isoformat(),
                "kind": "person",
                "modality": "yolo",
                "confidence": 0.87
            },
            {
                "camera_id": sample_camera.id,
                "ts": datetime.utcnow().isoformat(),
                "kind": "vehicle",
                "modality": "plate",
                "confidence": 0.92,
                "plate_text": "XYZ789GP"
            },
            {
                "camera_id": "cam_nonexistent",  # auto-registers as a new sensor, not skipped
                "ts": datetime.utcnow().isoformat(),
                "kind": "person",
                "modality": "yolo",
                "confidence": 0.85
            }
        ]
    }

    response = client.post("/v1/sightings/batch", json=payload)

    assert response.status_code == 201
    data = response.json()

    # Contract: created/skipped counts. Unknown camera_id auto-registers as a
    # new sensor on first sighting (no separate registration endpoint exists
    # yet), so nothing here is skipped.
    assert "created" in data
    assert "skipped" in data
    assert data["created"] == 3
    assert data["skipped"] == 0


def test_sighting_response_fields(client, sample_camera):
    """
    Test that response includes all contract fields.
    Contract validation: exact shape check.
    """
    payload = {
        "camera_id": sample_camera.id,
        "ts": datetime.utcnow().isoformat(),
        "kind": "weapon",
        "modality": "yolo",
        "confidence": 0.78,
        "hex_id": "881f1d4a9ffffff"
    }
    
    response = client.post("/v1/sightings", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    
    # Contract: required response fields
    required_fields = [
        "id", "camera_id", "entity_id", "ts", "hex_id",
        "kind", "modality", "confidence", "created_at"
    ]
    
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Contract: types
    assert isinstance(data["id"], int)
    assert isinstance(data["camera_id"], str)
    assert isinstance(data["kind"], str)
    assert isinstance(data["modality"], str)
    assert isinstance(data["confidence"], float)
    assert data["hex_id"] == "881f1d4a9ffffff"
