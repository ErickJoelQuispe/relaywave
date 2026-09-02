"""Request/response models for the room endpoints.

Same boundary as `schemas/auth.py`: these describe the wire contract, while the
SQLAlchemy models describe how rows map to tables. Route handlers stay thin and
the API surface stays explicit.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoomCreate(BaseModel):
    """Payload for `POST /rooms`."""

    name: str = Field(min_length=1, max_length=100)


class RoomResponse(BaseModel):
    """Public representation of a room."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by: int | None
    created_at: datetime


class RoomDetailResponse(RoomResponse):
    """A room plus how many members it has (see `Room.member_count`)."""

    member_count: int


class RoomMembershipResponse(BaseModel):
    """A single membership row: who is in which room, and since when."""

    model_config = ConfigDict(from_attributes=True)

    room_id: int
    user_id: int
    joined_at: datetime
