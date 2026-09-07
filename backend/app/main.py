from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, friends, health, rooms, ws
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

# Dev-only CORS: Flutter Web's dev server runs on a random localhost port
# (`flutter run -d chrome`), a different origin than the API. Scoped to
# localhost/127.0.0.1 via regex instead of `allow_origins=["*"]` — this is
# a learning project, not a public API, but a wildcard would still leak the
# habit. WebSocket handshakes are NOT covered by CORSMiddleware (it only
# wraps the ASGI "http" scope, not "websocket"), so /ws/rooms/{id} is
# unaffected; browsers don't enforce CORS preflight on WS anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(friends.router)
app.include_router(ws.router)
