"""Friend relationships and 1:1 DM rooms.

State machine (D1): ONE `user_relationships` row per unordered pair with
`status` in `pending | accepted | blocked`. Accepting a request creates the
pair's DM room inside the same transaction (F1-R4); DMs are `rooms` rows
with `kind='dm'` and the reserved `dm-{low}-{high}` name, so the whole
room-keyed messaging stack (Redis fan-out, WS, history, Drift cache) is
reused untouched.

Enumeration safety (F1-R1, D6): `send_friend_request` is a single linear
code path — rate limit first (existence-independent), then resolve the
username case-insensitively (>=2 matches count as no match), then query the
pair unconditionally. Every outcome that must not reveal account existence
returns the SAME 202 `{"status": "queued"}` body.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import (
    RateLimitExceeded,
    enforce_friend_request_rate_limit,
)
from app.core.slug import dm_room_name
from app.db.session import get_db
from app.models.room import Room, RoomKind
from app.models.room_membership import RoomMembership
from app.models.user import User
from app.models.user_relationship import RelationshipStatus, UserRelationship
from app.schemas.friends import (
    AcceptFriendRequestResponse,
    BlockedUserResponse,
    BlockUserRequest,
    FriendRequestQueued,
    FriendRequestResponse,
    FriendRequestSend,
    FriendResponse,
    PeerSummary,
)
from app.schemas.room import RoomResponse

router = APIRouter(prefix="/friends", tags=["friends"])


def _pair_ids(user_id_a: int, user_id_b: int) -> tuple[int, int]:
    """Normalize an unordered pair to (low, high) for the pair columns."""
    return sorted((user_id_a, user_id_b))


async def _relation_for_pair(
    db: AsyncSession, user_id_a: int, user_id_b: int
) -> UserRelationship | None:
    low, high = _pair_ids(user_id_a, user_id_b)
    return await db.scalar(
        select(UserRelationship).where(
            UserRelationship.user_low_id == low,
            UserRelationship.user_high_id == high,
        )
    )


async def _dm_room_id_for_pair(
    db: AsyncSession, user_id_a: int, user_id_b: int
) -> int | None:
    """The pair's DM room id, if its row exists (created only on accept)."""
    return await db.scalar(
        select(Room.id).where(Room.name == dm_room_name(user_id_a, user_id_b))
    )


async def _sever_dm_memberships(
    db: AsyncSession, user_id_a: int, user_id_b: int
) -> None:
    """Remove BOTH users' memberships from the pair's DM (row is retained).

    Used by remove-friend and block (F1-R3/R6): the DM disappears from both
    users' room lists while the room row and its message history are kept —
    no room-delete endpoint is in scope. Re-friending later reuses the row.
    """
    room_id = await _dm_room_id_for_pair(db, user_id_a, user_id_b)
    if room_id is None:
        return
    await db.execute(
        delete(RoomMembership).where(RoomMembership.room_id == room_id)
    )


async def _peer_usernames_by_relation(
    db: AsyncSession, user_id: int, relations: list[UserRelationship]
) -> dict[int, str]:
    """Map relation id -> the OTHER user's username for the caller's rows.

    The other side of a relation can be either column (the caller may be the
    low or the high id), so the join matches both and excludes the caller.
    This is what keeps username resolution relationship-scoped (F1-R7).
    """
    if not relations:
        return {}
    result = await db.execute(
        select(UserRelationship.id, User.id, User.username)
        .join(
            User,
            or_(
                User.id == UserRelationship.user_low_id,
                User.id == UserRelationship.user_high_id,
            ),
        )
        .where(
            UserRelationship.id.in_([r.id for r in relations]),
            User.id != user_id,
        )
    )
    peer_by_relation: dict[int, str] = {}
    for relation_id, _peer_id, username in result.all():
        peer_by_relation[relation_id] = username
    return peer_by_relation


def _peer_id_of(relation: UserRelationship, user_id: int) -> int:
    """The OTHER side of a pair row, regardless of column order."""
    return (
        relation.user_high_id
        if relation.user_low_id == user_id
        else relation.user_low_id
    )


# --- Request submission -----------------------------------------------------


@router.post(
    "/requests",
    response_model=FriendRequestQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_friend_request(
    payload: FriendRequestSend,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FriendRequestQueued:
    """Submit a friend request by username (F1-R1/R2/R3/R6).

    Single linear path, no early-exit on the no-match branch: the rate limit
    runs before resolution, and the pair-existence query runs unconditionally
    (id `0` when nothing resolved), so matched and unmatched requests do
    equivalent work before responding.
    """
    # F1-R2: existence-independent throttle, BEFORE any username work.
    try:
        await enforce_friend_request_rate_limit(user.id)
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many friend requests — try again later",
        ) from None

    # Resolve at most one account case-insensitively; >=2 matches (possible
    # because the DB unique is case-sensitive) are ambiguous -> no match.
    target_lower = payload.username.strip().lower()
    matches = list(
        (
            await db.execute(
                select(User).where(func.lower(User.username) == target_lower)
            )
        )
        .scalars()
        .all()
    )
    target = matches[0] if len(matches) == 1 else None

    # Self-request: a 4xx validation error revealing only the sender's own
    # username (F1-R1), never anything about another account.
    if target is not None and target.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You cannot send a friend request to yourself",
        )

    # Pair-existence query runs unconditionally: `0` is never a real user id,
    # so the no-match path performs the same query shape, not a quick exit.
    target_id = target.id if target is not None else 0
    relation = await _relation_for_pair(db, user.id, target_id)

    if target is None:
        # Unknown or ambiguous username: uniform "queued", nothing persisted.
        return FriendRequestQueued()

    if relation is None:
        low, high = _pair_ids(user.id, target.id)
        db.add(
            UserRelationship(
                user_low_id=low,
                user_high_id=high,
                status=RelationshipStatus.PENDING,
                actor_id=user.id,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            # A concurrent request for the same pair won the race.
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A friend request is already pending for this user",
            ) from None
        return FriendRequestQueued()

    if relation.status == RelationshipStatus.BLOCKED:
        if relation.actor_id == target.id:
            # The target blocked the sender: uniform "queued", nothing is
            # persisted and the blocked user is never notified (F1-R6).
            return FriendRequestQueued()
        # The sender is the blocker — they must unblock first.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have blocked this user — unblock before sending a request",
        )

    # Pending (either direction) or already friends: no second row (F1-R3).
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A friend request is already pending for this user",
    )


# --- Request lists ----------------------------------------------------------


@router.get("/requests", response_model=list[FriendRequestResponse])
async def list_friend_requests(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    direction: Literal["incoming", "outgoing"] = Query(...),
) -> list[FriendRequestResponse]:
    """Return the caller's pending requests, incoming or outgoing (F1-R3).

    The same row carries both directions: `actor_id` is the requester, so
    `direction=outgoing` is "rows I requested" and `direction=incoming` is
    "rows requested of me". Invalid `direction` values are rejected by the
    Literal type before the handler runs (422).
    """
    result = await db.execute(
        select(UserRelationship).where(
            UserRelationship.status == RelationshipStatus.PENDING,
            or_(
                UserRelationship.user_low_id == user.id,
                UserRelationship.user_high_id == user.id,
            ),
        )
    )
    relations = list(result.scalars().all())
    peers = await _peer_usernames_by_relation(db, user.id, relations)

    items: list[FriendRequestResponse] = []
    for relation in relations:
        is_outgoing = relation.actor_id == user.id
        if (direction == "outgoing") != is_outgoing:
            continue
        items.append(
            FriendRequestResponse(
                user_id=_peer_id_of(relation, user.id),
                username=peers[relation.id],
                created_at=relation.created_at,
            )
        )
    return items


# --- Accept / decline -------------------------------------------------------


@router.post(
    "/requests/{user_id}/accept",
    response_model=AcceptFriendRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_friend_request(
    user_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptFriendRequestResponse:
    """Accept an incoming request: friendship + DM in ONE transaction (F1-R4).

    The `FOR UPDATE` lock serializes concurrent accepts for the same pair;
    the loser re-reads a consumed row and gets a 409. Everything (request
    consumption, friendship, find-or-create of the `dm-{low}-{high}` room,
    both memberships) commits together or not at all.
    """
    peer = await db.get(User, user_id)
    if peer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No incoming friend request",
        )

    low, high = _pair_ids(user.id, user_id)
    relation = await db.scalar(
        select(UserRelationship)
        .where(
            UserRelationship.user_low_id == low,
            UserRelationship.user_high_id == high,
        )
        .with_for_update()
    )
    # None / my own outgoing request / blocked (block cancels requests): a
    # uniform "nothing to accept". Accepted is the racing-accept case.
    if (
        relation is None
        or relation.actor_id == user.id
        or relation.status == RelationshipStatus.BLOCKED
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No incoming friend request",
        )
    if relation.status == RelationshipStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already friends with this user",
        )

    relation.status = RelationshipStatus.ACCEPTED

    # Find-or-create the pair's DM room (reuse after remove keeps exactly one
    # DM per pair; the UNIQUE name constraint is the final guarantee).
    room = await db.scalar(
        select(Room).where(Room.name == dm_room_name(user.id, user_id))
    )
    if room is None:
        room = Room(name=dm_room_name(user.id, user_id), kind=RoomKind.DM)
        db.add(room)
        await db.flush()
    db.add_all(
        [
            RoomMembership(user_id=low, room_id=room.id),
            RoomMembership(user_id=high, room_id=room.id),
        ]
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conflicting relationship or room change won the race",
        ) from None
    await db.refresh(room)
    return AcceptFriendRequestResponse(
        peer=PeerSummary(user_id=peer.id, username=peer.username),
        room=RoomResponse.model_validate(room),
    )


@router.delete(
    "/requests/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def decline_friend_request(
    user_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Decline an incoming request (F1-R3): removes the pending row.

    After a decline the original requester MAY send a fresh request — no
    cooldown. A missing/consumed request is a 404; the caller cannot decline
    their own outgoing request through this route.
    """
    relation = await _relation_for_pair(db, user.id, user_id)
    if (
        relation is None
        or relation.status != RelationshipStatus.PENDING
        or relation.actor_id != user_id  # I must be the recipient
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No incoming friend request",
        )
    await db.delete(relation)
    await db.commit()
    return None


# --- Friends list / remove --------------------------------------------------


@router.get("", response_model=list[FriendResponse])
async def list_friends(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FriendResponse]:
    """Return the caller's friendships with each pair's DM room id (F1-R7)."""
    result = await db.execute(
        select(UserRelationship).where(
            UserRelationship.status == RelationshipStatus.ACCEPTED,
            or_(
                UserRelationship.user_low_id == user.id,
                UserRelationship.user_high_id == user.id,
            ),
        )
    )
    relations = list(result.scalars().all())
    peers = await _peer_usernames_by_relation(db, user.id, relations)

    items: list[FriendResponse] = []
    for relation in relations:
        peer_id = _peer_id_of(relation, user.id)
        room_id = await _dm_room_id_for_pair(db, user.id, peer_id)
        if room_id is None:
            # Accepted without a DM row is an invariant violation; skip it
            # rather than 500 the whole list.
            continue
        items.append(
            FriendResponse(
                user_id=peer_id,
                username=peers[relation.id],
                room_id=room_id,
            )
        )
    return items


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
    user_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Sever a friendship (F1-R3): relation gone, both DM memberships dropped.

    The DM room row and its message history are retained — the room simply
    becomes unreachable (no room-delete endpoint is in scope). Requires an
    existing friendship; anything else is a 404.
    """
    relation = await _relation_for_pair(db, user.id, user_id)
    if relation is None or relation.status != RelationshipStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not friends with this user",
        )
    await _sever_dm_memberships(db, user.id, user_id)
    await db.delete(relation)
    await db.commit()
    return None


# --- Blocks -----------------------------------------------------------------


@router.post("/blocks", status_code=status.HTTP_204_NO_CONTENT)
async def block_user(
    payload: BlockUserRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Block a user with whom the caller has a relation (F1-R6).

    Atomically: the pending request (either direction) or friendship becomes
    `blocked` with the caller as actor, and — when a friendship existed —
    both users' DM memberships are removed (frozen, history retained). There
    is no block-by-arbitrary-username surface: no existing relation -> 404.
    """
    relation = await _relation_for_pair(db, user.id, payload.user_id)
    if relation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No relationship with this user",
        )
    if relation.status == RelationshipStatus.BLOCKED:
        if relation.actor_id == user.id:
            return None  # already blocked — idempotent
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No relationship with this user",
        )
    if relation.status == RelationshipStatus.ACCEPTED:
        await _sever_dm_memberships(db, user.id, payload.user_id)
    relation.status = RelationshipStatus.BLOCKED
    relation.actor_id = user.id
    await db.commit()
    return None


@router.get("/blocks", response_model=list[BlockedUserResponse])
async def list_blocked_users(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BlockedUserResponse]:
    """Return the users the caller has blocked (F1-R6, the unblock list)."""
    result = await db.execute(
        select(UserRelationship).where(
            UserRelationship.status == RelationshipStatus.BLOCKED,
            UserRelationship.actor_id == user.id,
        )
    )
    relations = list(result.scalars().all())
    peers = await _peer_usernames_by_relation(db, user.id, relations)
    items: list[BlockedUserResponse] = []
    for relation in relations:
        items.append(
            BlockedUserResponse(
                user_id=_peer_id_of(relation, user.id),
                username=peers[relation.id],
            )
        )
    return items


@router.delete(
    "/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def unblock_user(
    user_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Unblock a user the caller blocked (F1-R6).

    Deletes the blocked row and restores normal rules — it does NOT restore
    any friendship automatically; the previously blocked user may send a
    fresh request under the ordinary flow.
    """
    relation = await _relation_for_pair(db, user.id, user_id)
    if (
        relation is None
        or relation.status != RelationshipStatus.BLOCKED
        or relation.actor_id != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This user is not blocked",
        )
    await db.delete(relation)
    await db.commit()
    return None
