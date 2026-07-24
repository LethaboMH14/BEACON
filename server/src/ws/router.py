"""
WebSocket endpoints.
/ws/ops    — ops console (all events)
/ws/member — member/guardian view (filtered to own cameras)

Contract from docs/01-ARCHITECTURE.md §5.
G1: member connections register their camera_ids after connect so alerts
    are only delivered for cameras they own.
"""
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .manager import ws_manager

router = APIRouter()


@router.websocket("/ws/ops")
async def websocket_ops(websocket: WebSocket) -> None:
    """
    Ops console — security operators.
    Events: sighting.new, entity.candidate, entity.flagged,
            alert.new, alert.acked, alert.cancelled,
            route.updated, forecast.updated
    """
    await ws_manager.connect_ops(websocket)

    try:
        await ws_manager.send_personal(
            {"event": "connected", "data": {"room": "ops", "message": "Connected to BEACON ops channel"}},
            websocket,
        )

        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)

            # Echo for testing / heartbeat
            await ws_manager.send_personal({"event": "echo", "data": message}, websocket)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"[ws/ops] error: {e}")
        ws_manager.disconnect(websocket)


@router.websocket("/ws/member")
async def websocket_member(
    websocket: WebSocket,
    member_id: str = Query(..., description="Member/guardian ID"),
) -> None:
    """
    Member/guardian view — filtered to own cameras.

    After connecting, the client sends a register_cameras message to declare
    which cameras belong to them:

        {"action": "register_cameras", "camera_ids": ["cam_001", "cam_002"]}

    After registration, alert.new events are only delivered when the alert's
    camera_id is in the registered set.

    Supported actions from client:
        register_cameras  — declare owned camera_ids
        guardian_request  — panic / request guardian response; forwarded to ops
    """
    await ws_manager.connect_member(websocket, member_id=member_id)

    try:
        await ws_manager.send_personal(
            {
                "event": "connected",
                "data": {
                    "room": "member",
                    "member_id": member_id,
                    "message": "Connected to BEACON member channel. Send register_cameras to receive filtered alerts.",
                },
            },
            websocket,
        )

        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            action = message.get("action", "")

            if action == "register_cameras":
                # Client declares which cameras it owns
                camera_ids = set(message.get("camera_ids", []))
                ws_manager.register_member_cameras(websocket, camera_ids)
                await ws_manager.send_personal(
                    {
                        "event": "cameras_registered",
                        "data": {"camera_ids": list(camera_ids)},
                    },
                    websocket,
                )

            elif action == "guardian_request":
                # Member triggered panic / guardian confirm — forward to ops
                await ws_manager.broadcast_to_ops(
                    {
                        "event": "guardian.request",
                        "data": {
                            "member_id": member_id,
                            "camera_id": message.get("camera_id"),
                            "note": message.get("note"),
                        },
                    }
                )
                # Confirm receipt to member
                await ws_manager.send_personal(
                    {"event": "guardian_request_sent", "data": {"member_id": member_id}},
                    websocket,
                )

            else:
                # Echo unknown messages for debugging
                await ws_manager.send_personal({"event": "echo", "data": message}, websocket)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"[ws/member] error: {e}")
        ws_manager.disconnect(websocket)


@router.get("/ws/status")
async def websocket_status() -> dict:
    """Connection statistics."""
    return {
        "ops_connections": ws_manager.get_room_count("ops"),
        "member_connections": ws_manager.get_room_count("member"),
        "total_connections": ws_manager.get_room_count("ops") + ws_manager.get_room_count("member"),
    }
