"""Integration tests for the room endpoints.

Mirrors `test_auth.py`: local helpers with `uuid4()`-unique data, driven over
ASGI with the `client` fixture, asserting status + body on every request.
"""

from uuid import uuid4


async def _register(client, email=None, username=None, password="supersecret123"):
    email = email or f"user-{uuid4()}@example.com"
    username = username or f"user_{uuid4().hex[:16]}"
    resp = await client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), email, username, password


async def _auth_headers(client, email, password):
    """Register's counterpart: log in and return the Bearer header."""
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_room(client, headers, name=None):
    name = name or f"room-{uuid4().hex[:8]}"
    resp = await client.post("/rooms", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json(), name


async def test_create_room_requires_auth(client):
    resp = await client.post("/rooms", json={"name": "no-auth"})
    assert resp.status_code == 401


async def test_create_room_auto_joins_creator(client):
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    room, name = await _create_room(client, headers)

    assert room["name"] == name
    assert "id" in room
    assert room["created_by"] is not None

    # The creator is automatically a member, so the room shows up in their list.
    listing = await client.get("/rooms", headers=headers)
    assert listing.status_code == 200
    assert room["id"] in {r["id"] for r in listing.json()}


async def test_list_rooms_only_returns_memberships(client):
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    room_a, _ = await _create_room(client, h1)
    room_b, _ = await _create_room(client, h1)

    # user2 joins only room A.
    assert (await client.post(f"/rooms/{room_a['id']}/join", headers=h2)).status_code == 201

    user2_ids = {r["id"] for r in (await client.get("/rooms", headers=h2)).json()}
    assert room_a["id"] in user2_ids
    assert room_b["id"] not in user2_ids

    user1_ids = {r["id"] for r in (await client.get("/rooms", headers=h1)).json()}
    assert room_a["id"] in user1_ids
    assert room_b["id"] in user1_ids


async def test_get_room_member_count(client):
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    room, _ = await _create_room(client, h1)

    detail = await client.get(f"/rooms/{room['id']}", headers=h1)
    assert detail.status_code == 200
    assert detail.json()["member_count"] == 1

    await client.post(f"/rooms/{room['id']}/join", headers=h2)

    detail = await client.get(f"/rooms/{room['id']}", headers=h1)
    assert detail.status_code == 200
    assert detail.json()["member_count"] == 2


async def test_get_room_unknown_returns_404(client):
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.get("/rooms/999999", headers=headers)
    assert resp.status_code == 404


async def test_join_room(client):
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    room, _ = await _create_room(client, h1)

    join = await client.post(f"/rooms/{room['id']}/join", headers=h2)
    assert join.status_code == 201
    body = join.json()
    assert body["room_id"] == room["id"]
    assert body["user_id"] > 0
    assert "joined_at" in body


async def test_join_unknown_room_returns_404(client):
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.post("/rooms/999999/join", headers=headers)
    assert resp.status_code == 404


async def test_join_already_member_returns_409(client):
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    room, _ = await _create_room(client, h1)

    assert (await client.post(f"/rooms/{room['id']}/join", headers=h2)).status_code == 201

    second = await client.post(f"/rooms/{room['id']}/join", headers=h2)
    assert second.status_code == 409
