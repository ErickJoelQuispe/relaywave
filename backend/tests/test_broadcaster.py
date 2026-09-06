"""Integration tests for `RoomBroadcaster`, against a real Redis instance.

Mirrors `test_db.py`'s approach for Postgres: prove the actual wire protocol
works rather than trust a fake's behavior — this project deliberately uses
real Redis over `fakeredis` for these tests. Skips (rather than fails) when
Redis isn't reachable, so CI stays green.

Room ids are hardcoded per test rather than generated, since Redis Pub/Sub
channels are transient (they only exist while a subscriber is attached) —
there is no persistent state to collide with across test runs.
"""

import asyncio

import pytest
import pytest_asyncio
import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import get_settings
from app.ws.broadcaster import RoomBroadcaster

# Redis SUBSCRIBE is asynchronous server-side: the subscription needs a
# moment to register before a publish sent immediately after is guaranteed
# to reach it.
_SUBSCRIBE_SETTLE_SECONDS = 0.1
_MESSAGE_TIMEOUT_SECONDS = 2.0
_NO_MESSAGE_TIMEOUT_SECONDS = 0.5


@pytest_asyncio.fixture(scope="session")
async def redis_client():
    """A session-scoped real Redis client, matching `engine`'s pattern in conftest.py."""
    client = redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.ping()
    except (RedisConnectionError, OSError):
        await client.aclose()
        pytest.skip("Redis not reachable — start it with `docker compose up -d redis`")
    yield client
    await client.aclose()


def _collector():
    """An `on_message` callback plus the queue it feeds, for assertions."""
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

    async def on_message(room_id: int, message: str) -> None:
        await queue.put((room_id, message))

    return on_message, queue


async def test_publish_reaches_a_subscriber_of_the_same_room(redis_client):
    on_message, queue = _collector()
    broadcaster = RoomBroadcaster(redis_client, on_message)
    room_id = 9001

    await broadcaster.subscribe(room_id)
    try:
        await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
        await broadcaster.publish(room_id, "hello")

        received = await asyncio.wait_for(queue.get(), timeout=_MESSAGE_TIMEOUT_SECONDS)
        assert received == (room_id, "hello")
    finally:
        await broadcaster.unsubscribe(room_id)


async def test_subscriber_does_not_receive_another_rooms_messages(redis_client):
    on_message, queue = _collector()
    broadcaster = RoomBroadcaster(redis_client, on_message)
    room_a, room_b = 9002, 9003

    await broadcaster.subscribe(room_a)
    try:
        await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
        # Published before the room_a message: if isolation were broken and
        # room_b leaked through, it would be the first thing in the queue.
        await broadcaster.publish(room_b, "not for room a")
        await broadcaster.publish(room_a, "for room a")

        received = await asyncio.wait_for(queue.get(), timeout=_MESSAGE_TIMEOUT_SECONDS)
        assert received == (room_a, "for room a")
        assert queue.empty()
    finally:
        await broadcaster.unsubscribe(room_a)


async def test_unsubscribe_stops_delivery(redis_client):
    on_message, queue = _collector()
    broadcaster = RoomBroadcaster(redis_client, on_message)
    room_id = 9004

    await broadcaster.subscribe(room_id)
    await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
    await broadcaster.publish(room_id, "before unsubscribe")
    received = await asyncio.wait_for(queue.get(), timeout=_MESSAGE_TIMEOUT_SECONDS)
    assert received == (room_id, "before unsubscribe")

    await broadcaster.unsubscribe(room_id)
    await broadcaster.publish(room_id, "after unsubscribe")

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=_NO_MESSAGE_TIMEOUT_SECONDS)


async def test_callback_error_does_not_trigger_reconnect(redis_client):
    """A bad payload (or any bug in `on_message`) must not be treated as a
    connection failure.

    `_on_redis_message` in `app/api/routes/ws.py` does `json.loads(data)`
    with no try/except — a malformed payload on the wire raises inside the
    callback, not inside `get_message()`. The Redis subscription itself is
    still perfectly healthy in that case; tearing it down and paying a full
    reconnect-backoff cycle fixes nothing and just delays delivery of the
    next legitimate message.
    """
    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

    async def on_message(room_id: int, message: str) -> None:
        if message == "malformed":
            raise ValueError("simulated bad payload")
        await queue.put((room_id, message))

    broadcaster = RoomBroadcaster(redis_client, on_message)
    room_id = 9006

    await broadcaster.subscribe(room_id)
    pubsub_before = broadcaster._pubsubs[room_id]
    try:
        await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
        await broadcaster.publish(room_id, "malformed")
        await broadcaster.publish(room_id, "still works")

        received = await asyncio.wait_for(queue.get(), timeout=_MESSAGE_TIMEOUT_SECONDS)
        assert received == (room_id, "still works")

        # No reconnect happened: the same PubSub object is still in use,
        # unlike test_listener_reconnects_after_a_dropped_connection below,
        # where a real connection failure replaces it via `_reconnect()`.
        assert broadcaster._pubsubs[room_id] is pubsub_before
    finally:
        await broadcaster.unsubscribe(room_id)


async def test_listener_reconnects_after_a_dropped_connection(redis_client):
    """Force-close the listener's socket mid-subscription, then prove
    delivery resumes without the background task dying.

    `pubsub.connection.disconnect()` closes the underlying socket while
    `_listen` is blocked inside `get_message()`, which raises a real
    `ConnectionError` from the blocked read — the same failure mode a
    genuine network blip or Redis restart would produce. This is a
    real-Redis test, not a mock, so the exception path is the actual
    redis-py behavior rather than an assumption about it.
    """
    on_message, queue = _collector()
    broadcaster = RoomBroadcaster(redis_client, on_message)
    room_id = 9005

    await broadcaster.subscribe(room_id)
    try:
        await asyncio.sleep(_SUBSCRIBE_SETTLE_SECONDS)
        await broadcaster.publish(room_id, "before drop")
        received = await asyncio.wait_for(queue.get(), timeout=_MESSAGE_TIMEOUT_SECONDS)
        assert received == (room_id, "before drop")

        # Force-close the socket the listener task is currently blocked on.
        await broadcaster._pubsubs[room_id].connection.disconnect()

        # The reconnect happens on the default (1s) backoff schedule, so
        # give it enough room to notice the failure, resubscribe, and
        # settle before publishing the message that proves recovery.
        await asyncio.sleep(1.5)
        await broadcaster.publish(room_id, "after reconnect")

        received = await asyncio.wait_for(queue.get(), timeout=_MESSAGE_TIMEOUT_SECONDS)
        assert received == (room_id, "after reconnect")
    finally:
        # Also proves unsubscribe() doesn't hang now that _listen has a
        # try/except wrapped around its blocking call.
        await asyncio.wait_for(broadcaster.unsubscribe(room_id), timeout=_MESSAGE_TIMEOUT_SECONDS)
