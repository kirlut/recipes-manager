import os

import psycopg

# Order matters only for readability; CASCADE handles dependents anyway.
# `nutrition_fact_types` is intentionally absent — the five seed rows
# (Energy, Protein, Net Carbs, Fat, Fibers) must survive between tests.
TABLES_TO_TRUNCATE: tuple[str, ...] = (
    "recipe_stars",
    "product_stars",
    "recipe_products",
    "product_nutrition_facts",
    "recipes",
    "products",
    "users",
)


def db_url() -> str:
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    user = os.environ["POSTGRES_USER"]
    pwd = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def truncate_all() -> None:
    """Wipe every user-data table; restart identity sequences.

    Used by the autouse `_clean_db` fixture in each phase's conftest so
    tests stay independent. `nutrition_fact_types` is preserved.
    """
    with psycopg.connect(db_url(), connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute(
            f"TRUNCATE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE;"
        )
        conn.commit()
