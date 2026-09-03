"""Cross-replica proof for Phase 2 slice 4: two real backend processes, one
Redis, no shared memory between them.

Every other WS test in this suite (`test_ws.py`) drives the app in-process
over `ASGITransport` — a single Python process, a single `ConnectionManager`,
a single event loop. That setup can never disprove a bug where Redis
Pub/Sub is bypassed by a local shortcut, because there is only one process
to begin with; a stray direct `manager.broadcast()` call would look
identical to a real Redis round trip.

This file is different on purpose: it connects to TWO separately running
`uvicorn` processes (`docker-compose.yml`'s `api` on host port 8000 and
`api-2` on host port 8001), each with its OWN in-memory `ConnectionManager`
and OWN Python interpreter. A message sent through replica 1's WebSocket can
only reach a client connected to replica 2 by actually publishing to Redis
and having replica 2's `RoomBroadcaster` subscription deliver it locally on
its side — there is no in-memory path between the two processes at all.

Requirements to run this file: the FULL Docker Compose stack must be up,
not just `redis`/`postgres` (see the skip message below for the exact
command). This test structurally cannot run against the ASGI in-process app
used elsewhere in this suite — there is nothing to prove cross-process
delivery against without two real, separately listening replicas.

KNOWN PRE-EXISTING RACE (discovered while writing this file, not introduced
by it — see the slice 4 report for full detail): `room_websocket` in
`app/api/routes/ws.py` calls `await broadcaster.subscribe(room_id)`
immediately followed by `await broadcaster.publish(room_id, join_event)`,
with no settle delay between them. `redis.asyncio`'s `PubSub.subscribe()`
sends the SUBSCRIBE command but deliberately does NOT wait for the server's
subscription confirmation before returning (see redis-py's own
`PubSub.execute_command` docstring). A publish that reaches Redis before
that subscription is actually active is silently dropped — no error, no
retry, nothing in the logs. This means the FIRST local connection to a
fresh room on a given replica has a real (empirically ~30-40% reproducible
over the real Docker network) chance of never receiving its own "join"
broadcast. `test_broadcaster.py` and `test_ws.py`'s raw-redis-subscriber
tests already work around the same underlying gotcha with
`_SUBSCRIBE_SETTLE_SECONDS` sleeps in the TEST code, but that settle delay
was never added to the production route itself. Per this task's
constraints, `app/api/routes/ws.py` is out of scope to fix here — so rather
than asserting on that specific racy self-echo (which would make this test
itself intermittently fail for a reason that has nothing to do with
cross-replica delivery), `_receive_until` below tolerates the presence
noise being absent, and only asserts on events proven safe by construction
(see each test's docstring for why).
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import httpx
import pytest
from httpx_ws import aconnect_ws

_REPLICA_1_URL = "http://127.0.0.1:8000"
_REPLICA_2_URL = "http://127.0.0.1:8001"
_MESSAGE_TIMEOUT_SECONDS = 5.0
# Same rationale and value as `_SUBSCRIBE_SETTLE_SECONDS` in
# test_broadcaster.py / test_ws.py: give a replica's freshly established
# Redis subscription (triggered by a socket's connect) time to be confirmed
# by the Redis server before anything is published that this test asserts
# on — see the module docstring's note on the subscribe/publish race.
_SUBSCRIBE_SETTLE_SECONDS = 0.1


def _ws_url(base_url: str, room_id: int) -> str:
    return f"{base_url.replace('http://', 'ws://')}/ws/rooms/{room_id}"


async def _replica_reachable(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
            resp = await client.get("/health")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


@pytest.fixture
async def _both_replicas_up():
    """Skip cleanly if either replica isn't reachable over real HTTP.

    Unlike `redis_client`/`engine` in the other test files, there is no way
    to bring these processes up from inside pytest — they're separate OS
    processes managed by Compose, not fixtures this suite can construct.
    """
    if not (await _replica_reachable(_REPLICA_1_URL) and await _replica_reachable(_REPLICA_2_URL)):
        pytest.skip(
            "Both replicas must be reachable for this test — start the full "
            "stack with `docker compose up -d` (not just redis/postgres) and "
            "wait for `api` (127.0.0.1:8000) and `api-2` (127.0.0.1:8001) to "
            "report healthy via `docker compose ps`."
        )


async def _register(client: httpx.AsyncClient, password: str = "supersecret123"):
    email = f"user-{uuid4()}@example.com"
    username = f"user_{uuid4().hex[:16]}"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), email, password


async def _auth_headers(client: httpx.AsyncClient, email: str, password: str):
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_room(client: httpx.AsyncClient, headers: dict):
    name = f"room-{uuid4().hex[:8]}"
    resp = await client.post("/rooms", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _receive_until(
    ws, predicate: Callable[[dict[str, Any]], bool], timeout: float
) -> dict[str, Any]:
    """Receive JSON frames from `ws`, skipping any that don't match
    `predicate`, until one does (or the overall `timeout` elapses).

    See this module's docstring for the pre-existing "join" self-echo race
    this exists to tolerate: a fresh connection may or may not see its own
    "join" broadcast, so tests that don't care about that specific frame
    skip past it instead of asserting on exact frame-by-frame ordering.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"no frame matching {predicate!r} within {timeout}s")
        data = json.loads(await ws.receive_text(timeout=remaining))
        if predicate(data):
            return data


async def test_chat_message_crosses_replicas_in_both_directions(_both_replicas_up):
    """Prove Redis Pub/Sub — not shared memory — is what delivers a chat
    message between two independent backend processes.

    Both users and the room are set up via replica 1's REST API; they land
    in the one shared Postgres both replicas point at. The two WebSocket
    connections are then split across the two replicas, so the only path a
    message can travel is: socket -> replica's WS route -> Redis publish ->
    the OTHER replica's `RoomBroadcaster` subscription -> that replica's own
    `ConnectionManager` -> its socket. If `RoomBroadcaster.publish()` (or
    the Redis subscription that feeds `_on_redis_message`) were removed,
    each replica would fall back to broadcasting only within its own
    process, and the assertions below would time out waiting for a message
    that never arrives.

    This test does not assert on the connect-triggered "join" presence
    broadcasts at all (see the module docstring on the subscribe/publish
    race) — `_receive_until` simply skips past any presence frames to reach
    the "message" frames that are the actual point of this test.
    """
    async with httpx.AsyncClient(base_url=_REPLICA_1_URL) as setup_client:
        user1, email1, password = await _register(setup_client)
        user2, email2, _ = await _register(setup_client)
        headers1 = await _auth_headers(setup_client, email1, password)
        headers2 = await _auth_headers(setup_client, email2, password)
        token1 = headers1["Authorization"].removeprefix("Bearer ")
        token2 = headers2["Authorization"].removeprefix("Bearer ")

        room = await _create_room(setup_client, headers1)
        room_id = room["id"]
        assert (
            await setup_client.post(f"/rooms/{room_id}/join", headers=headers2)
        ).status_code == 201

    is_message = lambda data: data["type"] == "message"  # noqa: E731

    async with (
        httpx.AsyncClient(base_url=_REPLICA_1_URL) as client1,
        httpx.AsyncClient(base_url=_REPLICA_2_URL) as client2,
    ):
        async with (
            aconnect_ws(_ws_url(_REPLICA_1_URL, room_id), client=client1) as ws1,
            aconnect_ws(_ws_url(_REPLICA_2_URL, room_id), client=client2) as ws2,
        ):
            await ws1.send_text(json.dumps({"type": "auth", "token": token1}))
            await ws2.send_text(json.dumps({"type": "auth", "token": token2}))
            await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)

            # Replica 1 -> replica 2: user1 sends through ws1, user2's
            # socket on the OTHER process must receive the identical
            # payload. Any "join" presence noise ahead of it in either
            # queue is skipped by `_receive_until`.
            await ws1.send_text(json.dumps({"type": "message", "content": "r1-to-r2"}))
            msg_on_ws1 = await _receive_until(ws1, is_message, _MESSAGE_TIMEOUT_SECONDS)
            msg_on_ws2 = await _receive_until(ws2, is_message, _MESSAGE_TIMEOUT_SECONDS)
            assert msg_on_ws1 == msg_on_ws2
            assert msg_on_ws1["type"] == "message"
            assert msg_on_ws1["room_id"] == room_id
            assert msg_on_ws1["sender_id"] == user1["id"]
            assert msg_on_ws1["content"] == "r1-to-r2"
            assert "id" in msg_on_ws1
            assert "created_at" in msg_on_ws1

            # Replica 2 -> replica 1: the reverse direction, for symmetry —
            # proves this isn't an artifact of connection order.
            await ws2.send_text(json.dumps({"type": "message", "content": "r2-to-r1"}))
            msg_on_ws2_again = await _receive_until(ws2, is_message, _MESSAGE_TIMEOUT_SECONDS)
            msg_on_ws1_again = await _receive_until(ws1, is_message, _MESSAGE_TIMEOUT_SECONDS)
            assert msg_on_ws1_again == msg_on_ws2_again
            assert msg_on_ws1_again["sender_id"] == user2["id"]
            assert msg_on_ws1_again["content"] == "r2-to-r1"


async def test_typing_and_presence_cross_replicas(_both_replicas_up):
    """Same cross-process proof as the chat-message test, applied to typing
    and the "leave" presence event, which route through Redis independently
    of chat messages (Phase 2 slice 3).

    Unlike a connecting socket's own "join" self-echo (see the module
    docstring), both of these are safe to assert on deterministically:

    - Typing is sent well after both sockets finished their auth handshake,
      by which point both replicas' subscriptions for this room have long
      since been confirmed by Redis (each already delivered at least the
      connect-triggered traffic before this point) — there is no
      subscribe/publish race left to lose.
    - The "leave" event fires when ws2 disconnects, on a subscription
      (replica 1's) that has existed since user1 connected, long before
      user2 even joined — again nothing freshly subscribing at publish time.
    """
    async with httpx.AsyncClient(base_url=_REPLICA_2_URL) as setup_client:
        user1, email1, password = await _register(setup_client)
        user2, email2, _ = await _register(setup_client)
        headers1 = await _auth_headers(setup_client, email1, password)
        headers2 = await _auth_headers(setup_client, email2, password)
        token1 = headers1["Authorization"].removeprefix("Bearer ")
        token2 = headers2["Authorization"].removeprefix("Bearer ")

        room = await _create_room(setup_client, headers1)
        room_id = room["id"]
        assert (
            await setup_client.post(f"/rooms/{room_id}/join", headers=headers2)
        ).status_code == 201

    async with (
        httpx.AsyncClient(base_url=_REPLICA_1_URL) as client1,
        httpx.AsyncClient(base_url=_REPLICA_2_URL) as client2,
    ):
        async with aconnect_ws(_ws_url(_REPLICA_1_URL, room_id), client=client1) as ws1:
            await ws1.send_text(json.dumps({"type": "auth", "token": token1}))
            await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)

            async with aconnect_ws(_ws_url(_REPLICA_2_URL, room_id), client=client2) as ws2:
                await ws2.send_text(json.dumps({"type": "auth", "token": token2}))
                await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)

                # Typing on replica 1 (user1) must reach replica 2's socket
                # (user2) — a cross-process delivery, not the exclude-self
                # local shortcut `test_ws.py` already covers in-process.
                await ws1.send_text(json.dumps({"type": "typing"}))
                typing_on_ws2 = await _receive_until(
                    ws2, lambda data: data["type"] == "typing", _MESSAGE_TIMEOUT_SECONDS
                )
                assert typing_on_ws2 == {
                    "type": "typing",
                    "room_id": room_id,
                    "user_id": user1["id"],
                }

            # ws2's context exited -> disconnect on replica 2 -> the "leave"
            # presence event must still reach ws1 on replica 1.
            left = await _receive_until(
                ws1,
                lambda data: data["type"] == "presence" and data["event"] == "leave",
                _MESSAGE_TIMEOUT_SECONDS,
            )
            assert left == {
                "type": "presence",
                "room_id": room_id,
                "event": "leave",
                "user_id": user2["id"],
            }
