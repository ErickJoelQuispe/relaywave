"""Integration tests for the room endpoints.

Mirrors `test_auth.py`: local helpers with `uuid4()`-unique data, driven over
ASGI with the `client` fixture, asserting status + body on every request.
"""

from uuid import uuid4

from app.models.message import Message
from app.models.room import Room, RoomKind
from app.models.room_membership import RoomMembership


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


async def test_join_is_allowed_beyond_capacity(client):
    """F3-R3-S1: capacity is display-only; a 3rd+ member joins past capacity."""
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    _, email3, _, _ = await _register(client)
    _, email4, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)
    h3 = await _auth_headers(client, email3, password)
    h4 = await _auth_headers(client, email4, password)

    resp = await client.post(
        "/rooms", json={"name": "cap-room", "capacity": 2}, headers=h1
    )
    assert resp.status_code == 201, resp.text
    room = resp.json()

    # Member 2 fills the capacity; member 3 overshoots it by numeric id.
    assert (await client.post(f"/rooms/{room['id']}/join", headers=h2)).status_code == 201
    assert (await client.post(f"/rooms/{room['id']}/join", headers=h3)).status_code == 201

    # Member 4 joins via the slug/name lookup path, still beyond capacity.
    by_name = await client.get("/rooms/by-name/cap-room", headers=h4)
    assert by_name.status_code == 200
    assert by_name.json()["id"] == room["id"]
    assert (await client.post(f"/rooms/{room['id']}/join", headers=h4)).status_code == 201

    # capacity stays 2 (display-only) and member_count tracks reality.
    detail = await client.get(f"/rooms/{room['id']}", headers=h1)
    assert detail.status_code == 200
    assert detail.json()["capacity"] == 2
    assert detail.json()["member_count"] == 4


async def test_list_messages_requires_auth(client):
    resp = await client.get("/rooms/1/messages")
    assert resp.status_code == 401


async def test_list_messages_unknown_room_returns_404(client):
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.get("/rooms/999999/messages", headers=headers)
    assert resp.status_code == 404


async def test_list_messages_requires_membership(client):
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    room, _ = await _create_room(client, h1)  # user2 never joins

    resp = await client.get(f"/rooms/{room['id']}/messages", headers=h2)
    assert resp.status_code == 403


async def test_list_messages_returns_history_after_id_ordered(client, db):
    user, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)
    room, _ = await _create_room(client, headers)

    messages = [
        Message(room_id=room["id"], sender_id=user["id"], content=f"msg-{i}")
        for i in range(3)
    ]
    db.add_all(messages)
    await db.commit()
    for m in messages:
        await db.refresh(m)

    # Default `after=0` returns the full history, oldest first.
    resp = await client.get(f"/rooms/{room['id']}/messages", headers=headers)
    assert resp.status_code == 200
    assert [m["content"] for m in resp.json()] == ["msg-0", "msg-1", "msg-2"]

    # Reconciliation: only messages after a given id come back.
    resp = await client.get(
        f"/rooms/{room['id']}/messages",
        params={"after": messages[0].id},
        headers=headers,
    )
    assert [m["content"] for m in resp.json()] == ["msg-1", "msg-2"]


async def test_list_messages_respects_limit(client, db):
    user, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)
    room, _ = await _create_room(client, headers)

    db.add_all(
        [
            Message(room_id=room["id"], sender_id=user["id"], content=f"msg-{i}")
            for i in range(5)
        ]
    )
    await db.commit()

    resp = await client.get(
        f"/rooms/{room['id']}/messages", params={"limit": 2}, headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_create_room_canonicalizes_free_text_name(client):
    """F2-R2: 'Project Alpha!' is stored and returned as 'project-alpha'."""
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.post("/rooms", json={"name": "Project Alpha!"}, headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "project-alpha"


async def test_create_room_duplicate_slug_returns_409(client):
    """F2-R2: a canonical slug collision is a 409, never an auto-suffix."""
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    first = await client.post("/rooms", json={"name": "Work"}, headers=h1)
    assert first.status_code == 201
    assert first.json()["name"] == "work"

    # Same canonical slug from a different user, written differently.
    for dup_name in ("work", "WORK", " Work! "):
        dup = await client.post("/rooms", json={"name": dup_name}, headers=h2)
        assert dup.status_code == 409, dup.text


async def test_create_room_reserved_prefix_returns_422(client):
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    # 'dm-' is reserved for DM auto-names (F2-R3); 'DM-Buddy' canonicalizes
    # to 'dm-buddy', which must also be rejected.
    for name in ("dm-buddy", "DM-Buddy"):
        resp = await client.post("/rooms", json={"name": name}, headers=headers)
        assert resp.status_code == 422, resp.text


async def test_create_room_all_numeric_name_returns_422(client):
    """F2-R2: the numeric-only space belongs to the id namespace."""
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.post("/rooms", json={"name": "123"}, headers=headers)
    assert resp.status_code == 422, resp.text


async def test_create_room_empty_canonical_name_returns_422(client):
    """F2-R2: a name with no ASCII alphanumeric canonicalizes to '' -> 422."""
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.post("/rooms", json={"name": "!!!"}, headers=headers)
    assert resp.status_code == 422, resp.text


async def test_create_room_rejects_non_positive_capacity(client):
    """F3-R3: capacity is validated gt=0 at create time (metadata only)."""
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    for capacity in (0, -3):
        resp = await client.post(
            "/rooms", json={"name": "cap-room", "capacity": capacity}, headers=headers
        )
        assert resp.status_code == 422, resp.text


async def test_get_room_by_name_resolves_canonical_slug(client):
    """F2-R5: lookup canonicalizes input and works for a non-member."""
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)

    room, _ = await _create_room(client, h1, name="Project Alpha!")

    # Case-insensitive by construction; user2 is NOT a member.
    resp = await client.get("/rooms/by-name/PROJECT-ALPHA", headers=h2)
    assert resp.status_code == 200
    assert resp.json()["id"] == room["id"]
    assert resp.json()["name"] == "project-alpha"


async def test_get_room_by_name_unknown_returns_404(client):
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.get("/rooms/by-name/no-such-room", headers=headers)
    assert resp.status_code == 404


async def test_get_room_by_name_dm_slug_returns_404(client, db):
    """F1-R5/F2-R5: DM names are never resolvable through alias lookup."""
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    dm = Room(name="dm-5-12", kind=RoomKind.DM, created_by=None)
    db.add(dm)
    await db.commit()

    resp = await client.get("/rooms/by-name/dm-5-12", headers=headers)
    assert resp.status_code == 404


async def _make_dm_room(client, db, user1, user2):
    """Build a DM row + memberships the way the accept flow does (F1-R4)."""
    low, high = sorted((user1["id"], user2["id"]))
    dm = Room(name=f"dm-{low}-{high}", kind=RoomKind.DM, created_by=None)
    db.add(dm)
    await db.commit()
    await db.refresh(dm)
    db.add_all(
        [
            RoomMembership(user_id=user1["id"], room_id=dm.id),
            RoomMembership(user_id=user2["id"], room_id=dm.id),
        ]
    )
    await db.commit()
    return dm


async def test_join_dm_room_returns_404_even_for_a_member(client, db):
    """F1-R5: DM rooms are never open-joinable, even by their own pair."""
    user1, email1, _, password = await _register(client)
    user2, email2, _, _ = await _register(client)
    user3, email3, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h2 = await _auth_headers(client, email2, password)
    h3 = await _auth_headers(client, email3, password)

    dm = await _make_dm_room(client, db, user1, user2)

    # A non-member who learned the numeric id, and the members themselves,
    # all get the same uniform 404.
    for h in (h1, h2, h3):
        resp = await client.post(f"/rooms/{dm.id}/join", headers=h)
        assert resp.status_code == 404, resp.text

    # No membership was minted for user3.
    listing = await client.get("/rooms", headers=h3)
    assert dm.id not in {r["id"] for r in listing.json()}


async def test_get_room_dm_non_member_returns_404(client, db):
    """F1-R5: DM detail is closed to non-members with a uniform 404."""
    user1, email1, _, password = await _register(client)
    user2, email2, _, _ = await _register(client)
    user3, email3, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h3 = await _auth_headers(client, email3, password)

    dm = await _make_dm_room(client, db, user1, user2)

    member = await client.get(f"/rooms/{dm.id}", headers=h1)
    assert member.status_code == 200
    non_member = await client.get(f"/rooms/{dm.id}", headers=h3)
    assert non_member.status_code == 404


async def test_get_room_dm_messages_non_member_returns_403(client, db):
    """F1-R5: the existing membership gate already closes DM history reads."""
    user1, email1, _, password = await _register(client)
    user2, email2, _, _ = await _register(client)
    user3, email3, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)
    h3 = await _auth_headers(client, email3, password)

    dm = await _make_dm_room(client, db, user1, user2)

    member = await client.get(f"/rooms/{dm.id}/messages", headers=h1)
    assert member.status_code == 200
    non_member = await client.get(f"/rooms/{dm.id}/messages", headers=h3)
    assert non_member.status_code == 403


async def test_create_room_cannot_mint_a_dm(client):
    """F1-R5/F2-R2: kind is server-set; a client payload cannot create 'dm'."""
    _, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await client.post(
        "/rooms",
        json={"name": "Some Group", "kind": "dm", "capacity": 2},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    # The server decides the kind; extra keys are ignored.
    assert resp.json()["kind"] == "group"
    assert resp.json()["name"] == "some-group"


async def test_list_exposes_kind_and_peer_username(client, db):
    """F1-R7/F3-R1: list rows carry kind; DM rows carry the peer username."""
    user1, email1, _, password = await _register(client)
    user2, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)

    group, _ = await _create_room(client, h1, name="Project Alpha!")

    # Build a DM room the way the accept flow will (PR3): one row with the
    # auto-name dm-{low}-{high}, created_by NULL, both users joined.
    low, high = sorted((user1["id"], user2["id"]))
    dm = Room(name=f"dm-{low}-{high}", kind=RoomKind.DM, created_by=None)
    db.add(dm)
    await db.commit()
    await db.refresh(dm)
    db.add_all(
        [
            RoomMembership(user_id=user1["id"], room_id=dm.id),
            RoomMembership(user_id=user2["id"], room_id=dm.id),
        ]
    )
    await db.commit()

    listing = await client.get("/rooms", headers=h1)
    assert listing.status_code == 200
    by_id = {r["id"]: r for r in listing.json()}

    assert by_id[group["id"]]["kind"] == "group"
    assert by_id[group["id"]]["peer_username"] is None
    assert by_id[dm.id]["kind"] == "dm"
    assert by_id[dm.id]["peer_username"] == user2["username"]
    assert by_id[dm.id]["name"] == f"dm-{low}-{high}"  # never displayed client-side


async def test_get_room_detail_exposes_kind_capacity_and_peer(client):
    """F3-R3/F1-R7: detail carries kind + capacity; DM detail names the peer."""
    _, email1, _, password = await _register(client)
    _, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)

    resp = await client.post(
        "/rooms", json={"name": "Cap Room", "capacity": 10}, headers=h1
    )
    assert resp.status_code == 201, resp.text
    room = resp.json()

    detail = await client.get(f"/rooms/{room['id']}", headers=h1)
    assert detail.status_code == 200
    body = detail.json()
    assert body["kind"] == "group"
    assert body["capacity"] == 10
    assert body["member_count"] == 1
    assert body["peer_username"] is None


async def test_get_room_detail_dm_names_peer(client, db):
    """F3-R1: a DM row's detail resolves peer_username for a member."""
    user1, email1, _, password = await _register(client)
    user2, email2, _, _ = await _register(client)
    h1 = await _auth_headers(client, email1, password)

    dm = Room(
        name=f"dm-{min(user1['id'], user2['id'])}-{max(user1['id'], user2['id'])}",
        kind=RoomKind.DM,
        created_by=None,
    )
    db.add(dm)
    await db.commit()
    await db.refresh(dm)
    db.add_all(
        [
            RoomMembership(user_id=user1["id"], room_id=dm.id),
            RoomMembership(user_id=user2["id"], room_id=dm.id),
        ]
    )
    await db.commit()

    detail = await client.get(f"/rooms/{dm.id}", headers=h1)
    assert detail.status_code == 200
    body = detail.json()
    assert body["kind"] == "dm"
    assert body["capacity"] is None
    assert body["member_count"] == 2
    assert body["peer_username"] == user2["username"]
