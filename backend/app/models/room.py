from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.room_membership import RoomMembership


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list[RoomMembership]] = relationship(back_populates="room")
    messages: Mapped[list[Message]] = relationship(back_populates="room")

    @property
    def member_count(self) -> int:
        """Number of members, as `len(self.memberships)`.

        Only safe when `memberships` has been eagerly loaded (via
        `selectinload`), because lazy loading is impossible in async and would
        raise `MissingGreenlet`. The `GET /rooms/{id}` endpoint is its only
        consumer and loads the relationship explicitly.
        """
        return len(self.memberships)
