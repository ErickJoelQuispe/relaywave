"""In-memory WebSocket connection registry, keyed by room.

Single-instance only: Phase 1 runs one API process, so a plain in-process
dict is enough to fan messages out to everyone connected to a room. Phase 2
replaces this with Redis Pub/Sub so multiple API instances can share room
membership (see the roadmap / ADR-004).
"""

from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)

    def connect(self, room_id: int, websocket: WebSocket) -> None:
        self._rooms[room_id].add(websocket)

    def disconnect(self, room_id: int, websocket: WebSocket) -> None:
        self._rooms[room_id].discard(websocket)
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    async def broadcast(
        self, room_id: int, message: str, *, exclude: WebSocket | None = None
    ) -> None:
        """Send `message` to every connection in `room_id` except `exclude`.

        A connection whose send fails (the client is gone but we haven't
        processed its disconnect yet) is dropped instead of raised — one
        dead socket must never break delivery to the rest of the room.
        """
        dead: list[WebSocket] = []
        for connection in self._rooms.get(room_id, set()):
            if connection is exclude:
                continue
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(room_id, connection)


# Module-level singleton: one registry per process, matching the
# single-instance Phase 1 deployment model.
manager = ConnectionManager()
