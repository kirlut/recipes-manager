"""Schema-shape integration tests for Phase 2.

Asserts the database state produced by the backend's `init_schema()` on
startup matches `.specs/ai_gen/db_schema.md`. All queries hit Postgres
system catalogs via psycopg; no server Python code is imported.
"""

from __future__ import annotations

import psycopg
import pytest

REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "users",
        "nutrition_fact_types",
        "products",
        "product_nutrition_facts",
        "recipes",
        "recipe_products",
        "recipe_stars",
        "product_stars",
    }
)


def _column_info(conn: psycopg.Connection, table: str) -> dict[str, dict[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return {
            row[0]: {"data_type": row[1], "udt_name": row[2], "is_nullable": row[3]}
            for row in cur.fetchall()
        }


def _pk_columns(conn: psycopg.Connection, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'p' AND c.conrelid = %s::regclass
            ORDER BY array_position(c.conkey, a.attnum)
            """,
            (f"public.{table}",),
        )
        return [row[0] for row in cur.fetchall()]


def _unique_column_sets(conn: psycopg.Connection, table: str) -> list[set[str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT array_agg(a.attname)
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'u' AND c.conrelid = %s::regclass
            GROUP BY c.conname
            """,
            (f"public.{table}",),
        )
        return [set(row[0]) for row in cur.fetchall()]


def _check_constraints(conn: psycopg.Connection, table: str) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE contype = 'c' AND conrelid = %s::regclass
            """,
            (f"public.{table}",),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def _foreign_keys(conn: psycopg.Connection, table: str) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              c.conname,
              c.confdeltype,
              (SELECT array_agg(a.attname ORDER BY array_position(c.conkey, a.attnum))
                 FROM pg_attribute a
                 WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)) AS cols,
              c.confrelid::regclass::text AS ref_table,
              (SELECT array_agg(a.attname ORDER BY array_position(c.confkey, a.attnum))
                 FROM pg_attribute a
                 WHERE a.attrelid = c.confrelid AND a.attnum = ANY(c.confkey)) AS ref_cols
            FROM pg_constraint c
            WHERE c.contype = 'f' AND c.conrelid = %s::regclass
            """,
            (f"public.{table}",),
        )
        return [
            {
                "name": r[0],
                "on_delete": r[1],
                "cols": list(r[2]),
                "ref_table": r[3].replace("public.", ""),
                "ref_cols": list(r[4]),
            }
            for r in cur.fetchall()
        ]


def _indexes(conn: psycopg.Connection, table: str) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
            """,
            (table,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Extension and enum
# ---------------------------------------------------------------------------


def test_pg_trgm_extension_present(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        row = cur.fetchone()
    assert row is not None, "pg_trgm extension is not installed"


def test_quantity_type_enum_values(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_type WHERE typname = 'quantity_type' AND typtype = 'e'"
        )
        assert cur.fetchone() is not None, "enum type 'quantity_type' does not exist"

        cur.execute("SELECT unnest(enum_range(NULL::quantity_type))::text")
        values = {row[0] for row in cur.fetchall()}

    assert values == {"weight", "volume"}, (
        f"quantity_type enum values mismatch: expected {{'weight', 'volume'}}, got {values!r}"
    )


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def test_required_tables_exist(pg_conn: psycopg.Connection) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        present = {row[0] for row in cur.fetchall()}

    missing = REQUIRED_TABLES - present
    assert not missing, f"Missing tables: {sorted(missing)}. Present: {sorted(present)}"


# ---------------------------------------------------------------------------
# Representative column shapes
# ---------------------------------------------------------------------------


def test_users_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "users")

    assert "id" in cols and cols["id"]["data_type"] == "bigint"
    assert cols["username"]["data_type"] == "text"
    assert cols["username"]["is_nullable"] == "NO"
    assert cols["pwd_hash"]["data_type"] == "text"
    assert cols["pwd_hash"]["is_nullable"] == "NO"
    assert cols["full_name"]["data_type"] == "text"
    assert cols["full_name"]["is_nullable"] == "YES"
    assert cols["created_at"]["data_type"] == "timestamp with time zone"
    assert cols["created_at"]["is_nullable"] == "NO"


def test_nutrition_fact_types_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "nutrition_fact_types")

    assert cols["id"]["data_type"] == "bigint"
    assert cols["name"]["data_type"] == "text"
    assert cols["name"]["is_nullable"] == "NO"
    assert cols["unit"]["data_type"] == "text"
    assert cols["unit"]["is_nullable"] == "NO"


def test_products_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "products")

    assert cols["id"]["data_type"] == "bigint"
    assert cols["name"]["data_type"] == "text"
    assert cols["name"]["is_nullable"] == "NO"
    assert cols["image_filename"]["data_type"] == "text"
    assert cols["image_filename"]["is_nullable"] == "YES"
    assert cols["created_by_user_id"]["data_type"] == "bigint"
    assert cols["created_by_user_id"]["is_nullable"] == "YES"
    assert cols["import_source"]["data_type"] == "text"
    assert cols["import_source"]["is_nullable"] == "YES"
    assert cols["created_at"]["data_type"] == "timestamp with time zone"


def test_recipes_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "recipes")

    assert cols["id"]["data_type"] == "bigint"
    assert cols["name"]["data_type"] == "text"
    assert cols["name"]["is_nullable"] == "NO"
    assert cols["description"]["data_type"] == "text"
    assert cols["description"]["is_nullable"] == "YES"
    assert cols["image_filename"]["data_type"] == "text"
    assert cols["image_filename"]["is_nullable"] == "YES"
    assert cols["created_by_user_id"]["data_type"] == "bigint"
    assert cols["created_by_user_id"]["is_nullable"] == "YES"
    assert cols["import_source"]["data_type"] == "text"
    assert cols["created_at"]["data_type"] == "timestamp with time zone"


def test_product_nutrition_facts_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "product_nutrition_facts")

    assert cols["product_id"]["data_type"] == "bigint"
    assert cols["product_id"]["is_nullable"] == "NO"
    assert cols["nutrition_fact_id"]["data_type"] == "bigint"
    assert cols["nutrition_fact_id"]["is_nullable"] == "NO"
    assert cols["quantity_type"]["udt_name"] == "quantity_type"
    assert cols["quantity_type"]["is_nullable"] == "NO"
    assert cols["amount"]["data_type"] == "double precision"
    assert cols["amount"]["is_nullable"] == "NO"


def test_recipe_products_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "recipe_products")

    assert cols["recipe_id"]["data_type"] == "bigint"
    assert cols["recipe_id"]["is_nullable"] == "NO"
    assert cols["product_id"]["data_type"] == "bigint"
    assert cols["product_id"]["is_nullable"] == "NO"
    assert cols["quantity_type"]["udt_name"] == "quantity_type"
    assert cols["quantity_type"]["is_nullable"] == "NO"
    assert cols["amount"]["data_type"] == "double precision"
    assert cols["amount"]["is_nullable"] == "NO"


def test_recipe_stars_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "recipe_stars")

    assert cols["user_id"]["data_type"] == "bigint"
    assert cols["recipe_id"]["data_type"] == "bigint"
    assert cols["created_at"]["data_type"] == "timestamp with time zone"


def test_product_stars_columns(pg_conn: psycopg.Connection) -> None:
    cols = _column_info(pg_conn, "product_stars")

    assert cols["user_id"]["data_type"] == "bigint"
    assert cols["product_id"]["data_type"] == "bigint"
    assert cols["created_at"]["data_type"] == "timestamp with time zone"


# ---------------------------------------------------------------------------
# Primary keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table,expected_pk",
    [
        ("users", ["id"]),
        ("nutrition_fact_types", ["id"]),
        ("products", ["id"]),
        ("recipes", ["id"]),
        ("product_nutrition_facts", ["product_id", "nutrition_fact_id", "quantity_type"]),
        ("recipe_products", ["recipe_id", "product_id"]),
        ("recipe_stars", ["user_id", "recipe_id"]),
        ("product_stars", ["user_id", "product_id"]),
    ],
)
def test_primary_keys(
    pg_conn: psycopg.Connection, table: str, expected_pk: list[str]
) -> None:
    pk = _pk_columns(pg_conn, table)
    assert set(pk) == set(expected_pk), (
        f"{table} PK columns mismatch: expected {sorted(expected_pk)}, got {sorted(pk)}"
    )
    assert len(pk) == len(expected_pk), (
        f"{table} PK has {len(pk)} columns, expected {len(expected_pk)}"
    )


# ---------------------------------------------------------------------------
# Unique constraints
# ---------------------------------------------------------------------------


def test_users_username_unique(pg_conn: psycopg.Connection) -> None:
    uniques = _unique_column_sets(pg_conn, "users")
    assert {"username"} in uniques, (
        f"users.username is not declared UNIQUE. Found uniques: {uniques}"
    )


def test_nutrition_fact_types_name_unique(pg_conn: psycopg.Connection) -> None:
    uniques = _unique_column_sets(pg_conn, "nutrition_fact_types")
    assert {"name"} in uniques, (
        f"nutrition_fact_types.name is not declared UNIQUE. Found uniques: {uniques}"
    )


# ---------------------------------------------------------------------------
# CHECK constraints
# ---------------------------------------------------------------------------


def test_products_origin_xor_check(pg_conn: psycopg.Connection) -> None:
    checks = _check_constraints(pg_conn, "products")
    assert "products_origin_xor" in checks, (
        f"products_origin_xor CHECK is missing. Found CHECKs: {list(checks)}"
    )
    definition = checks["products_origin_xor"].lower()
    assert "created_by_user_id" in definition and "import_source" in definition, (
        f"products_origin_xor does not reference both columns: {checks['products_origin_xor']!r}"
    )


def test_recipes_origin_xor_check(pg_conn: psycopg.Connection) -> None:
    checks = _check_constraints(pg_conn, "recipes")
    assert "recipes_origin_xor" in checks, (
        f"recipes_origin_xor CHECK is missing. Found CHECKs: {list(checks)}"
    )
    definition = checks["recipes_origin_xor"].lower()
    assert "created_by_user_id" in definition and "import_source" in definition, (
        f"recipes_origin_xor does not reference both columns: {checks['recipes_origin_xor']!r}"
    )


def test_product_nutrition_facts_amount_non_negative_check(
    pg_conn: psycopg.Connection,
) -> None:
    checks = _check_constraints(pg_conn, "product_nutrition_facts")
    matching = [
        defn
        for defn in checks.values()
        if "amount" in defn.lower() and ">=" in defn and "0" in defn
    ]
    assert matching, (
        "product_nutrition_facts is missing a CHECK on amount >= 0. "
        f"Found CHECKs: {checks}"
    )


def test_recipe_products_amount_positive_check(pg_conn: psycopg.Connection) -> None:
    checks = _check_constraints(pg_conn, "recipe_products")
    # amount > 0 in the spec; must be a strict "greater than", not ">="
    matching = [
        defn
        for defn in checks.values()
        if "amount" in defn.lower() and ">" in defn and ">=" not in defn and "0" in defn
    ]
    assert matching, (
        "recipe_products is missing a CHECK on amount > 0. "
        f"Found CHECKs: {checks}"
    )


# ---------------------------------------------------------------------------
# Foreign keys with ON DELETE behavior
# ---------------------------------------------------------------------------


# Expected FKs per `db_schema.md` §8.1. confdeltype: 'c'=CASCADE, 'r'=RESTRICT, 'a'=NO ACTION.
EXPECTED_FKS: list[tuple[str, list[str], str, list[str], str]] = [
    # (table, cols, ref_table, ref_cols, on_delete)
    ("products", ["created_by_user_id"], "users", ["id"], "r"),
    ("product_nutrition_facts", ["product_id"], "products", ["id"], "c"),
    ("product_nutrition_facts", ["nutrition_fact_id"], "nutrition_fact_types", ["id"], "r"),
    ("recipes", ["created_by_user_id"], "users", ["id"], "r"),
    ("recipe_products", ["recipe_id"], "recipes", ["id"], "c"),
    ("recipe_products", ["product_id"], "products", ["id"], "r"),
    ("recipe_stars", ["user_id"], "users", ["id"], "c"),
    ("recipe_stars", ["recipe_id"], "recipes", ["id"], "c"),
    ("product_stars", ["user_id"], "users", ["id"], "c"),
    ("product_stars", ["product_id"], "products", ["id"], "c"),
]


@pytest.mark.parametrize(
    "table,cols,ref_table,ref_cols,on_delete",
    EXPECTED_FKS,
    ids=lambda v: v if isinstance(v, str) else "_".join(v) if isinstance(v, list) else str(v),
)
def test_foreign_key_on_delete(
    pg_conn: psycopg.Connection,
    table: str,
    cols: list[str],
    ref_table: str,
    ref_cols: list[str],
    on_delete: str,
) -> None:
    fks = _foreign_keys(pg_conn, table)

    matching = [
        fk
        for fk in fks
        if fk["cols"] == cols and fk["ref_table"] == ref_table and fk["ref_cols"] == ref_cols
    ]
    assert matching, (
        f"FK {table}.{cols} -> {ref_table}.{ref_cols} not found. "
        f"Existing FKs on {table}: {fks}"
    )

    fk = matching[0]
    assert fk["on_delete"] == on_delete, (
        f"FK {table}.{cols} -> {ref_table}.{ref_cols} has ON DELETE "
        f"confdeltype={fk['on_delete']!r}, expected {on_delete!r}"
    )


# ---------------------------------------------------------------------------
# Indexes (db_schema.md §5)
# ---------------------------------------------------------------------------


def test_recipes_name_trgm_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "recipes")
    assert "recipes_name_trgm_idx" in idx, (
        f"recipes_name_trgm_idx missing. Indexes on recipes: {list(idx)}"
    )
    definition = idx["recipes_name_trgm_idx"].lower()
    assert "using gist" in definition, f"recipes_name_trgm_idx is not GIST: {definition!r}"
    assert "gist_trgm_ops" in definition, (
        f"recipes_name_trgm_idx does not use gist_trgm_ops: {definition!r}"
    )


def test_products_name_trgm_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "products")
    assert "products_name_trgm_idx" in idx, (
        f"products_name_trgm_idx missing. Indexes on products: {list(idx)}"
    )
    definition = idx["products_name_trgm_idx"].lower()
    assert "using gist" in definition, f"products_name_trgm_idx is not GIST: {definition!r}"
    assert "gist_trgm_ops" in definition, (
        f"products_name_trgm_idx does not use gist_trgm_ops: {definition!r}"
    )


def test_recipes_created_by_user_id_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "recipes")
    assert "recipes_created_by_user_id_idx" in idx, (
        f"recipes_created_by_user_id_idx missing. Indexes: {list(idx)}"
    )


def test_products_created_by_user_id_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "products")
    assert "products_created_by_user_id_idx" in idx, (
        f"products_created_by_user_id_idx missing. Indexes: {list(idx)}"
    )


def test_recipe_products_product_id_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "recipe_products")
    assert "recipe_products_product_id_idx" in idx, (
        f"recipe_products_product_id_idx missing. Indexes: {list(idx)}"
    )


def test_recipes_created_at_id_desc_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "recipes")
    assert "recipes_created_at_id_desc_idx" in idx, (
        f"recipes_created_at_id_desc_idx missing. Indexes: {list(idx)}"
    )
    definition = idx["recipes_created_at_id_desc_idx"].lower()
    assert "created_at desc" in definition, (
        f"recipes_created_at_id_desc_idx missing 'created_at DESC': {definition!r}"
    )
    assert "id desc" in definition, (
        f"recipes_created_at_id_desc_idx missing 'id DESC': {definition!r}"
    )


def test_products_created_at_id_desc_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "products")
    assert "products_created_at_id_desc_idx" in idx, (
        f"products_created_at_id_desc_idx missing. Indexes: {list(idx)}"
    )
    definition = idx["products_created_at_id_desc_idx"].lower()
    assert "created_at desc" in definition, (
        f"products_created_at_id_desc_idx missing 'created_at DESC': {definition!r}"
    )
    assert "id desc" in definition, (
        f"products_created_at_id_desc_idx missing 'id DESC': {definition!r}"
    )


def test_recipe_stars_user_created_at_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "recipe_stars")
    assert "recipe_stars_user_created_at_idx" in idx, (
        f"recipe_stars_user_created_at_idx missing. Indexes: {list(idx)}"
    )
    definition = idx["recipe_stars_user_created_at_idx"].lower()
    assert "user_id" in definition, definition
    assert "created_at desc" in definition, definition
    assert "recipe_id desc" in definition, definition


def test_product_stars_user_created_at_index(pg_conn: psycopg.Connection) -> None:
    idx = _indexes(pg_conn, "product_stars")
    assert "product_stars_user_created_at_idx" in idx, (
        f"product_stars_user_created_at_idx missing. Indexes: {list(idx)}"
    )
    definition = idx["product_stars_user_created_at_idx"].lower()
    assert "user_id" in definition, definition
    assert "created_at desc" in definition, definition
    assert "product_id desc" in definition, definition
