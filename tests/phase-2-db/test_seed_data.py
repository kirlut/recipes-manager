"""Seed-data integration tests for Phase 2.

Verifies that `init_schema()` seeded `nutrition_fact_types` with exactly
the five rows described in `.specs/ai_gen/db_schema.md` §6.
"""

from __future__ import annotations

import psycopg

EXPECTED_ROWS: list[tuple[str, str]] = [
    ("Energy", "kcal"),
    ("Fat", "g"),
    ("Fibers", "g"),
    ("Net Carbs", "g"),
    ("Protein", "g"),
]


def test_nutrition_fact_types_row_count(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM nutrition_fact_types")
        (count,) = cur.fetchone()
    assert count == 5, f"Expected 5 nutrition_fact_types rows, got {count}"


def test_nutrition_fact_types_rows_match_spec(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT name, unit FROM nutrition_fact_types ORDER BY name")
        rows = cur.fetchall()

    assert rows == EXPECTED_ROWS, (
        f"nutrition_fact_types rows mismatch:\n"
        f"  expected: {EXPECTED_ROWS}\n"
        f"  got:      {rows}"
    )


def test_nutrition_fact_types_have_ids(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name FROM nutrition_fact_types")
        rows = cur.fetchall()

    assert len(rows) == 5
    for row_id, name in rows:
        assert isinstance(row_id, int) and row_id > 0, (
            f"nutrition_fact_types row {name!r} has invalid id={row_id!r}"
        )
