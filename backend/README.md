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

## Rooms

- `POST /rooms` — create a room (creator is auto-joined as a member)
- `GET /rooms` — list the rooms the caller is a member of
- `GET /rooms/{room_id}` — room detail, including `member_count`
- `POST /rooms/{room_id}/join` — join an existing room
- `GET /rooms/{room_id}/messages?after={id}&limit={n}` — message history,
  oldest first, capped at `limit` (default 100, max 500). Used for both the
  initial history load (`after=0`) and WebSocket reconciliation after a
  reconnect (`after=<last message id the client has>`), per ADR-002's
  best-effort delivery model.

All room endpoints require a Bearer access token and, except for create/list,
membership in the target room (`403` otherwise).

## WebSocket protocol

`WS /ws/rooms/{room_id}` — real-time chat, typing, and presence for a room.

The WebSocket handshake has no `Authorization` header, so the connection
starts unauthenticated and the **first frame must be an auth message**:

```json
{"type": "auth", "token": "<access-token>"}
```

The server closes the socket if that frame is missing, invalid, or the user
is not a member of the room:

- `4401` — missing/invalid/expired token, or no auth frame within 5s
- `4403` — valid token, but the user is not a member of `room_id`

After a successful auth, the client may send:

```json
{"type": "message", "content": "hello"}
{"type": "typing"}
```

The server broadcasts to everyone connected to the room:

```json
{"type": "message", "id": 1, "room_id": 1, "sender_id": 1, "content": "hello", "created_at": "..."}
{"type": "typing", "room_id": 1, "user_id": 1}
{"type": "presence", "room_id": 1, "event": "join", "user_id": 1}
```

Only `message` is persisted (`typing` and `presence` are ephemeral). The
connection registry is in-process and single-instance only — correct for
Phase 1's single API process; Phase 2 replaces it with Redis Pub/Sub so
multiple instances can share room membership.
