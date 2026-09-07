"""unique room name

Apply the UNIQUE constraint on `rooms.name` — the constraint the ORM model
has expressed since M1's schema change but that M2's dedup had to make safe
first. Guard: count duplicate names and refuse to add the constraint while
any exist, pointing the operator at M2 rather than failing cryptically.

After this revision, `rooms.name` is the single canonical slug namespace:
user slugs (never `dm-`-prefixed, never all-numeric, enforced at create
time by app code) and DM auto-names (`dm-{low}-{high}`, F2-R3) are disjoint
by construction, and the constraint doubles as the "exactly one DM per
unordered pair" guarantee (F1-R4).

Revision ID: b1e2c3d4a5f3
Revises: b1e2c3d4a5f2
Create Date: 2026-09-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e2c3d4a5f3"
down_revision: Union[str, Sequence[str], None] = "b1e2c3d4a5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    duplicate_count = connection.execute(
        sa.text(
            "SELECT count(*) FROM ("
            "SELECT name FROM rooms GROUP BY name HAVING count(*) > 1"
            ") d"
        )
    ).scalar()
    if duplicate_count:
        raise RuntimeError(
            f"{duplicate_count} duplicate rooms.name value(s) still exist — "
            "run migration b1e2c3d4a5f2 (dedup_room_names) first"
        )
    op.create_unique_constraint("uq_rooms_name", "rooms", ["name"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_rooms_name", "rooms", type_="unique")
