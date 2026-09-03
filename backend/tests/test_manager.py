"""Unit tests for `ConnectionManager`'s local registry and broadcast rules.

No Redis or Postgres needed: `ConnectionManager` is a plain in-process
registry, and `connect`/`disconnect`'s return values are the only thing
`app/api/routes/ws.py` uses to decide when to subscribe/unsubscribe from
Redis (see app/ws/broadcaster.py). A fake stands in for `WebSocket` since
these tests never touch the network.
"""

from app.ws.manager import ConnectionManager


class _FakeWebSocket:
    """A hashable stand-in for `fastapi.WebSocket`; identity is all that
    matters for connection tracking, and `sent` records what `broadcast()`
    delivered so tests can assert on it directly.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, message: str) -> None:
        self.sent.append(message)


def test_first_connect_returns_true_second_returns_false():
    manager = ConnectionManager()
    room_id = 1
    ws_a, ws_b = _FakeWebSocket(), _FakeWebSocket()

    assert manager.connect(room_id, ws_a, user_id=1) is True
    assert manager.connect(room_id, ws_b, user_id=2) is False


def test_disconnect_returns_false_while_others_remain_true_when_last():
    manager = ConnectionManager()
    room_id = 1
    ws_a, ws_b = _FakeWebSocket(), _FakeWebSocket()
    manager.connect(room_id, ws_a, user_id=1)
    manager.connect(room_id, ws_b, user_id=2)

    assert manager.disconnect(room_id, ws_a) is False
    assert manager.disconnect(room_id, ws_b) is True


def test_disconnect_unknown_socket_is_a_no_op():
    manager = ConnectionManager()
    room_id = 1
    ws_a, ws_unknown = _FakeWebSocket(), _FakeWebSocket()
    manager.connect(room_id, ws_a, user_id=1)

    # A socket that was never registered in this room must not raise and
    # must not report the room as emptied out from under the real connection.
    assert manager.disconnect(room_id, ws_unknown) is False


async def test_broadcast_sends_to_every_local_connection():
    manager = ConnectionManager()
    room_id = 1
    ws_a, ws_b = _FakeWebSocket(), _FakeWebSocket()
    manager.connect(room_id, ws_a, user_id=1)
    manager.connect(room_id, ws_b, user_id=2)

    await manager.broadcast(room_id, "hello")

    assert ws_a.sent == ["hello"]
    assert ws_b.sent == ["hello"]


async def test_broadcast_exclude_skips_one_socket_object():
    manager = ConnectionManager()
    room_id = 1
    ws_a, ws_b = _FakeWebSocket(), _FakeWebSocket()
    manager.connect(room_id, ws_a, user_id=1)
    manager.connect(room_id, ws_b, user_id=2)

    await manager.broadcast(room_id, "hello", exclude=ws_a)

    assert ws_a.sent == []
    assert ws_b.sent == ["hello"]


async def test_broadcast_exclude_user_id_skips_every_socket_owned_by_that_user():
    """`exclude_user_id` must skip ALL local sockets owned by that user, not
    just one connection — the case it exists for is a user with two tabs
    open to the same room, who must not see their own typing indicator on
    either tab once the broadcast has round-tripped through Redis and the
    original `WebSocket` object that sent it is no longer available (see
    `_on_redis_message` in app/api/routes/ws.py).
    """
    manager = ConnectionManager()
    room_id = 1
    ws_a1, ws_a2, ws_b = _FakeWebSocket(), _FakeWebSocket(), _FakeWebSocket()
    manager.connect(room_id, ws_a1, user_id=1)
    manager.connect(room_id, ws_a2, user_id=1)  # user 1's second tab
    manager.connect(room_id, ws_b, user_id=2)

    await manager.broadcast(room_id, "typing", exclude_user_id=1)

    assert ws_a1.sent == []
    assert ws_a2.sent == []
    assert ws_b.sent == ["typing"]


async def test_broadcast_combines_exclude_and_exclude_user_id():
    manager = ConnectionManager()
    room_id = 1
    ws_a, ws_b, ws_c = _FakeWebSocket(), _FakeWebSocket(), _FakeWebSocket()
    manager.connect(room_id, ws_a, user_id=1)
    manager.connect(room_id, ws_b, user_id=2)
    manager.connect(room_id, ws_c, user_id=3)

    await manager.broadcast(room_id, "hello", exclude=ws_b, exclude_user_id=1)

    assert ws_a.sent == []
    assert ws_b.sent == []
    assert ws_c.sent == ["hello"]
