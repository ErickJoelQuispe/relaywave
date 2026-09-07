"""dedup room names

Data-only migration making every `rooms.name` a canonical, unique slug so M3
can apply the UNIQUE constraint. Rules live in `app.core.slug`:
`canonical_slug` + `plan_room_name_dedup` (F2-R4). This revision does not
touch any constraint — it only renames rows.

## Operator procedure (read before upgrading past this revision)

1. **Back up `rooms`** — this migration is IRREVERSIBLE. The downgrade is a
   deliberate no-op: it cannot restore the original free-text names (F2-R4:
   renames are permanent). A backup is the only way back.

       pg_dump --table=rooms relaywave > rooms_backup_$(date +%F).sql

2. **Dry-run on a copy** first. The planner is unit-tested (tests/test_slug.py
   — pytest never runs Alembic; the test suite builds its schema from
   `Base.metadata`, so M2's semantics rest on those pure tests plus this
   manual review), and the script shares the planner with this migration, so
   the two cannot diverge:

       uv run python scripts/dedup_room_names.py          # prints id | old | new

3. Upgrade to this revision, inspect the renames applied, then upgrade to M3
   (`unique_room_name`), whose guard re-checks the duplicate count is zero
   before adding the constraint:

       uv run alembic upgrade b1e2c3d4a5f2
       uv run alembic upgrade head

Revision ID: b1e2c3d4a5f2
Revises: b1e2c3d4a5f1
Create Date: 2026-09-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.slug import plan_room_name_dedup

# revision identifiers, used by Alembic.
revision: str = "b1e2c3d4a5f2"
down_revision: Union[str, Sequence[str], None] = "b1e2c3d4a5f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, created_at, name FROM rooms ORDER BY created_at, id"
        )
    ).fetchall()
    plans = plan_room_name_dedup(list(rows))
    for room_id, _old_name, new_name in plans:
        connection.execute(
            sa.text("UPDATE rooms SET name = :name WHERE id = :id"),
            {"name": new_name, "id": room_id},
        )


def downgrade() -> None:
    """Downgrade schema (no-op, by design).

    Renames are permanent (F2-R4): original free-text names cannot be
    reconstructed from the canonical slugs. The only rollback is the `rooms`
    backup taken before upgrading to this revision.
    """
