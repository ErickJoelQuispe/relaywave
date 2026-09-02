"""Integration tests for the room WebSocket.

Mirrors `test_rooms.py`: local helpers with `uuid4()`-unique data, driven
over ASGI — but through `ws_client` (httpx-ws) instead of `client`, since
`aconnect_ws` is what lets us open real WebSocket connections against the app
without leaving the test's asyncio event loop.
"""

import json
from uuid import uuid4

import pytest
from httpx_ws import WebSocketDisconnect, aconnect_ws


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
