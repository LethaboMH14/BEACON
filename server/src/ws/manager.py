"""
WebSocket connection manager.
Fan-out budget: ≤300 ms server-side (CLAUDE.md §6).

Rooms:
- ops:    security operators — receive all events
- member: guardians/residents — receive alert.new for own cameras only

G1 additions:
- member connections carry a member_id and a set of camera_ids.
- broadcast_alert_to_member() delivers only to connections whose
  registered cameras intersect the alert's camera_id.
"""
import asyncio
from typing import Dict, Optional, Set

from fastapi import WebSocket


class _MemberConn:
    """Metadata kept per member WebSocket connection."""
    __slots__ = ("websocket", "member_id", "camera_ids")

    def __init__(self, websocket: WebSocket, member_id: str, camera_ids: Set[str]):
        self.websocket  = websocket
        self.member_id  = member_id
        self.camera_ids = camera_ids   # cameras this member owns


class ConnectionManager:
    """Manage WebSocket connections with room-based routing."""

    def __init__(self) -> None:
        # ops room: plain set of websockets
        self._ops: Set[WebSocket] = set()
        # member room: websocket → _MemberConn
        self._members: Dict[WebSocket, _MemberConn] = {}

    # ── connection lifecycle ──────────────────────────────────────────────

    async def connect_ops(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._ops.add(websocket)

    async def connect_member(
        self,
        websocket: WebSocket,
        member_id: str,
        camera_ids: Optional[Set[str]] = None,
    ) -> None:
        await websocket.accept()
        self._members[websocket] = _MemberConn(
            websocket=websocket,
            member_id=member_id,
            camera_ids=camera_ids or set(),
        )

    def register_member_cameras(self, websocket: WebSocket, camera_ids: Set[str]) -> None:
        """
        Add cameras to an existing member connection (sent after connect via
        a 'register_cameras' message so the member doesn't have to pass them
        in the query string).
        """
        conn = self._members.get(websocket)
        if conn:
            conn.camera_ids.update(camera_ids)

    def disconnect(self, websocket: WebSocket) -> None:
        self._ops.discard(websocket)
        self._members.pop(websocket, None)

    # ── sending helpers ───────────────────────────────────────────────────

    async def send_personal(self, message: dict, websocket: WebSocket) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

    async def _fan_out(self, message: dict, websockets) -> None:
        """Send to a collection of websockets concurrently."""
        if not websockets:
            return
        dead: list[WebSocket] = []
        tasks = []
        for ws in list(websockets):
            try:
                tasks.append(ws.send_json(message))
            except Exception:
                dead.append(ws)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for ws in dead:
            self.disconnect(ws)

    # ── broadcast methods ─────────────────────────────────────────────────

    async def broadcast_to_ops(self, message: dict) -> None:
        """Broadcast to all ops connections."""
        await self._fan_out(message, self._ops)

    async def broadcast_to_all_members(self, message: dict) -> None:
        """Broadcast to every member connection (unfiltered)."""
        await self._fan_out(message, list(self._members.keys()))

    async def broadcast_alert_to_member(
        self,
        message: dict,
        camera_id: Optional[str],
    ) -> None:
        """
        Deliver alert.new only to member connections that own camera_id.
        If camera_id is None (unlikely for a real alert), fall back to
        broadcasting to all members.
        """
        if not camera_id:
            await self.broadcast_to_all_members(message)
            return

        targets = [
            conn.websocket
            for conn in self._members.values()
            if camera_id in conn.camera_ids
        ]
        await self._fan_out(message, targets)

    # ── stat helpers ──────────────────────────────────────────────────────

    def get_room_count(self, room: str) -> int:
        if room == "ops":
            return len(self._ops)
        if room == "member":
            return len(self._members)
        return 0

    # Kept for backwards compat with G0 tests
    async def broadcast_to_members(self, message: dict) -> None:
        await self.broadcast_to_all_members(message)

    # Kept for backwards compat with G0 conftest (connect() called with room=)
    async def connect(self, websocket: WebSocket, room: str = "ops") -> None:
        if room == "member":
            await self.connect_member(websocket, member_id="unknown")
        else:
            await self.connect_ops(websocket)


# Global singleton
ws_manager = ConnectionManager()
