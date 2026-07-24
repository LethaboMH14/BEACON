"""
WebSocket connection manager.
Fan-out budget: ≤300ms server-side (CLAUDE.md §6).

Rooms:
- ops: security operators (all events)
- member: guardians/members (own cameras only, filtered)
"""
from typing import Dict, Set, List
from fastapi import WebSocket
import json
import asyncio


class ConnectionManager:
    """Manage WebSocket connections with room-based routing."""
    
    def __init__(self):
        # room_name → set of websocket connections
        self.rooms: Dict[str, Set[WebSocket]] = {
            "ops": set(),
            "member": set()
        }
        # websocket → room mapping for cleanup
        self.ws_to_room: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, room: str = "ops"):
        """Accept a WebSocket connection and assign to room."""
        await websocket.accept()
        
        if room not in self.rooms:
            self.rooms[room] = set()
        
        self.rooms[room].add(websocket)
        self.ws_to_room[websocket] = room
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        room = self.ws_to_room.get(websocket)
        if room and websocket in self.rooms.get(room, set()):
            self.rooms[room].remove(websocket)
        if websocket in self.ws_to_room:
            del self.ws_to_room[websocket]
    
    async def send_personal(self, message: dict, websocket: WebSocket):
        """Send message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Error sending to websocket: {e}")
            self.disconnect(websocket)
    
    async def broadcast_to_room(self, message: dict, room: str):
        """
        Broadcast message to all connections in a room.
        Fan-out budget: ≤300ms.
        """
        if room not in self.rooms:
            return
        
        # Gather all send tasks
        tasks = []
        dead_connections = []
        
        for websocket in self.rooms[room]:
            try:
                tasks.append(websocket.send_json(message))
            except Exception:
                dead_connections.append(websocket)
        
        # Execute all sends concurrently (fan-out)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)
    
    async def broadcast_to_ops(self, message: dict):
        """Broadcast to ops room (security operators)."""
        await self.broadcast_to_room(message, "ops")
    
    async def broadcast_to_members(self, message: dict):
        """Broadcast to member room (guardians/residents)."""
        await self.broadcast_to_room(message, "member")
    
    def get_room_count(self, room: str) -> int:
        """Get number of connections in a room."""
        return len(self.rooms.get(room, set()))


# Global manager instance
ws_manager = ConnectionManager()
