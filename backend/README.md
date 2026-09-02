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
