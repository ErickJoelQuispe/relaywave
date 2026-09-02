from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables and `.env`.

    Database settings land here in Phase 1. Redis and JWT settings are
    added in later phases as those dependencies are introduced.
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


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so `Settings()` — which reads the environment and `.env` file —
    runs once per process. Exposed as a function (rather than a module-level
    singleton) so it can be used with FastAPI's dependency injection and
    overridden in tests via `app.dependency_overrides`.
    """
    return Settings()
