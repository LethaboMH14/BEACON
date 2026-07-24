"""
WebSocket endpoints.
/ws/ops — ops console (all events)
/ws/member — member/guardian view (filtered)

Contract from docs/01-ARCHITECTURE.md §5.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from .manager import ws_manager
import json

router = APIRouter()


@router.websocket("/ws/ops")
async def websocket_ops(websocket: WebSocket):
    """
    WebSocket endpoint for ops console (security operators).
    
    Events: sighting.new, entity.candidate, entity.flagged, alert.new,
            route.updated, forecast.updated
    """
    await ws_manager.connect(websocket, room="ops")
    
    try:
        # Send welcome message
        await ws_manager.send_personal({
            "event": "connected",
            "data": {
                "room": "ops",
                "message": "Connected to BEACON ops channel"
            }
        }, websocket)
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            
            # Echo for G0 testing
            message = json.loads(data)
            await ws_manager.send_personal({
                "event": "echo",
                "data": message
            }, websocket)
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


@router.websocket("/ws/member")
async def websocket_member(
    websocket: WebSocket,
    member_id: str = Query(..., description="Member/guardian ID for filtering")
):
    """
    WebSocket endpoint for member/guardian view.
    
    Events filtered to own cameras only.
    Events: alert.new (own cameras), guardian.request
    """
    await ws_manager.connect(websocket, room="member")
    
    try:
        # Send welcome message
        await ws_manager.send_personal({
            "event": "connected",
            "data": {
                "room": "member",
                "member_id": member_id,
                "message": "Connected to BEACON member channel"
            }
        }, websocket)
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            
            # Handle member actions (arm camera, guardian confirm, etc.)
            message = json.loads(data)
            
            # Echo for now (G1 will add proper action handlers)
            await ws_manager.send_personal({
                "event": "echo",
                "data": message
            }, websocket)
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection statistics."""
    return {
        "ops_connections": ws_manager.get_room_count("ops"),
        "member_connections": ws_manager.get_room_count("member"),
        "total_connections": (
            ws_manager.get_room_count("ops") + 
            ws_manager.get_room_count("member")
        )
    }
