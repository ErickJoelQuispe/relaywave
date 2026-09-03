"""In-memory WebSocket connection registry, keyed by room.

Single-instance only: Phase 1 runs one API process, so a plain in-process
dict is enough to fan messages out to everyone connected to a room. Phase 2
adds Redis Pub/Sub (see app/ws/broadcaster.py) so multiple API instances can
share room membership — this registry stays the LOCAL half of that: it still
only knows about sockets held by its own process, and now also tracks
per-room local connection counts so a caller can tell when a room goes from
zero to one local socket (subscribe to Redis) or one to zero (unsubscribe).

Each local socket is also mapped to the `user_id` that authenticated it.
That mapping exists for one reason: once a broadcast has round-tripped
through Redis (see `_on_redis_message` in app/api/routes/ws.py), the sender
is identified only by the `user_id` embedded in the message payload, not by
a `WebSocket` object — the object that originally sent the message lives on
whatever pod received it, and delivery on THIS pod is driven purely by what
Redis handed back. Excluding "the sender's own socket" therefore has to mean
"every local socket owned by that user_id", not "one specific object".
"""

from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, dict[WebSocket, int]] = defaultdict(dict)

    def connect(self, room_id: int, websocket: WebSocket, user_id: int) -> bool:
        """Register `websocket` under `room_id`, owned by `user_id`.

        Returns `True` if this is the first local connection for `room_id`
        on this process (a caller should subscribe to that room's Redis
        channel), `False` if other local sockets were already in the room.
        """
        is_first = room_id not in self._rooms
        self._rooms[room_id][websocket] = user_id
        return is_first

    def disconnect(self, room_id: int, websocket: WebSocket) -> bool:
        """Remove `websocket` (and its user_id mapping) from `room_id`.

        Returns `True` if this was the last local connection for `room_id`
        on this process (a caller should unsubscribe from that room's Redis
        channel), `False` if other local sockets remain in the room.
        """
        self._rooms[room_id].pop(websocket, None)
        if not self._rooms[room_id]:
            del self._rooms[room_id]
            return True
        return False

    async def broadcast(
        self,
        room_id: int,
        message: str,
        *,
        exclude: WebSocket | None = None,
        exclude_user_id: int | None = None,
    ) -> None:
        """Send `message` to every connection in `room_id`, minus exclusions.

        `exclude` skips one specific socket object — useful when the caller
        still holds the sending connection directly (a purely local
        broadcast). `exclude_user_id` skips every local socket owned by that
        user, regardless of which specific connection (or tab) it is —
        needed once a message has gone through Redis and only the sender's
        `user_id`, not their socket object, survived the round trip. Both
        can be combined; either, neither, or both may apply to a given call.
        """
        dead: list[WebSocket] = []
        for connection, owner_id in self._rooms.get(room_id, {}).items():
            if connection is exclude:
                continue
            if exclude_user_id is not None and owner_id == exclude_user_id:
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
