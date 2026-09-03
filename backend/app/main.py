from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, health, rooms, ws
from app.core.config import get_settings
from app.core.redis import close_redis, connect_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Verify Redis is reachable at startup; release its connections at shutdown.

    `app/db/session.py`'s engine needs no equivalent step — it is lazy and
    only opens a connection when a request calls `get_db`. Redis gets an
    explicit startup check instead, so a broken REDIS_URL fails at boot
    instead of surfacing later on the first WebSocket message that needs
    the Pub/Sub bus (see app/core/redis.py, app/ws/broadcaster.py).
    """
    await connect_redis()
    yield
    await close_redis()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(ws.router)
