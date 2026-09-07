"""Dry-run/apply renames of existing `rooms.name` values to canonical slugs.

The migration M2 (`dedup_room_names`) and this script share one planner
(`app.core.slug.plan_room_name_dedup`), so the two can never diverge: what
you see here is exactly what the migration will do. The script talks
directly to the database from `DATABASE_URL` (the app's Settings), the same
source Alembic uses.

Run it against a COPY of the database before migrating past M2 (see the M2
revision docstring for the full operator procedure):

    uv run python scripts/dedup_room_names.py          # default: dry run
    uv run python scripts/dedup_room_names.py --apply  # execute the renames

A dry run prints the `id | old | new` report and changes nothing; `--apply`
performs the same renames inside one transaction. Back up the `rooms` table
before applying — renames are permanent.
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.slug import plan_room_name_dedup


async def _run(apply: bool) -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, created_at, name FROM rooms "
                        "ORDER BY created_at, id"
                    )
                )
            ).fetchall()
            plans = plan_room_name_dedup(list(rows))

            print(f"{'id':>4}  {'old name':<24} {'new name':<24}")
            print("-" * 56)
            for room_id, old_name, new_name in plans:
                print(f"{room_id:>4}  {old_name:<24} {new_name:<24}")

            if not plans:
                print("\nNo renames needed — every name is already canonical and unique.")
                return

            if not apply:
                print(
                    f"\n{len(plans)} rename(s) planned (dry run — pass --apply to execute)."
                )
                return

            for room_id, _old_name, new_name in plans:
                await conn.execute(
                    text("UPDATE rooms SET name = :name WHERE id = :id"),
                    {"name": new_name, "id": room_id},
                )
            await conn.commit()
            print(f"\nApplied {len(plans)} rename(s).")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan (default) or apply canonical-slug renames for rooms.name."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="execute the renames (default is a read-only dry run)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.apply))


if __name__ == "__main__":
    main()
