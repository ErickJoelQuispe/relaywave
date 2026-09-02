from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# create_async_engine is lazy: it builds the engine object but does NOT
# connect until first use. `pool_pre_ping` verifies a pooled connection is
# still alive before handing it out (insurance against stale connections
# after a Postgres restart).
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# async_sessionmaker is a factory for AsyncSession instances, bound to the
# engine once so every session shares the same connection pool.
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session per request and close it after.

    `expire_on_commit=False` keeps ORM objects usable after a commit, which
    matters in async code where attribute access can trigger an implicit
    await that would fail on an expired object.
    """
    async with async_session_factory() as session:
        yield session
