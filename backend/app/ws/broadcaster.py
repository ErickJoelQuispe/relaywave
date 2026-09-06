"""Per-room Redis Pub/Sub fan-out.

`app/ws/manager.py`'s `ConnectionManager` only knows about sockets held by
its own process. `RoomBroadcaster` is the cross-process half: it publishes a
room's messages to a Redis channel, and for rooms it cares about, forwards
whatever Redis delivers back to a caller-supplied callback.

Design choice — one `PubSub` connection and one background listener task PER
SUBSCRIBED ROOM, not a single blanket `psubscribe("room:*")` connection.
This is locked in docs/project-definition.md §5.3: "every pod subscribes to
the relevant Redis channels (per room)". It trades one extra Redis
connection per active room for exact control over what a given process is
listening to — an API instance only calls `subscribe()` once it has at
least one local socket connected to that room (wired in Phase 2 slice 2),
so a room nobody on this process cares about costs nothing here.

Self-echo is intentional (see ADR-002 in docs/project-definition.md): a
publisher that is also subscribed to the room it published to gets its own
message delivered back through Redis, exactly like every other subscriber.
That is how a sender learns the DB-assigned message id without a separate
optimistic-append code path on the client.

Reconnect behavior (Phase 2 slice 2): a dropped Redis connection (or any
other failure inside the listen loop) does not kill the background task
silently. `_listen` catches it, logs it, rebuilds the `PubSub` and
resubscribes, and retries with exponential backoff — a room this process
still cares about keeps trying to recover instead of going dark.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

logger = logging.getLogger(__name__)

OnMessage = Callable[[int, str], Awaitable[None]]

_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0


class RoomBroadcaster:
    def __init__(self, client: Redis, on_message: OnMessage) -> None:
        self._client = client
        self._on_message = on_message
        self._pubsubs: dict[int, PubSub] = {}
        self._tasks: dict[int, asyncio.Task[None]] = {}

    @staticmethod
    def _channel(room_id: int) -> str:
        return f"room:{room_id}"

    async def subscribe(self, room_id: int) -> None:
        """Subscribe to `room_id`'s channel, if not already subscribed.

        Starts one background task that forwards every message received on
        that room's channel to `on_message`. A no-op if already subscribed,
        so callers don't need to track subscription state themselves.
        """
        if room_id in self._pubsubs:
            return
        pubsub = self._client.pubsub()
        await pubsub.subscribe(self._channel(room_id))
        self._pubsubs[room_id] = pubsub
        self._tasks[room_id] = asyncio.create_task(self._listen(room_id, pubsub))

    async def unsubscribe(self, room_id: int) -> None:
        """Stop listening to `room_id` and release its Redis connection.

        A no-op if `room_id` was never subscribed (or already unsubscribed).
        """
        task = self._tasks.pop(room_id, None)
        pubsub = self._pubsubs.pop(room_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if pubsub is not None:
            # `pubsub` may already be closed here: if the task was mid
            # reconnect-backoff when cancelled, `_listen` closed the broken
            # connection before ever handing us a fresh one. Tearing down an
            # already-closed pubsub can raise — cleanup must never fail the
            # caller (mirrors `ConnectionManager.broadcast`'s dead-socket
            # handling above), so it's best-effort here too.
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._channel(room_id))
                await pubsub.aclose()

    async def publish(self, room_id: int, message: str) -> None:
        """Publish `message` to `room_id`'s channel.

        Every current subscriber to `room:{room_id}` receives it, including
        this same process if it is also subscribed to that room (see the
        self-echo rationale in the module docstring).
        """
        await self._client.publish(self._channel(room_id), message)

    async def _reconnect(self, room_id: int) -> PubSub:
        """Rebuild and resubscribe `room_id`'s `PubSub`, retrying with backoff.

        Blocks until a subscribe attempt succeeds. `_listen` calls this after
        catching a failure; there is no retry cap — as long as this process
        still wants `room_id`, it keeps trying, on the assumption that
        whatever broke (a network blip, a Redis restart) is eventually
        recoverable. `unsubscribe()` cancelling the task interrupts this
        loop the same way it interrupts `_listen`'s normal wait.
        """
        backoff = _INITIAL_BACKOFF_SECONDS
        while True:
            try:
                pubsub = self._client.pubsub()
                await pubsub.subscribe(self._channel(room_id))
                self._pubsubs[room_id] = pubsub
                return pubsub
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "RoomBroadcaster resubscribe for room %s failed, retrying in %.1fs",
                    room_id,
                    backoff,
                    exc_info=True,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def _listen(self, room_id: int, pubsub: PubSub) -> None:
        """Forward every message on `room_id`'s channel to `on_message`.

        `get_message(timeout=None)` blocks until a message arrives instead
        of polling, so this task costs nothing between messages. `unsubscribe()`
        cancels this task directly; the `CancelledError` raised while blocked
        in `get_message` is the normal, expected way this loop ends, so it is
        re-raised unchanged — never treated as a failure to recover from.

        A dropped connection (an exception from `get_message` itself) is
        caught and logged, `pubsub` is closed best-effort, and `_reconnect`
        rebuilds a fresh subscription with backoff. Because a new
        `_reconnect` call starts its own backoff from
        `_INITIAL_BACKOFF_SECONDS`, a run of successful deliveries between
        outages never carries stale backoff state into the next failure.

        A failure inside `on_message` itself (a decode error, a bug in the
        caller's callback) is a *different* failure mode: the Redis
        subscription is still healthy, only the payload or the callback
        choked on it. Treating that the same as a dropped connection would
        pay a full reconnect-backoff cycle for nothing, so it is caught and
        logged separately and the loop just moves on to the next message.
        """
        while True:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=None
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "RoomBroadcaster listener for room %s failed, reconnecting",
                    room_id,
                    exc_info=True,
                )
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
                pubsub = await self._reconnect(room_id)
                continue

            if message is None:
                continue

            try:
                await self._on_message(room_id, message["data"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "RoomBroadcaster on_message callback for room %s failed, "
                    "skipping message",
                    room_id,
                    exc_info=True,
                )
