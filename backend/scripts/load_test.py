"""Load test driver for the Relaywave WebSocket chat backend.

Registers N ephemeral users against the real HTTP auth API, logs each one
in, creates a single shared room (user 0 creates it, everyone else joins
it), then opens N concurrent WebSocket connections against
`/ws/rooms/{room_id}` and has each connection send a small chat message on
a fixed interval to generate sustained CPU load. The point is to trigger a
real Horizontal Pod Autoscaler scale-out against a live Kubernetes
deployment, not just to hold idle sockets open — every broadcast chat
message is fanned out to every other connected member (see
`app/api/routes/ws.py`), so N connections produce roughly N^2 message
deliveries per round, which is exactly the kind of CPU load an autoscaler
should react to.

This script talks to a real, already-running backend over the network. It
does not start or configure anything — run it against a backend reachable
at `--base-url` (default: `http://localhost:8000`), for example via:

    kubectl port-forward svc/backend 8000:8000 -n relaywave

Usage:

    uv run python scripts/load_test.py --connections 300 --duration 60

Environment override for the base URL (useful in scripted runs):

    RELAYWAVE_BASE_URL=http://localhost:8000 uv run python scripts/load_test.py
"""

import argparse
import asyncio
import contextlib
import json
import os
import signal
import time
from dataclasses import dataclass
from uuid import uuid4

import httpx
from httpx_ws import WebSocketDisconnect, aconnect_ws

_DEFAULT_BASE_URL = "http://localhost:8000"
_SETUP_CONCURRENCY = 50
_SETUP_HTTP_TIMEOUT_SECONDS = 30.0
_RECEIVE_POLL_TIMEOUT_SECONDS = 1.0
_PROGRESS_INTERVAL_SECONDS = 5.0
_WS_QUEUE_SIZE = 4096
_PASSWORD = "loadtest-password-123"


@dataclass
class Stats:
    """Mutable counters shared across every connection task.

    Safe to increment from multiple asyncio tasks without a lock: asyncio
    is single-threaded and cooperative, so `stats.sent += 1` never races
    with another task's increment — there is no `await` between the read
    and the write of a single `+= 1`.
    """

    connections_opened: int = 0
    connections_failed: int = 0
    connections_alive: int = 0
    messages_sent: int = 0
    messages_received: int = 0


@dataclass
class LoadUser:
    """A registered, logged-in user, ready to open a WebSocket connection."""

    index: int
    email: str
    access_token: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Drive concurrent WebSocket connections against the Relaywave "
            "backend to generate real CPU load for HPA scale-out testing."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("RELAYWAVE_BASE_URL", _DEFAULT_BASE_URL),
        help=(
            "Backend base URL (http:// or https://). Reused for REST calls "
            "and to derive the ws(s):// WebSocket URL. "
            "(default: %(default)s, env: RELAYWAVE_BASE_URL)"
        ),
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=300,
        help="Number of concurrent WebSocket connections to open (default: %(default)s).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help=(
            "How long to hold connections open and send messages, in "
            "seconds (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--message-interval",
        type=float,
        default=2.0,
        help="Seconds between chat messages sent per connection (default: %(default)s).",
    )
    return parser.parse_args()


def _ws_base_url(base_url: str) -> str:
    """Derive the ws(s):// base URL from an http(s):// base URL."""
    if base_url.startswith("https://"):
        return "wss://" + base_url.removeprefix("https://")
    if base_url.startswith("http://"):
        return "ws://" + base_url.removeprefix("http://")
    raise ValueError(f"--base-url must start with http:// or https://, got {base_url!r}")


async def _register_and_login(
    client: httpx.AsyncClient, index: int, run_id: str, semaphore: asyncio.Semaphore
) -> LoadUser | None:
    """Register one ephemeral user and log them in. Returns None on failure.

    Failures are logged and swallowed rather than raised: the setup phase's
    job is to get as many real, authenticated users as possible, not to
    guarantee exactly `--connections` of them. A handful of register/login
    failures under load must not abort the whole run.
    """
    email = f"loadtest-{run_id}-{index}@example.com"
    username = f"loadtest_{run_id}_{index}"[:50]
    async with semaphore:
        try:
            resp = await client.post(
                "/auth/register",
                json={"email": email, "username": username, "password": _PASSWORD},
            )
            resp.raise_for_status()
            resp = await client.post(
                "/auth/login", json={"email": email, "password": _PASSWORD}
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]
        except (httpx.HTTPError, KeyError) as exc:
            print(f"[setup] user {index} register/login failed: {exc}")
            return None
    return LoadUser(index=index, email=email, access_token=token)


async def _join_room(
    client: httpx.AsyncClient, user: LoadUser, room_id: int, semaphore: asyncio.Semaphore
) -> bool:
    """Join `user` to `room_id`. Returns False (and logs) on failure."""
    headers = {"Authorization": f"Bearer {user.access_token}"}
    async with semaphore:
        try:
            resp = await client.post(f"/rooms/{room_id}/join", headers=headers)
            # 409 means "already a member" — harmless, treat as success.
            if resp.status_code not in (201, 409):
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"[setup] user {user.index} failed to join room {room_id}: {exc}")
            return False
    return True


async def _setup(base_url: str, connections: int) -> tuple[int, list[LoadUser]]:
    """Register/login N users, create one shared room, join everyone to it.

    Returns the room id and the list of users who made it all the way
    through (registered, logged in, AND confirmed room members) — only
    those are eligible to open a WebSocket connection in the load phase.
    """
    run_id = uuid4().hex[:8]
    semaphore = asyncio.Semaphore(_SETUP_CONCURRENCY)

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=_SETUP_HTTP_TIMEOUT_SECONDS,
        limits=httpx.Limits(max_connections=_SETUP_CONCURRENCY + 10),
    ) as client:
        print(f"[setup] registering {connections} users (run id {run_id})...")
        results = await asyncio.gather(
            *(
                _register_and_login(client, i, run_id, semaphore)
                for i in range(connections)
            )
        )
        users = [u for u in results if u is not None]
        print(f"[setup] {len(users)}/{connections} users registered and logged in")
        if not users:
            raise RuntimeError("No users could be registered — is the backend reachable?")

        creator = users[0]
        headers = {"Authorization": f"Bearer {creator.access_token}"}
        resp = await client.post(
            "/rooms", json={"name": f"load-test-{run_id}"}, headers=headers
        )
        resp.raise_for_status()
        room_id = resp.json()["id"]
        print(f"[setup] created room {room_id} (owner: user {creator.index})")

        joined_flags = await asyncio.gather(
            *(_join_room(client, u, room_id, semaphore) for u in users[1:])
        )
        joined = zip(users[1:], joined_flags, strict=True)
        members = [creator] + [u for u, ok in joined if ok]
        print(f"[setup] {len(members)}/{len(users)} users confirmed as room members")

    return room_id, members


async def _sender(
    ws, interval: float, deadline: float, stats: Stats, shutdown: asyncio.Event
) -> None:
    """Send a small chat message every `interval` seconds until `deadline`."""
    while time.monotonic() < deadline and not shutdown.is_set():
        try:
            await ws.send_text(json.dumps({"type": "message", "content": "load-test ping"}))
            stats.messages_sent += 1
        except Exception:  # noqa: BLE001 — connection already dead; receiver reports it
            return
        remaining = max(deadline - time.monotonic(), 0.0)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(shutdown.wait(), timeout=min(interval, remaining) or 0.01)


async def _receiver(ws, deadline: float, stats: Stats, shutdown: asyncio.Event) -> None:
    """Drain incoming broadcasts (chat echoes, presence, typing) until `deadline`."""
    while time.monotonic() < deadline and not shutdown.is_set():
        try:
            await asyncio.wait_for(ws.receive_text(), timeout=_RECEIVE_POLL_TIMEOUT_SECONDS)
            stats.messages_received += 1
        except TimeoutError:
            continue
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001 — connection dropped; nothing more to drain
            return


async def _run_connection(
    ws_url: str,
    user: LoadUser,
    duration: float,
    interval: float,
    stats: Stats,
    shutdown: asyncio.Event,
) -> None:
    """Open one WebSocket connection, perform the auth handshake, then
    send/receive chat traffic until `duration` elapses or shutdown fires.
    """
    try:
        async with httpx.AsyncClient(timeout=_SETUP_HTTP_TIMEOUT_SECONDS) as client:
            async with aconnect_ws(ws_url, client=client, queue_size=_WS_QUEUE_SIZE) as ws:
                # First frame after connecting MUST be the auth envelope —
                # see app/api/routes/ws.py's `_authenticate`. There is no
                # explicit "auth ok" ack; success just means the connection
                # stays open and starts receiving broadcasts.
                await ws.send_text(json.dumps({"type": "auth", "token": user.access_token}))
                stats.connections_opened += 1
                stats.connections_alive += 1
                deadline = time.monotonic() + duration
                try:
                    await asyncio.gather(
                        _sender(ws, interval, deadline, stats, shutdown),
                        _receiver(ws, deadline, stats, shutdown),
                    )
                finally:
                    stats.connections_alive -= 1
    except Exception as exc:  # noqa: BLE001 — one bad connection must not kill the run
        stats.connections_failed += 1
        print(f"[load] user {user.index} connection failed: {exc}")


async def _print_progress(
    stats: Stats, total: int, shutdown: asyncio.Event, start: float
) -> None:
    while not shutdown.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(shutdown.wait(), timeout=_PROGRESS_INTERVAL_SECONDS)
        elapsed = time.monotonic() - start
        print(
            f"[progress] t={elapsed:5.1f}s alive={stats.connections_alive}/{total} "
            f"sent={stats.messages_sent} received={stats.messages_received} "
            f"errors={stats.connections_failed}"
        )


async def _run_load(
    ws_base_url: str,
    room_id: int,
    users: list[LoadUser],
    duration: float,
    interval: float,
) -> Stats:
    ws_url = f"{ws_base_url}/ws/rooms/{room_id}"
    stats = Stats()
    shutdown = asyncio.Event()

    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        # Not implemented on Windows — Ctrl+C still raises KeyboardInterrupt
        # there, which asyncio.run() propagates out of _main().
        loop.add_signal_handler(signal.SIGINT, shutdown.set)

    start = time.monotonic()
    progress_task = asyncio.create_task(_print_progress(stats, len(users), shutdown, start))
    print(f"[load] opening {len(users)} connections to {ws_url} for {duration}s...")

    connection_tasks = [
        asyncio.create_task(_run_connection(ws_url, user, duration, interval, stats, shutdown))
        for user in users
    ]
    await asyncio.gather(*connection_tasks, return_exceptions=True)

    shutdown.set()
    progress_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_task

    return stats


async def _main() -> None:
    args = _parse_args()
    ws_base_url = _ws_base_url(args.base_url)

    room_id, users = await _setup(args.base_url, args.connections)
    if not users:
        print("[load] no users survived setup — aborting load phase")
        return

    start = time.monotonic()
    stats = await _run_load(ws_base_url, room_id, users, args.duration, args.message_interval)
    elapsed = time.monotonic() - start

    print("\n=== Load test summary ===")
    print(f"Requested connections : {args.connections}")
    print(f"Users ready for load  : {len(users)}")
    print(f"Connections opened    : {stats.connections_opened}")
    print(f"Connections failed    : {stats.connections_failed}")
    print(f"Messages sent         : {stats.messages_sent}")
    print(f"Messages received     : {stats.messages_received}")
    print(f"Elapsed               : {elapsed:.1f}s")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())
