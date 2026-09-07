"""Request/response models for the room endpoints.

Same boundary as `schemas/auth.py`: these describe the wire contract, while the
SQLAlchemy models describe how rows map to tables. Route handlers stay thin and
the API surface stays explicit.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.slug import canonical_slug, validate_group_slug


class RoomCreate(BaseModel):
    """Payload for `POST /rooms`.

    `name` is canonicalized server-side into the room-slug namespace (F2-R2):
    the route stores and returns the canonical slug, never the raw input.
    There is deliberately no `kind` field — `kind` is server-set only
    (always `'group'` here; `'dm'` rows are created solely by the accept
    flow), and Pydantic's default `extra='ignore'` silently drops any
    client-supplied `kind`, so a payload cannot mint a DM (F1-R5).
    """

    name: str = Field(min_length=1, max_length=100)
    # Display-only metadata (F3-R3): accepted on group-room creation, never
    # enforced at join/WS admission. DM rooms never carry one (server keeps
    # it NULL on accept).
    capacity: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def _canonicalize_name(cls, value: str) -> str:
        slug = canonical_slug(value)
        # Raises ValueError -> FastAPI surfaces it as a 422.
        validate_group_slug(slug)
        return slug


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
