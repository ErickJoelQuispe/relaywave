# Relaywave Backend

FastAPI backend for Relaywave, a real-time chat platform. Phase 0: bare
application skeleton with a health check endpoint. See
`../docs/project-definition.md` for the full project context and roadmap.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; docs at `/docs`.

## Test

```bash
uv run pytest
```

## Lint

```bash
uv run ruff check .
```

## Migrations

Database schema changes are managed with Alembic. After changing a model,
generate a migration and apply it:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

## Authentication

- `POST /auth/register` — create an account (password hashed with Argon2id)
- `POST /auth/login` — exchange credentials for an access + refresh token pair
- `POST /auth/refresh` — rotate a refresh token for a new pair
- `POST /auth/logout` — revoke a refresh token (idempotent)
- `GET /auth/me` — return the authenticated user (requires a Bearer access token)

The integration test suite runs against a dedicated `relaywave_test` database.
Create it once with:

```bash
docker compose exec postgres createdb -U relaywave relaywave_test
```
