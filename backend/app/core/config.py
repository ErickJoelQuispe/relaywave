from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables and `.env`.

    Database settings land here in Phase 1; JWT settings in the auth phase;
    Redis settings in Phase 2 (see docs/project-definition.md §5.3).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "relaywave-backend"
    environment: str = "local"
    debug: bool = False

    # asyncpg driver scheme. Host is `localhost` for local `uv run`
    # development (postgres is exposed on 127.0.0.1:5432 by compose); the
    # dockerized api overrides this with host `postgres` via DATABASE_URL.
    database_url: str = "postgresql+asyncpg://relaywave:relaywave@localhost:5432/relaywave"

    # redis.asyncio client URL, same local-vs-container split as
    # database_url: `localhost` for local `uv run` development (redis is
    # exposed on 127.0.0.1:6379 by compose); the dockerized api overrides
    # this with host `redis` via REDIS_URL.
    redis_url: str = "redis://localhost:6379/0"

    # Auth (JWT). `jwt_secret_key` is intentionally REQUIRED (no default):
    # a hardcoded signing key would silently ship a broken security model.
    # It must come from the environment or `backend/.env` (see `.env.example`).
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so `Settings()` — which reads the environment and `.env` file —
    runs once per process. Exposed as a function (rather than a module-level
    singleton) so it can be used with FastAPI's dependency injection and
    overridden in tests via `app.dependency_overrides`.
    """
    return Settings()
