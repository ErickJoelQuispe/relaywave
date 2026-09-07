import os

# Must run BEFORE any `app.*` import: pydantic-settings reads the environment
# when `Settings` is first instantiated, and `jwt_secret_key` has no default.
# `setdefault` lets a real secret from the shell win; this is only a fallback.
os.environ.setdefault("JWT_SECRET_KEY", "relaywave-test-secret-not-for-prod")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from httpx_ws.transport import ASGIWebSocketTransport
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — registers every table on Base.metadata
from app.core.config import get_settings
from app.core.redis import redis_client
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Tests build/drop tables with Base.metadata for SPEED, not Alembic migrations.
# Migrations remain the source of truth for real databases; this is a
# deliberate tradeoff that keeps the test suite fast and self-contained.
# Integration tests run against a dedicated `relaywave_test` database so the
# development database is never truncated or mutated.


def _test_url():
    """The app's database URL with the database name swapped to `relaywave_test`."""
    return make_url(get_settings().database_url).set(database="relaywave_test")


@pytest_asyncio.fixture(scope="session")
async def engine():
    """A session-scoped engine bound to the dedicated test database."""
    engine = create_async_engine(_test_url())

    # Probe connectivity eagerly. If Postgres isn't reachable, skip the whole
    # suite (CI has no DB) rather than failing every test.
    try:
        async with engine.connect():
            pass
    except (OperationalError, OSError):
        await engine.dispose()
        pytest.skip("Postgres not reachable — start it and create relaywave_test")

    # A fresh schema per test session: drop then recreate all tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """A fresh AsyncSession per test, closed automatically."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def two_sessions(engine):
    """Two independent AsyncSessions for concurrency scenarios.

    The `db` fixture yields ONE session shared by the test and the ASGI app,
    which is exactly right for sequential requests but cannot express a race:
    two concurrent transactions (e.g. the F1-R4 concurrent-accept scenario)
    need two real connections so Postgres row locks actually contend. Both
    sessions come from the same session-scoped test engine.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session_a, session_factory() as session_b:
        yield session_a, session_b


@pytest_asyncio.fixture
async def client(db):
    """An httpx client that drives the app over ASGI with the test session.

    Overrides FastAPI's `get_db` so requests use the test session instead of
    the app's real engine (which points at the development database).
    """

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def ws_client(db):
    """An httpx client wired for both REST and WebSocket calls.

    Same `get_db` override as `client`. `ASGIWebSocketTransport` (from
    `httpx-ws`) extends `httpx.ASGITransport` with `aconnect_ws` support, so
    WebSocket traffic is driven in-process on the SAME event loop as the rest
    of the async test suite — mixing in Starlette's sync `TestClient` here
    would spin up a second loop and asyncpg would reject cross-loop use.

    Teardown of `ASGIWebSocketTransport` raises a spurious
    `RuntimeError: Attempted to exit cancel scope in a different task than
    it was entered in` under `pytest-asyncio` (it doesn't happen with the
    `anyio` pytest plugin). This is a confirmed upstream limitation —
    frankie567/httpx-ws#128, closed by the maintainer as "not planned" — not
    a bug in this app: every test's assertions already ran and passed by the
    time this fires during cleanup, so it's suppressed here rather than
    failing otherwise-green tests.
    """

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with ASGIWebSocketTransport(app) as transport:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
    except RuntimeError as exc:
        if "cancel scope" not in str(exc):
            raise
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(engine):
    """Truncate all tables after each test to keep tests independent."""
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, rooms, messages, room_memberships, "
                "refresh_tokens, user_relationships "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limit_keys():
    """Best-effort Redis cleanup of friend-request limiter keys after a test.

    TRUNCATE restarts user id sequences, so the next test's first registered
    user is again id 1 — a leftover `rl:friend-req:1:{window}` key from a
    429 test would throttle an unrelated test that happens to run in the
    same 60s window. Deleting the whole `rl:friend-req:*` namespace is cheap
    and never touches Pub/Sub channels (the WS/broadcaster tests use those,
    and FLUSHDB/SCAN-DEL do not affect subscriptions).
    """

    yield
    try:
        await redis_client.ping()
    except (RedisConnectionError, OSError):
        return
    async for key in redis_client.scan_iter("rl:friend-req:*", count=100):
        await redis_client.delete(key)
