import psycopg

from tests.helpers.db import db_url


def test_postgres_select_one() -> None:
    """Connect to the test compose's host-bound Postgres and run SELECT 1.

    Confirms that the postgres image, env vars, and host port-binding
    are all wired correctly — independently of the backend.
    """
    with psycopg.connect(db_url(), connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()

    assert row == (1,), f"Expected (1,) from SELECT 1, got {row!r}"
