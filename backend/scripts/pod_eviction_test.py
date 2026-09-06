"""End-to-end proof that a live WebSocket survives a Kubernetes pod eviction.

This is Phase 3 Slice 7's proof, automated: two real users (A and B) join
the same room over two WebSocket connections pinned to two *specific*
backend pods by name (never the Service, which pins a whole port-forward
session to one pod and would defeat the point). Once a message flows
end-to-end, the pod serving user A is deleted with `kubectl delete pod`
while B keeps sending messages into the outage window. The script then
waits for Kubernetes to schedule a replacement pod, reconnects A to it, and
asserts that every message B sent during the outage shows up via history
reconciliation (`GET /rooms/{id}/messages?after=`) with no duplicates and
no gaps — exactly the ADR-002 contract the Flutter client already relies on.

This script itself issues the cluster-mutating `kubectl` commands (scale,
get pods, delete pod, port-forward). That is a deliberate, narrow,
user-authorized exception to this project's Phase 3 rule that the human
writes and runs every kubectl/kind command; it does not change that rule
going forward.

Usage:

    uv run python scripts/pod_eviction_test.py

Requires: an existing `relaywave` kind cluster with the Phase 3 manifests
applied (namespace, Postgres, Redis, backend Deployment/Service/HPA), and a
working `kubectl` context pointed at it (`kubectl config current-context`).
"""

import asyncio
import contextlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
from httpx_ws import aconnect_ws

_NAMESPACE = "relaywave"
_DEPLOYMENT = "backend"
_LABEL_SELECTOR = "app=backend"
_PORT_A = 18000
_PORT_B = 18001
_PASSWORD = "podevict-password-123"
_PORT_FORWARD_READY_TIMEOUT = 15.0
_POD_READY_TIMEOUT = 90.0
_POD_TERMINATED_TIMEOUT = 60.0
_OUTAGE_MESSAGE_COUNT = 5
_OUTAGE_MESSAGE_INTERVAL = 1.5
_POST_RECONNECT_SETTLE_SECONDS = 3.0


def _kubectl(*args: str, timeout: float = 30.0) -> str:
    """Run kubectl synchronously and return stdout, raising on failure."""
    proc = subprocess.run(
        ["kubectl", *args, "-n", _NAMESPACE],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"kubectl {' '.join(args)} failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def _get_backend_pod_names() -> list[str]:
    out = _kubectl("get", "pods", "-l", _LABEL_SELECTOR, "-o", "json")
    data = json.loads(out)
    return [item["metadata"]["name"] for item in data["items"]]


def _get_ready_backend_pod_names() -> list[str]:
    out = _kubectl("get", "pods", "-l", _LABEL_SELECTOR, "-o", "json")
    data = json.loads(out)
    ready = []
    for item in data["items"]:
        if item["status"].get("phase") != "Running":
            continue
        conditions = {c["type"]: c["status"] for c in item["status"].get("conditions", [])}
        if conditions.get("Ready") == "True":
            ready.append(item["metadata"]["name"])
    return ready


def _ensure_two_replicas() -> None:
    print(f"[setup] scaling deployment/{_DEPLOYMENT} to 2 replicas...")
    _kubectl("scale", f"deployment/{_DEPLOYMENT}", "--replicas=2")
    deadline = time.monotonic() + _POD_READY_TIMEOUT
    while time.monotonic() < deadline:
        ready = _get_ready_backend_pod_names()
        if len(ready) >= 2:
            print(f"[setup] 2 backend pods ready: {ready}")
            return
        time.sleep(2)
    raise RuntimeError("timed out waiting for 2 ready backend pods")


class PortForward:
    """A background `kubectl port-forward pod/<name> <local>:8000` process."""

    def __init__(self, pod_name: str, local_port: int) -> None:
        self.pod_name = pod_name
        self.local_port = local_port
        self._proc: subprocess.Popen[str] | None = None

    async def start(self) -> None:
        self._proc = subprocess.Popen(
            [
                "kubectl",
                "port-forward",
                f"pod/{self.pod_name}",
                f"{self.local_port}:8000",
                "-n",
                _NAMESPACE,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        deadline = time.monotonic() + _PORT_FORWARD_READY_TIMEOUT
        assert self._proc.stdout is not None
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"port-forward to pod/{self.pod_name} exited early "
                    f"(code {self._proc.returncode})"
                )
            line = await asyncio.get_event_loop().run_in_executor(
                None, self._proc.stdout.readline
            )
            if "Forwarding from" in line:
                print(f"[pf] pod/{self.pod_name} -> 127.0.0.1:{self.local_port} ready")
                return
        raise RuntimeError(f"port-forward to pod/{self.pod_name} never became ready")

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=5)


@dataclass
class TestUser:
    email: str
    username: str
    access_token: str = ""
    user_id: int = 0


@dataclass
class ReceivedMessages:
    items: list[dict] = field(default_factory=list)
    max_id: int = 0

    def record(self, payload: dict) -> None:
        self.items.append(payload)
        self.max_id = max(self.max_id, payload["id"])

    def contents(self) -> list[str]:
        return [m["content"] for m in self.items]


async def _register_and_login(base_url: str, run_id: str, index: int) -> TestUser:
    email = f"podevict-{run_id}-{index}@example.com"
    username = f"podevict_{run_id}_{index}"[:50]
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.post(
            "/auth/register",
            json={"email": email, "username": username, "password": _PASSWORD},
        )
        resp.raise_for_status()
        resp = await client.post("/auth/login", json={"email": email, "password": _PASSWORD})
        resp.raise_for_status()
        body = resp.json()
    return TestUser(email=email, username=username, access_token=body["access_token"])


async def _create_room(base_url: str, owner: TestUser, run_id: str) -> int:
    headers = {"Authorization": f"Bearer {owner.access_token}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.post(
            "/rooms", json={"name": f"pod-evict-test-{run_id}"}, headers=headers
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def _join_room(base_url: str, user: TestUser, room_id: int) -> None:
    headers = {"Authorization": f"Bearer {user.access_token}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.post(f"/rooms/{room_id}/join", headers=headers)
        if resp.status_code not in (201, 409):
            resp.raise_for_status()


async def _fetch_history(base_url: str, token: str, room_id: int, after: int) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.get(
            f"/rooms/{room_id}/messages", params={"after": after, "limit": 500}, headers=headers
        )
        resp.raise_for_status()
        return resp.json()


async def _ws_receiver(ws, received: ReceivedMessages, stop: asyncio.Event) -> None:
    """Drain broadcasts until `stop` is set or the socket dies."""
    while not stop.is_set():
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
        except TimeoutError:
            continue
        except Exception:  # noqa: BLE001 — socket dropped; caller decides what that means
            return
        payload = json.loads(raw)
        if payload.get("type") == "message":
            received.record(payload)


async def _send_outage_messages(
    ws_url_b: str, token_b: str, count: int, interval: float
) -> list[str]:
    """B sends `count` messages, `interval` seconds apart, while A is presumed down."""
    sent: list[str] = []
    async with httpx.AsyncClient(timeout=30.0) as client, aconnect_ws(
        ws_url_b, client=client
    ) as ws:
        await ws.send_text(json.dumps({"type": "auth", "token": token_b}))
        for i in range(count):
            content = f"outage-message-{i}"
            await ws.send_text(json.dumps({"type": "message", "content": content}))
            sent.append(content)
            print(f"[outage] B sent: {content}")
            await asyncio.sleep(interval)
    return sent


async def _main() -> int:
    print("=== Phase 3 Slice 7: pod-eviction resilience proof ===\n")

    _ensure_two_replicas()
    pods = _get_ready_backend_pod_names()
    if len(pods) < 2:
        print(f"FAIL: expected 2 ready pods, got {pods}")
        return 1
    pod_a, pod_b = pods[0], pods[1]
    print(f"[setup] user A pinned to pod/{pod_a} (port {_PORT_A})")
    print(f"[setup] user B pinned to pod/{pod_b} (port {_PORT_B}) — never touched\n")

    pf_a = PortForward(pod_a, _PORT_A)
    pf_b = PortForward(pod_b, _PORT_B)
    await pf_a.start()
    await pf_b.start()

    base_url_a = f"http://127.0.0.1:{_PORT_A}"
    base_url_b = f"http://127.0.0.1:{_PORT_B}"
    ws_base_a = f"ws://127.0.0.1:{_PORT_A}"
    ws_base_b = f"ws://127.0.0.1:{_PORT_B}"

    run_id = uuid4().hex[:8]
    user_a = await _register_and_login(base_url_a, run_id, 0)
    user_b = await _register_and_login(base_url_b, run_id, 1)
    room_id = await _create_room(base_url_a, user_a, run_id)
    await _join_room(base_url_b, user_b, room_id)
    print(f"[setup] room {room_id} created, both users joined\n")

    ws_url_a = f"{ws_base_a}/ws/rooms/{room_id}"
    ws_url_b = f"{ws_base_b}/ws/rooms/{room_id}"

    received_a = ReceivedMessages()
    stop_a = asyncio.Event()

    client_a = httpx.AsyncClient(timeout=30.0)
    ws_a_ctx = aconnect_ws(ws_url_a, client=client_a)
    ws_a = await ws_a_ctx.__aenter__()
    await ws_a.send_text(json.dumps({"type": "auth", "token": user_a.access_token}))
    receiver_task = asyncio.create_task(_ws_receiver(ws_a, received_a, stop_a))

    # --- Baseline: prove the room actually works before breaking anything ---
    async with httpx.AsyncClient(timeout=30.0) as client, aconnect_ws(
        ws_url_b, client=client
    ) as ws_b_baseline:
        await ws_b_baseline.send_text(json.dumps({"type": "auth", "token": user_b.access_token}))
        await ws_b_baseline.send_text(json.dumps({"type": "message", "content": "baseline"}))
        await asyncio.sleep(1.5)

    if "baseline" not in received_a.contents():
        print("FAIL: user A never received B's baseline message before eviction — aborting")
        stop_a.set()
        pf_a.stop()
        pf_b.stop()
        return 1
    last_seen_id = received_a.max_id
    print(f"[baseline] OK — A received B's message live (last_seen_id={last_seen_id})\n")

    # --- Evict pod A while B keeps talking ---
    print(f"[evict] deleting pod/{pod_a} now (user A's live connection)...")
    delete_proc = subprocess.Popen(
        ["kubectl", "delete", "pod", pod_a, "-n", _NAMESPACE, "--wait=true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    outage_sent = await _send_outage_messages(
        ws_url_b, user_b.access_token, _OUTAGE_MESSAGE_COUNT, _OUTAGE_MESSAGE_INTERVAL
    )

    delete_proc.wait(timeout=_POD_TERMINATED_TIMEOUT)
    print(f"[evict] pod/{pod_a} terminated\n")

    stop_a.set()
    with contextlib.suppress(Exception):
        await receiver_task
    with contextlib.suppress(Exception):
        await ws_a_ctx.__aexit__(None, None, None)
    with contextlib.suppress(Exception):
        await client_a.aclose()
    pf_a.stop()
    print("[evict] user A's connection and port-forward are confirmed down\n")

    # --- Wait for Kubernetes to replace the evicted pod ---
    print("[recover] waiting for a replacement pod...")
    deadline = time.monotonic() + _POD_READY_TIMEOUT
    new_pod_a = None
    while time.monotonic() < deadline:
        ready = _get_ready_backend_pod_names()
        candidates = [p for p in ready if p != pod_b and p != pod_a]
        if candidates:
            new_pod_a = candidates[0]
            break
        time.sleep(2)
    if new_pod_a is None:
        print("FAIL: no replacement pod became ready in time")
        pf_b.stop()
        return 1
    print(f"[recover] replacement pod/{new_pod_a} is ready\n")

    # --- Reconnect A to the new pod and backfill via history reconciliation ---
    new_pf_a = PortForward(new_pod_a, _PORT_A)
    await new_pf_a.start()

    history = await _fetch_history(base_url_a, user_a.access_token, room_id, last_seen_id)
    history_contents = [m["content"] for m in history]
    history_ids = [m["id"] for m in history]

    # Also prove the *live* socket recovers, not just the REST backfill: open
    # a fresh WS on the new pod (auth handshake again — this is exactly what
    # the Flutter client's auto-reconnect does) and confirm a brand-new
    # message from B is delivered live post-recovery.
    live_received = ReceivedMessages()
    stop_new = asyncio.Event()
    async with httpx.AsyncClient(timeout=30.0) as client_new, aconnect_ws(
        f"{ws_base_a}/ws/rooms/{room_id}", client=client_new
    ) as ws_a_new:
        await ws_a_new.send_text(json.dumps({"type": "auth", "token": user_a.access_token}))
        live_task = asyncio.create_task(_ws_receiver(ws_a_new, live_received, stop_new))
        async with httpx.AsyncClient(timeout=30.0) as client_b2, aconnect_ws(
            ws_url_b, client=client_b2
        ) as ws_b2:
            await ws_b2.send_text(json.dumps({"type": "auth", "token": user_b.access_token}))
            await ws_b2.send_text(
                json.dumps({"type": "message", "content": "post-reconnect-live"})
            )
        await asyncio.sleep(_POST_RECONNECT_SETTLE_SECONDS)
        stop_new.set()
        with contextlib.suppress(Exception):
            await live_task

    new_pf_a.stop()
    pf_b.stop()

    # --- Verdict ---
    print("=== Results ===")
    print(f"Outage messages sent by B      : {outage_sent}")
    print(f"Backfilled via REST (after={last_seen_id}): {history_contents}")
    print(f"Backfilled message ids         : {history_ids}")
    print(f"Live post-reconnect delivery    : {live_received.contents()}")

    missing = [m for m in outage_sent if m not in history_contents]
    duplicate_ids = len(history_ids) != len(set(history_ids))
    live_ok = "post-reconnect-live" in live_received.contents()

    ok = not missing and not duplicate_ids and live_ok
    print()
    if ok:
        print(
            "PASS: every message B sent during the outage was recovered via history "
            "reconciliation with no duplicates, and A's live socket resumed receiving "
            "new broadcasts after reconnecting to the replacement pod."
        )
        return 0

    print("FAIL:")
    if missing:
        print(f"  - missing from backfill: {missing}")
    if duplicate_ids:
        print(f"  - duplicate message ids in backfill: {history_ids}")
    if not live_ok:
        print("  - live socket did not receive the post-reconnect message")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
