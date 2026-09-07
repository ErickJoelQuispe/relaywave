"""Integration tests for the friends/DM endpoints (F1-R1..R7).

Driven over ASGI like test_rooms.py, with direct DB assertions where the
spec cares about persisted state (no room before accept, exactly one DM per
pair, memberships severed on remove/block, history retained). Concurrency
(F1-R4) uses the `two_sessions` fixture plus real Postgres row locks by
calling the route handler directly — the shared `db` fixture yields one
session and cannot express a race.
"""

import asyncio
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.routes.friends import accept_friend_request
from app.models.room import Room
from app.models.room_membership import RoomMembership
from app.models.user import User
from app.models.user_relationship import RelationshipStatus, UserRelationship
from app.schemas.friends import AcceptFriendRequestResponse


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
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _send(client, headers, username):
    return await client.post(
        "/friends/requests", json={"username": username}, headers=headers
    )


async def _make_friends(client, a, b, h_a, h_b):
    """A requests B and B accepts; returns the accept body."""
    assert (await _send(client, h_a, b["username"])).status_code == 202
    accept = await client.post(
        f"/friends/requests/{a['id']}/accept", headers=h_b
    )
    assert accept.status_code == 201, accept.text
    return accept.json()


def _relation_count(db):
    return db.scalar(select(func.count()).select_from(UserRelationship))


async def _dm_room_ids(db, user_a_id, user_b_id):
    """All room ids whose name is this pair's DM auto-name."""
    low, high = sorted((user_a_id, user_b_id))
    rows = await db.execute(
        select(Room.id).where(Room.name == f"dm-{low}-{high}")
    )
    return list(rows.scalars().all())


# --- F1-R1: enumeration-safe, uniform request submission --------------------


async def test_request_to_unknown_username_is_queued_and_persists_nothing(
    client, db
):
    user, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await _send(client, headers, "no-such-user-anywhere")
    assert resp.status_code == 202
    assert resp.json() == {"status": "queued"}
    assert await _relation_count(db) == 0


async def test_request_to_known_and_unknown_username_are_identical(client, db):
    sender, email_s, _, password_s = await _register(client)
    target, _, _, _ = await _register(client)
    h_s = await _auth_headers(client, email_s, password_s)

    known = await _send(client, h_s, target["username"])
    unknown = await _send(client, h_s, "totally-unknown-username")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"status": "queued"}

    # The known one persisted exactly one pending request; the unknown one
    # persisted nothing more.
    assert await _relation_count(db) == 1
    relation = (
        await db.execute(select(UserRelationship))
    ).scalars().one()
    assert relation.status == RelationshipStatus.PENDING
    assert relation.actor_id == sender["id"]


async def test_case_differing_accounts_are_ambiguous(client, db):
    # The DB username unique is case-sensitive, so "alice" and "Alice" can
    # both register. A request for "ALICE" must be treated as ambiguous.
    _, email_a, _, _ = await _register(client, username="alice")
    await _register(client, username="Alice")
    _, email_s, _, password_s = await _register(client)
    h_s = await _auth_headers(client, email_s, password_s)

    resp = await _send(client, h_s, "ALICE")
    assert resp.status_code == 202
    assert resp.json() == {"status": "queued"}
    assert await _relation_count(db) == 0


async def test_self_request_is_rejected_with_422(client, db):
    user, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)

    resp = await _send(client, headers, user["username"])
    assert resp.status_code == 422
    # Case-variant of the caller's own username is still themselves when
    # unambiguous.
    resp = await _send(client, headers, user["username"].upper())
    assert resp.status_code == 422
    assert await _relation_count(db) == 0


# --- F1-R2: per-sender rate limiting ----------------------------------------


async def test_rate_limit_throttles_bulk_probing(client):
    sender, email, _, password = await _register(client)
    headers = await _auth_headers(client, email, password)
    target, _, _, _ = await _register(client)

    for i in range(20):
        resp = await _send(client, headers, f"probe-user-{i}")
        assert resp.status_code == 202, f"request {i}: {resp.status_code}"

    # The 21st request is throttled whether or not the username exists.
    throttled = await _send(client, headers, "another-probe-user")
    assert throttled.status_code == 429
    throttled_real = await _send(client, headers, target["username"])
    assert throttled_real.status_code == 429


# --- F1-R3: relationship state machine --------------------------------------


async def test_duplicate_and_reverse_pending_requests_conflict(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    assert (await _send(client, h_a, b["username"])).status_code == 202
    duplicate = await _send(client, h_a, b["username"])
    assert duplicate.status_code == 409
    reverse = await _send(client, h_b, a["username"])
    assert reverse.status_code == 409

    assert await _relation_count(db) == 1


async def test_decline_then_requester_may_send_again(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    assert (await _send(client, h_a, b["username"])).status_code == 202
    declined = await client.delete(f"/friends/requests/{a['id']}", headers=h_b)
    assert declined.status_code == 204
    assert await _relation_count(db) == 0

    # The requester may submit a fresh request — no cooldown.
    assert (await _send(client, h_a, b["username"])).status_code == 202
    assert await _relation_count(db) == 1


async def test_remove_friend_severs_friendship_and_dm_memberships(
    client, db
):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    accept = await _make_friends(client, a, b, h_a, h_b)
    dm_id = accept["room"]["id"]

    # A message exists in the DM before the removal.
    from app.models.message import Message

    db.add(Message(room_id=dm_id, sender_id=a["id"], content="history survives"))
    await db.commit()

    removed = await client.delete(f"/friends/{b['id']}", headers=h_a)
    assert removed.status_code == 204

    # Friendship gone; both DM memberships gone; room row + history retained.
    assert await _relation_count(db) == 0
    memberships = (
        await db.execute(
            select(func.count()).select_from(RoomMembership).where(
                RoomMembership.room_id == dm_id
            )
        )
    ).scalar()
    assert memberships == 0
    assert await db.get(Room, dm_id) is not None
    message_count = await db.scalar(
        select(func.count()).select_from(Message).where(Message.room_id == dm_id)
    )
    assert message_count == 1

    # The DM is unreachable from both room lists now.
    for h in (h_a, h_b):
        listing = await client.get("/rooms", headers=h)
        assert dm_id not in {r["id"] for r in listing.json()}


# --- F1-R4: accept creates exactly one DM, transactionally -------------------


async def test_request_alone_never_creates_a_room(client, db):
    a, email_a, _, password_a = await _register(client)
    b, _, _, _ = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)

    assert (await _send(client, h_a, b["username"])).status_code == 202

    # No room, no membership for the pair before acceptance.
    assert await _dm_room_ids(db, a["id"], b["id"]) == []
    assert (
        await db.scalar(select(func.count()).select_from(RoomMembership))
    ) == 0


async def test_accept_creates_friendship_and_single_dm_with_both_members(
    client, db
):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    accept = await _make_friends(client, a, b, h_a, h_b)

    # B accepted A's request, so the peer in B's response is A.
    assert accept["peer"] == {"user_id": a["id"], "username": a["username"]}
    room = accept["room"]
    assert room["kind"] == "dm"
    assert room["created_by"] is None
    assert room["name"] == f"dm-{min(a['id'], b['id'])}-{max(a['id'], b['id'])}"

    assert await _dm_room_ids(db, a["id"], b["id"]) == [room["id"]]
    member_count = (
        await db.execute(
            select(func.count())
            .select_from(RoomMembership)
            .where(RoomMembership.room_id == room["id"])
        )
    ).scalar()
    assert member_count == 2

    # Both users see each other on their friends list.
    for h, peer_id in ((h_a, b["id"]), (h_b, a["id"])):
        friends = await client.get("/friends", headers=h)
        assert friends.status_code == 200
        assert any(f["user_id"] == peer_id for f in friends.json())
        assert friends.json()[0]["room_id"] == room["id"]


async def test_accept_is_transactional_single_commit(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)

    assert (await _send(client, h_a, b["username"])).status_code == 202
    # B never exists as a valid accept target for a stranger... but a request
    # from someone who is NOT the recipient cannot accept: C tries.
    c, email_c, _, password_c = await _register(client)
    h_c = await _auth_headers(client, email_c, password_c)
    bad = await client.post(f"/friends/requests/{a['id']}/accept", headers=h_c)
    assert bad.status_code == 404
    # Nothing was created for the pair.
    assert await _dm_room_ids(db, a["id"], b["id"]) == []
    assert await _relation_count(db) == 1  # still just the pending request


async def test_concurrent_accepts_produce_one_friendship_and_one_dm(
    client, two_sessions, db
):
    a, email_a, _, password_a = await _register(client)
    b, _, _, _ = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)

    assert (await _send(client, h_a, b["username"])).status_code == 202

    s1, s2 = two_sessions
    user_b_s1 = await s1.get(User, b["id"])
    user_b_s2 = await s2.get(User, b["id"])

    results = await asyncio.gather(
        accept_friend_request(user_id=a["id"], user=user_b_s1, db=s1),
        accept_friend_request(user_id=a["id"], user=user_b_s2, db=s2),
        return_exceptions=True,
    )
    successes = [
        r for r in results if isinstance(r, AcceptFriendRequestResponse)
    ]
    conflicts = [
        r for r in results if isinstance(r, HTTPException) and r.status_code == 409
    ]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results

    # Exactly one friendship and exactly one DM row survive.
    accepted = await db.scalar(
        select(func.count())
        .select_from(UserRelationship)
        .where(UserRelationship.status == RelationshipStatus.ACCEPTED)
    )
    assert accepted == 1
    assert len(await _dm_room_ids(db, a["id"], b["id"])) == 1


async def test_refriending_reuses_the_pair_dm(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    first = await _make_friends(client, a, b, h_a, h_b)
    dm_id = first["room"]["id"]

    assert (await client.delete(f"/friends/{b['id']}", headers=h_a)).status_code == 204

    # B requests A; A accepts. The existing DM row is reused — no second room.
    assert (await _send(client, h_b, a["username"])).status_code == 202
    accept = await client.post(f"/friends/requests/{b['id']}/accept", headers=h_a)
    assert accept.status_code == 201, accept.text
    assert accept.json()["room"]["id"] == dm_id
    assert await _dm_room_ids(db, a["id"], b["id"]) == [dm_id]
    member_count = (
        await db.execute(
            select(func.count())
            .select_from(RoomMembership)
            .where(RoomMembership.room_id == dm_id)
        )
    ).scalar()
    assert member_count == 2


# --- F1-R6: blocking --------------------------------------------------------


async def test_block_cancels_pending_request(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    assert (await _send(client, h_a, b["username"])).status_code == 202
    blocked = await client.post(
        "/friends/blocks", json={"user_id": a["id"]}, headers=h_b
    )
    assert blocked.status_code == 204

    row = (await db.execute(select(UserRelationship))).scalars().one()
    assert row.status == RelationshipStatus.BLOCKED
    assert row.actor_id == b["id"]

    # The blocked user's new request is uniformly queued and NOT persisted.
    queued = await _send(client, h_a, b["username"])
    assert queued.status_code == 202
    assert queued.json() == {"status": "queued"}
    unknown = await _send(client, h_a, "some-unknown-user")
    assert queued.status_code == unknown.status_code == 202
    assert queued.json() == unknown.json()
    assert await _relation_count(db) == 1  # still just the blocked row


async def test_block_severs_friendship_and_dm_memberships(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    accept = await _make_friends(client, a, b, h_a, h_b)
    dm_id = accept["room"]["id"]

    blocked = await client.post(
        "/friends/blocks", json={"user_id": a["id"]}, headers=h_b
    )
    assert blocked.status_code == 204

    memberships = (
        await db.execute(
            select(func.count()).select_from(RoomMembership).where(
                RoomMembership.room_id == dm_id
            )
        )
    ).scalar()
    assert memberships == 0
    for h in (h_a, h_b):
        listing = await client.get("/rooms", headers=h)
        assert dm_id not in {r["id"] for r in listing.json()}


async def test_block_requires_an_existing_relationship(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)

    resp = await client.post(
        "/friends/blocks", json={"user_id": b["id"]}, headers=h_a
    )
    assert resp.status_code == 404
    assert await _relation_count(db) == 0


async def test_unblock_restores_normal_rules(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)

    assert (await _send(client, h_a, b["username"])).status_code == 202
    assert (
        await client.post(
            "/friends/blocks", json={"user_id": a["id"]}, headers=h_b
        )
    ).status_code == 204

    # The blocker sees the blocked user on their list and can unblock.
    blocked_list = await client.get("/friends/blocks", headers=h_b)
    assert blocked_list.status_code == 200
    assert blocked_list.json() == [
        {"user_id": a["id"], "username": a["username"]}
    ]

    assert (
        await client.delete(f"/friends/blocks/{a['id']}", headers=h_b)
    ).status_code == 204
    assert await _relation_count(db) == 0

    # Normal rules restored: A's fresh request becomes pending again.
    assert (await _send(client, h_a, b["username"])).status_code == 202
    assert await _relation_count(db) == 1


# --- F1-R7: relationship-scoped lists ---------------------------------------


async def test_request_lists_split_incoming_and_outgoing(client, db):
    a, email_a, _, password_a = await _register(client)
    b, email_b, _, password_b = await _register(client)
    c, email_c, _, password_c = await _register(client)
    h_a = await _auth_headers(client, email_a, password_a)
    h_b = await _auth_headers(client, email_b, password_b)
    h_c = await _auth_headers(client, email_c, password_c)

    # A -> B and C -> B: B has two incoming; A and C have one outgoing each.
    assert (await _send(client, h_a, b["username"])).status_code == 202
    assert (await _send(client, h_c, b["username"])).status_code == 202

    incoming_b = await client.get(
        "/friends/requests", params={"direction": "incoming"}, headers=h_b
    )
    assert incoming_b.status_code == 200
    assert {r["user_id"] for r in incoming_b.json()} == {a["id"], c["id"]}
    usernames = {r["username"] for r in incoming_b.json()}
    assert usernames == {a["username"], c["username"]}
    assert all("created_at" in r for r in incoming_b.json())

    outgoing_a = await client.get(
        "/friends/requests", params={"direction": "outgoing"}, headers=h_a
    )
    assert outgoing_a.status_code == 200
    assert [r["user_id"] for r in outgoing_a.json()] == [b["id"]]

    # No request is visible from an unrelated side.
    outgoing_c = await client.get(
        "/friends/requests", params={"direction": "outgoing"}, headers=h_c
    )
    assert [r["user_id"] for r in outgoing_c.json()] == [b["id"]]

    # Bad direction is rejected before the handler.
    bad = await client.get(
        "/friends/requests", params={"direction": "sideways"}, headers=h_a
    )
    assert bad.status_code == 422
