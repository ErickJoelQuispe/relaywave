"""Shared Redis async client (redis.asyncio), used for Pub/Sub fan-out.

Phase 1 ran a single backend instance, so `app/ws/manager.py`'s in-process
`ConnectionManager` was enough. Phase 2 introduces this client so multiple
instances can share room messaging via Redis Pub/Sub (see
docs/project-definition.md §5.3). This module only owns the connection
lifecycle; `app/ws/broadcaster.py`'s `RoomBroadcaster` is what actually
publishes/subscribes with it.
"""

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

# from_url is lazy like create_async_engine: it builds the client and its
# connection pool but does not open a socket until first use.
# `decode_responses=True` because every message this project sends over
# Redis is a UTF-8 JSON string (see app/schemas/message.py) — decoding once
# here means every call site gets `str`, not `bytes`.
redis_client: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)


async def connect_redis() -> None:
    """Ping Redis once at startup.

    A broken REDIS_URL then fails at boot instead of surfacing later, on
    the first WebSocket message that needs the Pub/Sub bus.
    """
    await redis_client.ping()


async def close_redis() -> None:
    """Close the shared client's connection pool. Called at app shutdown."""
    await redis_client.aclose()
