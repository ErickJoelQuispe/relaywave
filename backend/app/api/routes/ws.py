"""Real-time room WebSocket: chat messages, typing, and presence.

Auth cannot ride an `Authorization` header (the WebSocket handshake gives
browsers no way to set one), and a `?token=` query param would leak a live
access token into proxy/access logs. So the client connects unauthenticated
and the FIRST frame must be `{"type": "auth", "token": "..."}`; the
connection is closed if that doesn't arrive, validate, or match a real user.
"""

import asyncio
import json
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.core.security import decode_token
from app.db.session import get_db
from app.models.message import Message
from app.models.room_membership import RoomMembership
from app.models.user import User
from app.schemas.message import (
    ClientEnvelope,
    MessageBroadcast,
    PresenceBroadcast,
    TypingBroadcast,
)
from app.ws.broadcaster import RoomBroadcaster
from app.ws.manager import manager

router = APIRouter(tags=["websocket"])

_AUTH_TIMEOUT_SECONDS = 5.0
_envelope_adapter: TypeAdapter[ClientEnvelope] = TypeAdapter(ClientEnvelope)


async def _on_redis_message(room_id: int, data: str) -> None:
    """Forward a Redis-delivered message to this process's local sockets.

    This is the other half of `broadcaster.publish()`: local delivery for
    chat messages, typing, and presence all happen exclusively here, driven
    by Redis — including for the pod that published the payload. That round
    trip is what makes the sender's own message echo (see the self-echo
    note in app/ws/broadcaster.py) genuinely cross-pod instead of a local
    shortcut.

    Typing is the one exception to "deliver to everyone": a user must never
    see their own "user is typing" indicator, but by the time this callback
    runs, the `WebSocket` object that originally sent it is gone — it lives
    on whichever pod handled that connection, and this callback only has
    `data` from Redis. The fix is to exclude by `user_id`, which the
    payload carries, instead of by socket object (see
    `ConnectionManager.broadcast`'s `exclude_user_id` parameter). Messages
    and presence events carry no such exclusion — everyone in the room,
    including the acting user's other tabs, sees them.
    """
    payload = json.loads(data)
    if payload.get("type") == "typing":
        await manager.broadcast(room_id, data, exclude_user_id=payload["user_id"])
    else:
        await manager.broadcast(room_id, data)


broadcaster = RoomBroadcaster(redis_client, _on_redis_message)

# Codes 4000-4999 are reserved for application use by the WebSocket spec.
# Mirroring HTTP semantics makes the client's close handler easy to reason
# about: 4401 ~ 401 Unauthorized, 4403 ~ 403 Forbidden.
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403


async def _authenticate(websocket: WebSocket, db: AsyncSession) -> User | None:
    """Consume the mandatory first frame and resolve it to a `User`.

    Closes the socket and returns `None` on any failure. This deliberately
    duplicates `deps.get_current_user`'s token checks rather than reusing it:
    that dependency is built around an HTTP `Authorization` header, not a
    WebSocket frame.
    """
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=_AUTH_TIMEOUT_SECONDS
        )
    except (TimeoutError, WebSocketDisconnect):
        await websocket.close(code=WS_UNAUTHORIZED, reason="Authentication timeout")
        return None

    try:
        envelope = _envelope_adapter.validate_json(raw)
    except ValidationError:
        await websocket.close(code=WS_UNAUTHORIZED, reason="Expected auth message")
        return None

    if envelope.type != "auth":
        await websocket.close(code=WS_UNAUTHORIZED, reason="Expected auth message")
        return None

    try:
        payload = decode_token(envelope.token)
    except jwt.PyJWTError:
        await websocket.close(code=WS_UNAUTHORIZED, reason="Invalid or expired token")
        return None

    if payload.get("type") != "access":
        await websocket.close(code=WS_UNAUTHORIZED, reason="Invalid token type")
        return None

    user = await db.get(User, int(payload["sub"]))
    if user is None:
        await websocket.close(code=WS_UNAUTHORIZED, reason="User not found")
        return None
    return user


@router.websocket("/ws/rooms/{room_id}")
async def room_websocket(
    websocket: WebSocket,
    room_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await websocket.accept()

    user = await _authenticate(websocket, db)
    if user is None:
        return

    is_member = await db.scalar(
        select(RoomMembership).where(
            RoomMembership.room_id == room_id,
            RoomMembership.user_id == user.id,
        )
    )
    if is_member is None:
        await websocket.close(code=WS_FORBIDDEN, reason="Not a member of this room")
        return

    is_first_local_connection = manager.connect(room_id, websocket, user.id)
    if is_first_local_connection:
        await broadcaster.subscribe(room_id)
    await broadcaster.publish(
        room_id,
        PresenceBroadcast(
            room_id=room_id, event="join", user_id=user.id
        ).model_dump_json(),
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                envelope = _envelope_adapter.validate_json(raw)
            except ValidationError:
                # A malformed frame doesn't kill the connection — the client
                # just gets ignored until it sends something valid.
                continue

            if envelope.type == "message":
                message = Message(
                    room_id=room_id, sender_id=user.id, content=envelope.content
                )
                db.add(message)
                await db.commit()
                await db.refresh(message)
                await broadcaster.publish(
                    room_id,
                    MessageBroadcast(
                        id=message.id,
                        room_id=room_id,
                        sender_id=user.id,
                        content=message.content,
                        created_at=message.created_at,
                    ).model_dump_json(),
                )
            elif envelope.type == "typing":
                # Exclusion of the sender now happens in `_on_redis_message`
                # (by user_id, not by this socket object) once this comes
                # back through Redis — see that function's docstring.
                await broadcaster.publish(
                    room_id,
                    TypingBroadcast(
                        room_id=room_id, user_id=user.id
                    ).model_dump_json(),
                )
            # A stray "auth" frame after the handshake is silently ignored.
    except WebSocketDisconnect:
        pass
    finally:
        is_last_local_connection = manager.disconnect(room_id, websocket)
        if is_last_local_connection:
            await broadcaster.unsubscribe(room_id)
        await broadcaster.publish(
            room_id,
            PresenceBroadcast(
                room_id=room_id, event="leave", user_id=user.id
            ).model_dump_json(),
        )
