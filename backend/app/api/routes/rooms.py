"""Room endpoints: create, list, detail, join, and message history.

Every route is protected by `get_current_user`, so a valid access token is
required. Rooms and memberships were modeled back in the persistence slice;
this module is where they become a real REST surface.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.slug import canonical_slug
from app.db.session import get_db
from app.models.message import Message
from app.models.room import Room, RoomKind
from app.models.room_membership import RoomMembership
from app.models.user import User
from app.schemas.message import MessageResponse
from app.schemas.room import (
    RoomCreate,
    RoomDetailResponse,
    RoomMembershipResponse,
    RoomResponse,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post(
    "", response_model=RoomResponse, status_code=status.HTTP_201_CREATED
)
async def create_room(
    payload: RoomCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Room:
    """Create a group room and add the creator as its first member.

    Appending the membership to `room.memberships` leans on the ORM: the
    relationship's default `save-update` cascade inserts the membership row
    alongside the room, and `back_populates` wires `membership.room = room`.
    One `db.add(room)` + one commit persists both.

    `payload.name` arrives already canonicalized by `RoomCreate`'s validator
    (F2-R2). The UNIQUE constraint on `rooms.name` (uq_rooms_name, M3) is
    the real collision guarantee; the `IntegrityError` handler below is the
    safety net for the race where two creates pass validation and collide —
    mapped to a 409 just like the duplicate-join path.
    """
    room = Room(name=payload.name, created_by=user.id, capacity=payload.capacity)
    room.memberships.append(RoomMembership(user_id=user.id))
    db.add(room)
    try:
        await db.commit()
    except IntegrityError:
        # The unique room-name constraint won the race.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A room with this name already exists — choose a distinct name",
        ) from None
    # Re-read to populate `created_at` (a server default) before returning.
    await db.refresh(room)
    return room


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Room]:
    """Return the rooms the current user is a member of, most recent first.

    This is the home-screen query: a user should not see rooms they are not
    in. "Discover all rooms" would be a separate endpoint (future work).
    """
    result = await db.execute(
        select(Room)
        .join(RoomMembership, RoomMembership.room_id == Room.id)
        .where(RoomMembership.user_id == user.id)
        .order_by(Room.created_at.desc(), Room.id.desc())
    )
    return list(result.scalars().all())


@router.get("/by-name/{name}", response_model=RoomResponse)
async def get_room_by_name(
    name: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Room:
    """Resolve a canonical room slug to a room (F2-R5).

    The join UI accepts free text; all-numeric input takes the numeric-id
    path, everything else is canonicalized and looked up here, after which
    the caller reuses the existing id-based join. Lookup resolves ONLY
    `kind='group'` rooms: an unknown slug, an invalid canonical form, or a
    `dm-` auto-name all fall out of the WHERE clause and produce the same
    uniform 404, so DM rooms are never resolvable by alias (F1-R5) and the
    endpoint never reveals whether a name exists.
    """
    slug = canonical_slug(name)
    result = await db.execute(
        select(Room).where(Room.name == slug, Room.kind == RoomKind.GROUP)
    )
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )
    return room


@router.get("/{room_id}", response_model=RoomDetailResponse)
async def get_room(
    room_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Room:
    """Return a single room with its member count.

    `selectinload` eagerly loads `memberships` in a second query so
    `Room.member_count` (a plain `len(...)`) does not trigger lazy loading —
    which is impossible in async and would raise `MissingGreenlet`.
    """
    result = await db.execute(
        select(Room)
        .options(selectinload(Room.memberships))
        .where(Room.id == room_id)
    )
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )
    return room


@router.post(
    "/{room_id}/join",
    response_model=RoomMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def join_room(
    room_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RoomMembership:
    """Add the current user as a member of an existing room.

    The composite primary key `(user_id, room_id)` enforces uniqueness at the
    database level, so a duplicate join raises `IntegrityError`; we map that to
    a friendly 409 rather than leaking a raw constraint error.
    """
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )

    # Pre-check gives a friendly 409 in the common case. The composite PK is
    # the real guarantee; the `IntegrityError` handler below is the safety net
    # for the race where two requests both pass this check and collide.
    already_member = await db.scalar(
        select(RoomMembership).where(
            RoomMembership.user_id == user.id,
            RoomMembership.room_id == room_id,
        )
    )
    if already_member is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already a member"
        )

    membership = RoomMembership(user_id=user.id, room_id=room_id)
    db.add(membership)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already a member"
        ) from None
    # Re-read to populate `joined_at` (a server default) before returning.
    await db.refresh(membership)
    return membership


@router.get("/{room_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    room_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Message]:
    """Return messages with `id > after`, oldest first, capped at `limit`.

    This is the history-reconciliation endpoint from ADR-002: best-effort
    WebSocket delivery means a client that was briefly disconnected can miss
    broadcasts, so on reconnect it calls this with the highest message `id`
    it already has and fills the gap. `after=0` (the default) doubles as
    "give me the room's full history" for a client with nothing cached yet.
    The `(room_id, id)` composite index from the persistence slice exists
    specifically to make this query — filter by room, range-scan by id —
    fast without a full table scan.
    """
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )

    is_member = await db.scalar(
        select(RoomMembership).where(
            RoomMembership.user_id == user.id,
            RoomMembership.room_id == room_id,
        )
    )
    if is_member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this room"
        )

    result = await db.execute(
        select(Message)
        .where(Message.room_id == room_id, Message.id > after)
        .order_by(Message.id)
        .limit(limit)
    )
    return list(result.scalars().all())
