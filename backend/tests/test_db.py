import pytest
from asyncpg.exceptions import InvalidCatalogNameError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import engine


async def test_db_connection() -> None:
    """Smoke test: prove the async engine can reach Postgres.

    Skips (rather than fails) when the app's own database is not reachable,
    so both local runs without Postgres and CI — whose service container
    only provisions the isolated `relaywave_test` database, not this app's
    dev/prod database name — stay green. Locally, run `docker compose up -d
    postgres` first and this connects to the compose-managed database.
    """
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except (OperationalError, OSError, InvalidCatalogNameError):
        pytest.skip("App database not reachable — start it with `docker compose up -d postgres`")
