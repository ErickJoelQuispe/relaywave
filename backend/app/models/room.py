from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.room_membership import RoomMembership


class RoomKind(StrEnum):
    """Server-set discriminator for what a room is (D1/D4).

    `group` is the default for every room created through `POST /rooms`;
    `dm` rows are produced only inside the friend-accept transaction (F1-R4)
    and carry the reserved auto-generated `dm-{low}-{high}` name (F2-R3).
    """

    GROUP = "group"
    DM = "dm"


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        # The UNIQUE name is the whole F2 namespace AND the per-pair DM
        # guarantee (D3): user slugs can never start with `dm-`, so a second
        # row with the same `dm-{low}-{high}` name is impossible. Added by
        # migration M3 after M2's dedup.
        UniqueConstraint("name", name="uq_rooms_name"),
        CheckConstraint("kind IN ('group', 'dm')", name="ck_rooms_kind"),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="ck_rooms_capacity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # `kind` is never client-settable: the create route always produces
    # `group`, and only the accept flow (F1-R4) writes `dm`.
    kind: Mapped[str] = mapped_column(
        String(8),
        default=RoomKind.GROUP,
        server_default=text("'group'"),
    )
    # Display-only metadata (F3-R3): never enforced at join/WS admission.
    capacity: Mapped[int | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Transient response-only field — deliberately NOT a column (no Mapped
    # annotation, so SQLAlchemy leaves it as a plain class attribute). Route
    # handlers resolve and set it for `kind='dm'` rows so the wire payload
    # (RoomResponse.peer_username, F1-R7) carries the peer's username while
    # the client never sees or displays the internal `dm-*` auto-name.
    peer_username = None

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
