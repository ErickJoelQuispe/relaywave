import os

# Must run BEFORE any `app.*` import: pydantic-settings reads the environment
# when `Settings` is first instantiated, and `jwt_secret_key` has no default.
# `setdefault` lets a real secret from the shell win; this is only a fallback.
os.environ.setdefault("JWT_SECRET_KEY", "relaywave-test-secret-not-for-prod")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — registers every table on Base.metadata
from app.core.config import get_settings
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
                "TRUNCATE users, rooms, messages, room_memberships, refresh_tokens "
                "RESTART IDENTITY CASCADE"
            )
        )
