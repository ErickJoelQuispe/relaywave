from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables and `.env`.

    Only app-identity settings live here for now. Database, Redis, and JWT
    settings are added in later phases as those dependencies are
    introduced (see docs/project-definition.md, Phase 1+).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "relaywave-backend"
    environment: str = "local"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so `Settings()` — which reads the environment and `.env` file —
    runs once per process. Exposed as a function (rather than a module-level
    singleton) so it can be used with FastAPI's dependency injection and
    overridden in tests via `app.dependency_overrides`.
    """
    return Settings()
