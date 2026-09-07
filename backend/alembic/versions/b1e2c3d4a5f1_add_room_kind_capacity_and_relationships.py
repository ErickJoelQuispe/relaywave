"""add room kind/capacity and user relationships

Purely additive schema step for friends-room-discovery:

- `rooms.kind`      VARCHAR(8) NOT NULL DEFAULT 'group' (F1/F3 discriminator)
- `rooms.capacity`  INTEGER NULL (display-only metadata, F3-R3)
- `user_relationships` table (the whole F1 state machine, D1/D2)

Safe to deploy alone: existing rows get `kind='group'`, capacity stays NULL,
and nothing reads the new table yet. The UNIQUE constraint on `rooms.name`
is deliberately NOT added here — M2 (`dedup_room_names`) must deduplicate
existing free-text names first, and M3 (`unique_room_name`) applies the
constraint once the duplicate count is zero.

Revision ID: b1e2c3d4a5f1
Revises: 3b05922772d1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e2c3d4a5f1"
down_revision: Union[str, Sequence[str], None] = "3b05922772d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "rooms",
        sa.Column(
            "kind",
            sa.String(length=8),
            server_default=sa.text("'group'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_rooms_kind", "rooms", "kind IN ('group', 'dm')"
    )
    op.add_column("rooms", sa.Column("capacity", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_rooms_capacity", "rooms", "capacity IS NULL OR capacity > 0"
    )

    op.create_table(
        "user_relationships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_low_id", sa.Integer(), nullable=False),
        sa.Column("user_high_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_id IN (user_low_id, user_high_id)",
            name="ck_user_relationships_actor",
        ),
        sa.CheckConstraint(
            "user_low_id < user_high_id", name="ck_user_relationships_ordered"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'blocked')",
            name="ck_user_relationships_status",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_high_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_low_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_low_id", "user_high_id", name="uq_user_relationships_pair"
        ),
    )
    op.create_index(
        "ix_user_relationships_user_high_id",
        "user_relationships",
        ["user_high_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_user_relationships_user_high_id", table_name="user_relationships"
    )
    op.drop_table("user_relationships")
    op.drop_constraint("ck_rooms_capacity", "rooms", type_="check")
    op.drop_column("rooms", "capacity")
    op.drop_constraint("ck_rooms_kind", "rooms", type_="check")
    op.drop_column("rooms", "kind")
