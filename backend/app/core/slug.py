"""Canonical room-name slug helpers (pure: no DB, no I/O).

One shared implementation of the F2 naming rules, imported by three very
different callers — create-time validation, alias lookup / DM auto-naming,
and the dedup migration M2 (plus its dry-run script). Keeping the rules in
one pure module is what lets the test suite exercise migration semantics
without a database: `tests/test_slug.py` pins the planner's output over
synthetic rows, and pytest never runs Alembic (conftest builds the schema
from `Base.metadata` instead).

IMMUTABILITY CONTRACT: the output of every function here must never change
once a migration importing it has been released. The migration file
snapshots the *call*, not the *implementation*, so editing a function below
after `dedup_room_names` shipped would silently change what a deployed M2
does. If the naming rules ever need to change, ADD a new function and leave
the existing ones untouched — the golden tests in tests/test_slug.py are the
guard that makes a contract breach visible.
"""

import re

#: Reserved prefix for auto-generated DM room names (F2-R3). User-chosen
#: group-room slugs are rejected when they start with this prefix, so the
#: user-slug set and the DM-name set stay disjoint inside the single UNIQUE
#: constraint on `rooms.name`.
RESERVED_DM_PREFIX = "dm-"

# Lowercase ASCII letters/digits are the only characters a slug may contain;
# every maximal run of anything else collapses into a single dash.
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")

# A room row as consumed by `plan_room_name_dedup`: `(id, created_at, name)`.
# `created_at` is never inspected (ordering is the caller's job) but is part
# of the row shape so the signature mirrors the migration's SELECT.
type RoomRow = tuple[int, object, str]


def canonical_slug(text: str) -> str:
    """Canonicalize arbitrary text into the room-slug namespace (F2-R1).

    Lowercases the input, collapses every maximal run of characters outside
    ``[a-z0-9]`` into a single ``-``, and trims leading/trailing ``-``. Every
    stored `rooms.name` is the canonical form of what the user typed, so
    equality lookup is case-insensitive by construction.
    """
    return _NON_SLUG_CHARS.sub("-", text.lower()).strip("-")


def dm_room_name(user_a: int, user_b: int) -> str:
    """The deterministic auto-name for the pair's DM room (F2-R3).

    ``dm-{lower_user_id}-{upper_user_id}`` with ascending numeric ids. Because
    group slugs can never start with ``dm-``, the UNIQUE constraint on
    `rooms.name` doubles as the "exactly one DM per unordered pair"
    guarantee.
    """
    low, high = sorted((user_a, user_b))
    return f"{RESERVED_DM_PREFIX}{low}-{high}"


def validate_group_slug(slug: str) -> None:
    """Reject canonical slugs that must never become a group room's name.

    `slug` must already be canonical (`canonical_slug` output). Raises
    `ValueError` when the canonical form is empty (no ASCII alphanumeric),
    longer than 100, all-numeric (that space belongs to the numeric-id
    namespace), or starts with the reserved ``dm-`` prefix. The create route's
    Pydantic validator surfaces the message as a 422; the by-name lookup does
    not call this — there, any invalid input is just a uniform 404 miss.
    """
    if not slug:
        raise ValueError("Room name must contain at least one letter or number")
    if len(slug) > 100:
        raise ValueError("Room name is too long (max 100 characters)")
    if slug.isdigit():
        raise ValueError("Room names cannot be only numbers")
    if slug.startswith(RESERVED_DM_PREFIX):
        raise ValueError("Room names cannot start with 'dm-' — that prefix is reserved")


def plan_room_name_dedup(
    rows: list[RoomRow] | tuple[RoomRow, ...],
) -> list[tuple[int, str, str]]:
    """Plan renames making every `rooms.name` canonical and unique (F2-R4).

    `rows` are ``(id, created_at, name)`` tuples ordered by
    ``created_at, id`` ascending — first wins. For each row in that order:
    canonicalize the stored name; when the canonical form is empty use base
    ``room``; when it is all-numeric or starts with the reserved ``dm-``
    prefix, prefix it with ``room-``; then resolve collisions by appending
    ``-2``, ``-3``, ... until the slug is unique among already-assigned ones.

    Returns ``(id, old_name, new_name)`` for every row whose stored name
    changes. A row already at its planned name is not returned — no UPDATE is
    needed for it.
    """
    assigned: set[str] = set()
    plans: list[tuple[int, str, str]] = []

    for room_id, _created_at, name in rows:
        slug = canonical_slug(name)
        if not slug:
            slug = "room"
        elif slug.isdigit() or slug.startswith(RESERVED_DM_PREFIX):
            slug = f"room-{slug}"

        base = slug
        counter = 1
        while slug in assigned:
            counter += 1
            slug = f"{base}-{counter}"
        assigned.add(slug)

        if slug != name:
            plans.append((room_id, name, slug))

    return plans
