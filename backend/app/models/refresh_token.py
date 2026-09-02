from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """A server-side record of an issued refresh token.

    The raw JWT is never stored — only its SHA-256 hash — so a database leak
    does not expose reusable tokens. `jti` (the JWT ID embedded in the token)
    is the lookup key used to find this row during rotation; `revoked_at` is
    `None` while the token is valid and set to a timestamp once it is revoked.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    # `index=True` speeds up "list all of a user's sessions" and lets cascade
    # deletes locate the rows efficiently.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The JWT ID, embedded in the token as the `jti` claim and used to locate
    # this row on refresh/logout. UUID4 (36 chars) is globally unique.
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    # SHA-256 hex digest of the raw token is always exactly 64 chars.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # None == still valid; a timestamp == revoked. We keep the row (rather than
    # deleting it) so a reused/revoked token can still be detected in the future.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
