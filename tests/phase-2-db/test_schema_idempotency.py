"""Schema-init idempotency test for Phase 2.

Re-executes `src/server/dal/schema.sql` against the already-initialized
test database via psycopg and verifies that:

  1. Re-running the DDL raises no exception (so every statement is guarded
     by `IF NOT EXISTS` or an equivalent guard like the `DO` block around
     `CREATE TYPE`).
  2. The seed insert is idempotent under `ON CONFLICT (name) DO NOTHING`,
     so `nutrition_fact_types` still has exactly five rows with the
     canonical names.

This covers the implementation-plan DoD line: "Restarting the backend
twice is idempotent (no errors, no duplicate seed rows)."
"""

from __future__ import annotations

import pathlib

import psycopg
import pytest


def test_schema_sql_can_be_reapplied(
    pg_conn: psycopg.Connection, schema_sql_path: pathlib.Path
) -> None:
    if not schema_sql_path.exists():
        pytest.skip(
            f"{schema_sql_path} does not exist yet; "
            "Phase 2 implementation has not landed."
        )

    sql = schema_sql_path.read_text()

    with pg_conn.cursor() as cur:
        cur.execute(sql)
    pg_conn.commit()

    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM nutrition_fact_types")
        (count,) = cur.fetchone()
    assert count == 5, (
        f"Re-running schema.sql changed nutrition_fact_types row count: "
        f"expected 5, got {count}. Seed insert is not idempotent."
    )

    with pg_conn.cursor() as cur:
        cur.execute("SELECT name FROM nutrition_fact_types ORDER BY name")
        names = [row[0] for row in cur.fetchall()]
    assert names == ["Energy", "Fat", "Fibers", "Net Carbs", "Protein"], (
        f"Seed names diverged after re-run: {names}"
    )
