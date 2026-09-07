"""Golden tests for the pure room-name slug helpers in `app/core/slug.py`.

The naming rules are shared by create-time validation, DM auto-naming, and
the dedup migration M2. pytest never runs Alembic (conftest builds the test
schema from `Base.metadata`), so these unit tests — plus the documented
manual dry-run stop point in the M2 revision docstring — are the only
automated coverage the dedup migration has. Any change to a function below
that breaks a golden here is a migration-semantics regression by definition.
"""

import pytest

from app.core.slug import (
    RESERVED_DM_PREFIX,
    canonical_slug,
    dm_room_name,
    plan_room_name_dedup,
    validate_group_slug,
)


class TestCanonicalSlug:
    def test_lowercases_and_collapses_runs_of_non_slug_chars(self):
        assert canonical_slug("Project Alpha!") == "project-alpha"
        assert canonical_slug("  My   Room  ") == "my-room"
        assert canonical_slug("a--b  c") == "a-b-c"

    def test_trims_leading_and_trailing_dashes(self):
        assert canonical_slug("--trim--") == "trim"
        assert canonical_slug("---") == ""

    def test_non_ascii_characters_collapse(self):
        # 'é' is outside [a-z0-9], so it collapses like any other character.
        assert canonical_slug("Café Latte") == "caf-latte"

    def test_pure_numeric_input_survives_canonicalization(self):
        # All-numeric canonical forms are REJECTED at create time by
        # `validate_group_slug`, but `canonical_slug` itself must not mangle
        # them — the reserved numeric space is the id namespace.
        assert canonical_slug("123") == "123"

    def test_reserved_prefix_is_not_escaped_by_canonicalization(self):
        # Escaping `dm-` is the planner's / validator's job, not the
        # canonicalizer's: the slug is the pure normalization step.
        assert canonical_slug("dm-buddy") == "dm-buddy"

    def test_case_insensitivity_is_by_construction(self):
        assert canonical_slug("MY-ROOM") == "my-room"
        assert canonical_slug("my room") == "my-room"
        assert canonical_slug("MyRoom") == "myroom"


class TestDmRoomName:
    def test_uses_ascending_numeric_ids(self):
        assert dm_room_name(5, 12) == "dm-5-12"
        assert dm_room_name(12, 5) == "dm-5-12"

    def test_prefix_is_the_reserved_constant(self):
        assert dm_room_name(1, 2).startswith(RESERVED_DM_PREFIX)


class TestValidateGroupSlug:
    def test_accepts_a_valid_canonical_slug(self):
        # A valid slug must not raise.
        validate_group_slug("my-room")

    def test_rejects_empty_slug(self):
        with pytest.raises(ValueError, match="at least one letter or number"):
            validate_group_slug("")

    def test_rejects_all_numeric_slug(self):
        with pytest.raises(ValueError, match="only numbers"):
            validate_group_slug("123")

    def test_rejects_reserved_prefix(self):
        with pytest.raises(ValueError, match="reserved"):
            validate_group_slug("dm-buddy")

    def test_rejects_too_long_slug(self):
        with pytest.raises(ValueError, match="too long"):
            validate_group_slug("a" * 101)


class TestPlanRoomNameDedup:
    """F2-R4 scenarios over synthetic rows.

    Rows are `(id, created_at, name)` tuples ordered by `created_at, id`
    ascending — the migration SELECT's order. `created_at` is opaque here
    (`None`), since ordering is the caller's contract.
    """

    def test_duplicate_names_deduplicate_with_suffixes(self):
        rows = [(1, None, "Work"), (2, None, "work"), (3, None, "Work!")]
        assert plan_room_name_dedup(rows) == [
            (1, "Work", "work"),
            (2, "work", "work-2"),
            (3, "Work!", "work-3"),
        ]

    def test_first_row_in_order_wins_the_plain_slug(self):
        # "first wins" is defined by the row ORDER (created_at, id), which
        # the planner receives pre-sorted — it must never re-sort. The first
        # row keeps 'work' (no rename needed), the second is suffixed.
        rows = [(10, None, "work"), (1, None, "Work")]
        assert plan_room_name_dedup(rows) == [(1, "Work", "work-2")]

    def test_reserved_and_numeric_only_names_are_escaped(self):
        rows = [(1, None, "DM-5-12"), (2, None, "123"), (3, None, "!!!")]
        assert plan_room_name_dedup(rows) == [
            (1, "DM-5-12", "room-dm-5-12"),
            (2, "123", "room-123"),
            (3, "!!!", "room"),
        ]

    def test_escape_colliding_with_existing_room_slug(self):
        rows = [(1, None, "Room"), (2, None, "room"), (3, None, "!!!")]
        assert plan_room_name_dedup(rows) == [
            (1, "Room", "room"),
            (2, "room", "room-2"),
            (3, "!!!", "room-3"),
        ]

    def test_suffixes_skip_until_unique(self):
        rows = [
            (1, None, "Work"),
            (2, None, "work"),
            (3, None, "work-2"),  # literal name collides with the 2nd suffix
        ]
        assert plan_room_name_dedup(rows) == [
            (1, "Work", "work"),
            (2, "work", "work-2"),
            (3, "work-2", "work-2-2"),
        ]

    def test_unchanged_rows_are_not_reported(self):
        # A row whose stored name is already its planned unique slug needs no
        # UPDATE, so it must not appear in the dry-run report.
        rows = [(1, None, "my-room"), (2, None, "other-room")]
        assert plan_room_name_dedup(rows) == []

    def test_all_rows_canonical_but_unique_only_suffix_duplicates(self):
        # The first 'room' keeps its name (unchanged, not reported); only the
        # duplicate is suffixed.
        rows = [(1, None, "room"), (2, None, "room"), (3, None, "chat")]
        assert plan_room_name_dedup(rows) == [(2, "room", "room-2")]

    def test_dry_run_plan_is_applyable_without_mutation(self):
        # The script's --dry-run default just prints this list; applying the
        # same list must yield a unique-constraint-safe dataset. Simulate:
        # the planned names are all unique and canonical.
        rows = [(1, None, "Work"), (2, None, "work"), (3, None, "Work!")]
        planned = plan_room_name_dedup(rows)
        new_names = [new for _, _, new in planned]
        assert len(new_names) == len(set(new_names))
        assert all(not name.isdigit() for name in new_names)
        assert all(not name.startswith(RESERVED_DM_PREFIX) for name in new_names)
        # Every row is covered exactly once.
        assert {room_id for room_id, _, _ in planned} == {1, 2, 3}
