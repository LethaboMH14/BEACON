"""
Contract tests for WebSocket endpoints.
VUKA style: test connection, echo, event delivery.
Contract from docs/01-ARCHITECTURE.md §5.
"""
import pytest
import json
from datetime import datetime


def test_websocket_ops_connection(client):
    """
    Test /ws/ops connection and welcome message.
    Contract: accepts connection, sends connected event.
    """
    with client.websocket_connect("/ws/ops") as websocket:
        # Contract: receive welcome message
        data = websocket.receive_json()
        
        assert data["event"] == "connected"
        assert data["data"]["room"] == "ops"
        assert "message" in data["data"]


def test_websocket_ops_echo(client):
    """
    Test /ws/ops echo functionality (G0).
    Contract: echo back sent messages.
    """
    with client.websocket_connect("/ws/ops") as websocket:
        # Receive welcome
        websocket.receive_json()
        
        # Send test message
        test_message = {
            "action": "test",
            "payload": {"value": 123}
        }
        websocket.send_text(json.dumps(test_message))
        
        # Contract: receive echo
        response = websocket.receive_json()
        assert response["event"] == "echo"
        assert response["data"]["action"] == "test"
        assert response["data"]["payload"]["value"] == 123


def test_websocket_member_connection(client):
    """
    Test /ws/member connection with member_id.
    Contract: requires member_id query param.
    """
    member_id = "member_001"
    
    with client.websocket_connect(f"/ws/member?member_id={member_id}") as websocket:
        # Contract: receive welcome message with member_id
        data = websocket.receive_json()
        
        assert data["event"] == "connected"
        assert data["data"]["room"] == "member"
        assert data["data"]["member_id"] == member_id


def test_websocket_member_echo(client):
    """
    Test /ws/member echo functionality.
    Contract: echo back sent messages.
    """
    with client.websocket_connect("/ws/member?member_id=member_002") as websocket:
        # Receive welcome
        websocket.receive_json()
        
        # Send test message
        test_message = {
            "action": "arm_camera",
            "camera_id": "cam_001"
        }
        websocket.send_text(json.dumps(test_message))
        
        # Contract: receive echo
        response = websocket.receive_json()
        assert response["event"] == "echo"
        assert response["data"]["action"] == "arm_camera"


def test_websocket_status_endpoint(client):
    """
    Test GET /ws/status shows connection counts.
    Contract: returns ops/member/total connection counts.
    """
    response = client.get("/ws/status")
    
    assert response.status_code == 200
    data = response.json()
    
    # Contract: required fields
    assert "ops_connections" in data
    assert "member_connections" in data
    assert "total_connections" in data
    
    # Contract: types
    assert isinstance(data["ops_connections"], int)
    assert isinstance(data["member_connections"], int)
    assert isinstance(data["total_connections"], int)
    
    # Should be zero with no active connections
    assert data["ops_connections"] >= 0
    assert data["member_connections"] >= 0


def test_websocket_sighting_event_delivery(client, sample_camera):
    """
    Test that POST /v1/sightings triggers WebSocket event.
    Contract: sighting.new event delivered to ops room.
    """
    with client.websocket_connect("/ws/ops") as websocket:
        # Receive welcome and clear it
        websocket.receive_json()
        
        # Create a sighting via API
        payload = {
            "camera_id": sample_camera.id,
            "ts": datetime.utcnow().isoformat(),
            "kind": "person",
            "modality": "yolo",
            "confidence": 0.89
        }
        
        response = client.post("/v1/sightings", json=payload)
        assert response.status_code == 201
        
        # Contract: receive sighting.new event on WebSocket
        event = websocket.receive_json()
        
        assert event["event"] == "sighting.new"
        assert "data" in event
        assert event["data"]["camera_id"] == sample_camera.id
        assert event["data"]["kind"] == "person"
        assert event["data"]["confidence"] == 0.89
        assert "id" in event["data"]
        assert "ts" in event["data"]


def test_websocket_batch_event_delivery(client, sample_camera):
    """
    Test that batch sightings trigger WebSocket event.
    Contract: sighting.batch event with count and camera_ids.
    """
    with client.websocket_connect("/ws/ops") as websocket:
        # Receive welcome and clear it
        websocket.receive_json()
        
        # Create batch via API
        payload = {
            "sightings": [
                {
                    "camera_id": sample_camera.id,
                    "ts": datetime.utcnow().isoformat(),
                    "kind": "person",
                    "modality": "yolo",
                    "confidence": 0.85
                },
                {
                    "camera_id": sample_camera.id,
                    "ts": datetime.utcnow().isoformat(),
                    "kind": "vehicle",
                    "modality": "yolo",
                    "confidence": 0.91
                }
            ]
        }
        
        response = client.post("/v1/sightings/batch", json=payload)
        assert response.status_code == 201
        
        # Contract: receive sighting.batch event
        event = websocket.receive_json()
        
        assert event["event"] == "sighting.batch"
        assert event["data"]["count"] == 2
        assert sample_camera.id in event["data"]["camera_ids"]


def test_websocket_multiple_connections(client):
    """
    Test multiple simultaneous WebSocket connections.
    Contract: manager handles multiple connections per room.
    """
    with client.websocket_connect("/ws/ops") as ws1:
        with client.websocket_connect("/ws/ops") as ws2:
            # Both receive welcome
            data1 = ws1.receive_json()
            data2 = ws2.receive_json()
            
            assert data1["event"] == "connected"
            assert data2["event"] == "connected"
            
            # Status should show 2 ops connections
            status_response = client.get("/ws/status")
            status = status_response.json()
            assert status["ops_connections"] == 2
