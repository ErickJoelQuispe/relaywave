import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import engine


async def test_db_connection() -> None:
    """Smoke test: prove the async engine can reach Postgres.

    Skips (rather than fails) when Postgres is not reachable so CI — which
    has no database — stays green. Locally, run `docker compose up -d
    postgres` first and this connects to the compose-managed database.
    """
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    except (OperationalError, OSError):
        pytest.skip("Postgres not reachable — start it with `docker compose up -d postgres`")
