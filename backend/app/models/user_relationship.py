from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RelationshipStatus(StrEnum):
    """The single per-pair relationship row's state machine (D1).

    One row per unordered pair, `pending | accepted | blocked`, so every
    transition is one locked UPDATE and pair uniqueness is one constraint:
    - `pending`  — a friend request; `actor_id` is the requester;
    - `accepted` — a friendship (a DM room exists for the pair);
    - `blocked`  — `actor_id` is the blocker.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class UserRelationship(Base):
    """One row per unordered pair of users (F1).

    Column order is normalized (`user_low_id < user_high_id`, enforced by a
    CHECK), so the UNIQUE pair constraint is a plain btree index usable for
    lookups in either direction — the app sorts ids with `sorted()` before
    ever touching this table.

    FKs are CASCADE (not the `rooms.created_by` SET NULL pattern): a
    relationship missing a participant is meaningless, matching the
    `messages`/`refresh_tokens` precedent.
    """

    __tablename__ = "user_relationships"
    __table_args__ = (
        CheckConstraint(
            "user_low_id < user_high_id", name="ck_user_relationships_ordered"
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'blocked')",
            name="ck_user_relationships_status",
        ),
        CheckConstraint(
            "actor_id IN (user_low_id, user_high_id)",
            name="ck_user_relationships_actor",
        ),
        # The unordered-pair uniqueness guarantee: at most one pending
        # request and at most one friendship per pair, ever.
        UniqueConstraint(
            "user_low_id", "user_high_id", name="uq_user_relationships_pair"
        ),
        # `uq_..._pair` already covers the `user_low_id` prefix; this index
        # serves lookups by the high column (e.g. "my incoming requests").
        Index("ix_user_relationships_user_high_id", "user_high_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_low_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    user_high_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(
        String(8),
        default=RelationshipStatus.PENDING,
        server_default=text("'pending'"),
    )
    # Requester while `pending`, blocker while `blocked` — drives the
    # incoming/outgoing request split and the blocked list (F1-R3/R6).
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
