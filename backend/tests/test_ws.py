"""Integration tests for the room WebSocket.

Mirrors `test_rooms.py`: local helpers with `uuid4()`-unique data, driven
over ASGI — but through `ws_client` (httpx-ws) instead of `client`, since
`aconnect_ws` is what lets us open real WebSocket connections against the app
without leaving the test's asyncio event loop.
"""

import asyncio
import json
from uuid import uuid4

import pytest
import redis.asyncio as redis
from httpx_ws import WebSocketDisconnect, aconnect_ws
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import get_settings

_SUBSCRIBE_SETTLE_SECONDS = 0.1
_MESSAGE_TIMEOUT_SECONDS = 2.0


async def _register(client, email=None, username=None, password="supersecret123"):
    email = email or f"user-{uuid4()}@example.com"
    username = username or f"user_{uuid4().hex[:16]}"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), email, username, password


async def _auth_headers(client, email, password):
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_room(client, headers, name=None):
    name = name or f"room-{uuid4().hex[:8]}"
    resp = await client.post("/rooms", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json(), name


def _ws_url(room_id):
    return f"ws://test/ws/rooms/{room_id}"


async def _next_channel_message(pubsub):
    """Block until `pubsub` has a real (non-subscribe-confirmation) message."""
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
        if message is not None:
            return message["data"]


async def test_ws_requires_auth_as_first_frame(ws_client):
    _, email, _, password = await _register(ws_client)
    headers = await _auth_headers(ws_client, email, password)
    room, _ = await _create_room(ws_client, headers)

    async with aconnect_ws(_ws_url(room["id"]), client=ws_client) as ws:
        await ws.send_text(json.dumps({"type": "message", "content": "too early"}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_text()
        assert exc_info.value.code == 4401


async def test_ws_rejects_non_member(ws_client):
    _, email1, _, password = await _register(ws_client)
    _, email2, _, _ = await _register(ws_client)
    h1 = await _auth_headers(ws_client, email1, password)
    h2 = await _auth_headers(ws_client, email2, password)
    room, _ = await _create_room(ws_client, h1)  # user2 never joins

    token2 = h2["Authorization"].removeprefix("Bearer ")
    async with aconnect_ws(_ws_url(room["id"]), client=ws_client) as ws:
        await ws.send_text(json.dumps({"type": "auth", "token": token2}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_text()
        assert exc_info.value.code == 4403


async def test_ws_message_typing_and_presence(ws_client):
    user1, email1, _, password = await _register(ws_client)
    user2, email2, _, _ = await _register(ws_client)
    h1 = await _auth_headers(ws_client, email1, password)
    h2 = await _auth_headers(ws_client, email2, password)
    token1 = h1["Authorization"].removeprefix("Bearer ")
    token2 = h2["Authorization"].removeprefix("Bearer ")

    room, _ = await _create_room(ws_client, h1)
    room_id = room["id"]
    assert (
        await ws_client.post(f"/rooms/{room_id}/join", headers=h2)
    ).status_code == 201

    async with aconnect_ws(_ws_url(room_id), client=ws_client) as ws_a:
        await ws_a.send_text(json.dumps({"type": "auth", "token": token1}))

        # A is alone in the room at this point, so the "join" broadcast that
        # fires on every connect reaches only A itself — must be drained
        # before anything else or it desyncs every later receive_text() call.
        own_join_a = json.loads(await ws_a.receive_text())
        assert own_join_a == {
            "type": "presence",
            "room_id": room_id,
            "event": "join",
            "user_id": user1["id"],
        }

        async with aconnect_ws(_ws_url(room_id), client=ws_client) as ws_b:
            await ws_b.send_text(json.dumps({"type": "auth", "token": token2}))

            # B's own "join" broadcast reaches everyone now in the room:
            # A gets notified, and B also gets its own join confirmation.
            # Draining both is the synchronization point every later
            # assertion depends on.
            expected_join = {
                "type": "presence",
                "room_id": room_id,
                "event": "join",
                "user_id": user2["id"],
            }
            assert json.loads(await ws_a.receive_text()) == expected_join
            assert json.loads(await ws_b.receive_text()) == expected_join

            # B sends a chat message; both connections get the persisted
            # broadcast, including the server-assigned id and timestamp.
            await ws_b.send_text(json.dumps({"type": "message", "content": "hi"}))
            msg_a = json.loads(await ws_a.receive_text())
            msg_b = json.loads(await ws_b.receive_text())
            assert msg_a == msg_b
            assert msg_a["type"] == "message"
            assert msg_a["room_id"] == room_id
            assert msg_a["sender_id"] == user2["id"]
            assert msg_a["content"] == "hi"
            assert "id" in msg_a
            assert "created_at" in msg_a

            # Typing: B signals typing, A receives it.
            await ws_b.send_text(json.dumps({"type": "typing"}))
            typing_a = json.loads(await ws_a.receive_text())
            assert typing_a == {
                "type": "typing",
                "room_id": room_id,
                "user_id": user2["id"],
            }

            # B never gets its own typing echo: the very next frame B
            # receives is the next message broadcast, not a stray typing
            # frame sitting ahead of it in the queue.
            await ws_b.send_text(json.dumps({"type": "message", "content": "2nd"}))
            confirm_b = json.loads(await ws_b.receive_text())
            assert confirm_b["type"] == "message"
            assert confirm_b["content"] == "2nd"
            # A also gets the second message.
            await ws_a.receive_text()

        # `ws_b` context exited -> disconnect -> A gets a "leave" event.
        left = json.loads(await ws_a.receive_text())
        assert left == {
            "type": "presence",
            "room_id": room_id,
            "event": "leave",
            "user_id": user2["id"],
        }


async def test_ws_message_publishes_through_redis_and_echoes_to_sender(ws_client):
    """Prove a chat message actually crosses the Redis boundary, not just a
    local shortcut that happens to look the same.

    `test_ws_message_typing_and_presence` already shows the sender gets its
    own message back, but that alone doesn't rule out a stray direct
    `manager.broadcast()` call sitting next to `broadcaster.publish()` (the
    exact regression Phase 2 slice 2 is meant to catch). This test adds an
    independent raw Redis subscriber on `room:{room_id}` — a client with no
    connection to `RoomBroadcaster` at all — and asserts it sees the exact
    publish. Only `broadcaster.publish()` reaching real Redis can satisfy
    that; a local-only code path would leave this subscriber silent.

    The raw subscriber is attached before the WebSocket connects, so it also
    observes the connect-triggered "join" presence broadcast on the same
    channel (presence crosses Redis too, as of Phase 2 slice 3) — that event
    is drained first so it doesn't get mistaken for the chat message.
    """
    raw_client = redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await raw_client.ping()
    except (RedisConnectionError, OSError):
        await raw_client.aclose()
        pytest.skip("Redis not reachable — start it with `docker compose up -d redis`")

    _, email, _, password = await _register(ws_client)
    headers = await _auth_headers(ws_client, email, password)
    room, _ = await _create_room(ws_client, headers)
    room_id = room["id"]
    token = headers["Authorization"].removeprefix("Bearer ")

    raw_pubsub = raw_client.pubsub()
    await raw_pubsub.subscribe(f"room:{room_id}")
    try:
        async with aconnect_ws(_ws_url(room_id), client=ws_client) as ws:
            await ws.send_text(json.dumps({"type": "auth", "token": token}))
            await ws.receive_text()  # own "join" presence broadcast, drained

            # The raw subscriber sees the same "join" event on the channel;
            # drain it too before waiting for the chat message.
            join_data = await asyncio.wait_for(
                _next_channel_message(raw_pubsub), timeout=_MESSAGE_TIMEOUT_SECONDS
            )
            assert json.loads(join_data)["type"] == "presence"

            # Give both the app's RoomBroadcaster subscription and this raw
            # subscriber a moment to register with Redis before publishing.
            await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
            await ws.send_text(
                json.dumps({"type": "message", "content": "cross-pod"})
            )

            raw_data = await asyncio.wait_for(
                _next_channel_message(raw_pubsub), timeout=_MESSAGE_TIMEOUT_SECONDS
            )
            published = json.loads(raw_data)
            assert published["type"] == "message"
            assert published["content"] == "cross-pod"

            # The sender's own client receives the identical payload back —
            # the self-echo — via the same Redis round trip the raw
            # subscriber just observed, not a local delivery shortcut.
            echoed = json.loads(await ws.receive_text())
            assert echoed == published
    finally:
        await raw_pubsub.unsubscribe(f"room:{room_id}")
        await raw_pubsub.aclose()
        await raw_client.aclose()


async def test_ws_typing_and_presence_publish_through_redis(ws_client):
    """Prove typing and presence broadcasts cross the Redis boundary too,
    not just chat messages.

    Mirrors `test_ws_message_publishes_through_redis_and_echoes_to_sender`:
    an independent raw Redis subscriber, with no connection to
    `RoomBroadcaster` at all, observes the exact JSON payload for both a
    "join" presence event and a "typing" event. That rules out a stray
    direct `manager.broadcast()` call sitting next to `broadcaster.publish()`
    for either one (the regression this slice's routing change is meant to
    avoid).
    """
    raw_client = redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await raw_client.ping()
    except (RedisConnectionError, OSError):
        await raw_client.aclose()
        pytest.skip("Redis not reachable — start it with `docker compose up -d redis`")

    user, email, _, password = await _register(ws_client)
    headers = await _auth_headers(ws_client, email, password)
    room, _ = await _create_room(ws_client, headers)
    room_id = room["id"]
    token = headers["Authorization"].removeprefix("Bearer ")

    raw_pubsub = raw_client.pubsub()
    await raw_pubsub.subscribe(f"room:{room_id}")
    try:
        async with aconnect_ws(_ws_url(room_id), client=ws_client) as ws:
            await ws.send_text(json.dumps({"type": "auth", "token": token}))
            await ws.receive_text()  # own "join" presence broadcast, drained

            join_data = await asyncio.wait_for(
                _next_channel_message(raw_pubsub), timeout=_MESSAGE_TIMEOUT_SECONDS
            )
            assert json.loads(join_data) == {
                "type": "presence",
                "room_id": room_id,
                "event": "join",
                "user_id": user["id"],
            }

            await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
            await ws.send_text(json.dumps({"type": "typing"}))

            typing_data = await asyncio.wait_for(
                _next_channel_message(raw_pubsub), timeout=_MESSAGE_TIMEOUT_SECONDS
            )
            assert json.loads(typing_data) == {
                "type": "typing",
                "room_id": room_id,
                "user_id": user["id"],
            }
    finally:
        await raw_pubsub.unsubscribe(f"room:{room_id}")
        await raw_pubsub.aclose()
        await raw_client.aclose()


async def test_ws_typing_excludes_only_the_sender(ws_client):
    """A user must never see their own typing indicator, while everyone
    else in the room must see it.

    This is the exact regression `exclude_user_id` exists to prevent: once
    typing round-trips through Redis, the callback that delivers it locally
    (`_on_redis_message`) only has the `user_id` embedded in the payload —
    the original `WebSocket` object that sent it lives on whichever pod
    handled that connection and is not available here. A naive
    unconditional `manager.broadcast()` on the Redis-delivered payload
    would echo the typing indicator back to its own sender.
    """
    user1, email1, _, password = await _register(ws_client)
    user2, email2, _, _ = await _register(ws_client)
    h1 = await _auth_headers(ws_client, email1, password)
    h2 = await _auth_headers(ws_client, email2, password)
    token1 = h1["Authorization"].removeprefix("Bearer ")
    token2 = h2["Authorization"].removeprefix("Bearer ")

    room, _ = await _create_room(ws_client, h1)
    room_id = room["id"]
    assert (
        await ws_client.post(f"/rooms/{room_id}/join", headers=h2)
    ).status_code == 201

    async with aconnect_ws(_ws_url(room_id), client=ws_client) as ws_a:
        await ws_a.send_text(json.dumps({"type": "auth", "token": token1}))
        await ws_a.receive_text()  # own "join" presence broadcast, drained

        async with aconnect_ws(_ws_url(room_id), client=ws_client) as ws_b:
            await ws_b.send_text(json.dumps({"type": "auth", "token": token2}))
            # B's join broadcast reaches everyone now in the room.
            await ws_a.receive_text()
            await ws_b.receive_text()

            # A sends typing: only B should receive it.
            await ws_a.send_text(json.dumps({"type": "typing"}))
            typing_b = json.loads(await ws_b.receive_text())
            assert typing_b == {
                "type": "typing",
                "room_id": room_id,
                "user_id": user1["id"],
            }

            # Prove A truly never got its own typing indicator back: the
            # very next frame A receives is B's typing signal below, not a
            # stray echo of A's own typing sitting ahead of it in the queue.
            await ws_b.send_text(json.dumps({"type": "typing"}))
            typing_a = json.loads(await ws_a.receive_text())
            assert typing_a == {
                "type": "typing",
                "room_id": room_id,
                "user_id": user2["id"],
            }
