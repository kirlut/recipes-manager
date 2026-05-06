import os
import pathlib
import sys
from collections.abc import Iterator

import psycopg
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
os.environ.setdefault("POSTGRES_PORT", os.environ.get("POSTGRES_HOST_PORT", "15432"))
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "recipes_test")

from tests.helpers.db import db_url  # noqa: E402


@pytest.fixture
def pg_conn() -> Iterator[psycopg.Connection]:
    """A fresh psycopg connection per test, closed on teardown.

    Per `.specs/ai_gen/testing_strategy.md` §6: DB-direct tests open one
    connection per test via the host-bound Postgres port.
    """
    with psycopg.connect(db_url(), connect_timeout=10) as conn:
        yield conn


@pytest.fixture
def schema_sql_path() -> pathlib.Path:
    """Path to `src/server/dal/schema.sql` on the host filesystem."""
    return _REPO_ROOT / "src" / "server" / "dal" / "schema.sql"
