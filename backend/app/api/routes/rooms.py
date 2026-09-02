"""Room endpoints: create, list, detail, and join.

Every route is protected by `get_current_user`, so a valid access token is
required. Rooms and memberships were modeled back in the persistence slice;
this module is where they become a real REST surface.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.room import Room
from app.models.room_membership import RoomMembership
from app.models.user import User
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
    """Create a room and add the creator as its first member.

    Appending the membership to `room.memberships` leans on the ORM: the
    relationship's default `save-update` cascade inserts the membership row
    alongside the room, and `back_populates` wires `membership.room = room`.
    One `db.add(room)` + one commit persists both.
    """
    room = Room(name=payload.name, created_by=user.id)
    room.memberships.append(RoomMembership(user_id=user.id))
    db.add(room)
    await db.commit()
    # Re-read to populate `created_at` (a server default) before returning.
    await db.refresh(room)
    return room


@router.get("", response_model=list[RoomResponse])
async def list_rooms(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Room]:
    """Return the rooms the current user is a member of, oldest first.

    This is the home-screen query: a user should not see rooms they are not
    in. "Discover all rooms" would be a separate endpoint (future work).
    """
    result = await db.execute(
        select(Room)
        .join(RoomMembership, RoomMembership.room_id == Room.id)
        .where(RoomMembership.user_id == user.id)
        .order_by(Room.created_at, Room.id)
    )
    return list(result.scalars().all())


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
