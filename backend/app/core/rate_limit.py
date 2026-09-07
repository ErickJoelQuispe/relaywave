"""Fixed-window per-sender rate limiting for friend-request submission (F1-R2).

Enumeration posture (D6): the limit is applied BEFORE the target username is
resolved, so bulk username probing is throttled identically whether or not
the username exists — the limiter can never become an existence oracle.

Mechanism: a plain Redis `INCR` + `EXPIRE` fixed window over the key
`rl:friend-req:{user_id}:{window}`, where `window` is the current 60s epoch
bucket. The bucket is part of the key, so keys are naturally namespaced per
user per window and `EXPIRE` only needs to run on the first increment of a
bucket (the bucket rolls over on its own after 60s).
"""

import time

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.core.redis import redis_client

FRIEND_REQUEST_WINDOW_SECONDS = 60
FRIEND_REQUEST_MAX_PER_WINDOW = 20


class RateLimitExceeded(Exception):
    """Raised when the sender has exhausted the current window's quota."""


async def enforce_friend_request_rate_limit(user_id: int) -> None:
    """Consume one slot of the sender's current window, raising when full."""
    window = int(time.time()) // FRIEND_REQUEST_WINDOW_SECONDS
    key = f"rl:friend-req:{user_id}:{window}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, FRIEND_REQUEST_WINDOW_SECONDS)
    except (RedisConnectionError, OSError, RedisError):
        # Redis is required infrastructure (the app refuses to boot without
        # it, see app/main.py lifespan), so a runtime blip means larger
        # problems — failing open keeps the endpoint usable rather than
        # letting the limiter take the whole friends surface down.
        return
    if count > FRIEND_REQUEST_MAX_PER_WINDOW:
        raise RateLimitExceeded()
