"""Phase-6 (listing + search + pagination + starring) test fixtures.

Stack: postgres (host port 15432) + backend (host port 18000). Backend
is hit directly without nginx, so route paths are unprefixed
(`/products`, `/recipes`, `/products/{id}/star`, ...) per
`api_spec.md §1.1` and `testing_strategy.md §4.7`.

Mirrors `tests/phase-5-recipes/conftest.py`; adds a `make_recipe`
factory alongside the `make_product` factory inherited from phase-5.
Each phase folder is required to be self-contained
(`testing_strategy.md` §3), hence the duplication rather than an
import from another phase folder.
"""

from __future__ import annotations

import os
import pathlib
import sys
from collections.abc import Iterator
from typing import Any

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
os.environ.setdefault("BACKEND_HOST_PORT", "18000")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

from tests.helpers import api as api_helpers  # noqa: E402
from tests.helpers.db import db_url, truncate_all  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    truncate_all()
    yield


@pytest.fixture
def api_base_url() -> str:
    port = os.environ["BACKEND_HOST_PORT"]
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


@pytest.fixture
def pg_conn() -> Iterator[psycopg.Connection]:
    """Fresh psycopg connection per test, closed on teardown."""
    with psycopg.connect(db_url(), connect_timeout=10) as conn:
        yield conn


@pytest.fixture
def make_user(api_base_url: str):
    """Factory: register + log in a user, return `(user_dict, token)`."""

    def _make(
        username: str = "alice",
        password: str = "hunter2pwd",
        full_name: str | None = "Alice Smith",
    ) -> tuple[dict, str]:
        reg = api_helpers.auth_register(
            api_base_url,
            username=username,
            password=password,
            full_name=full_name,
        )
        assert reg.status_code == 201, (
            f"make_user: register failed: {reg.status_code} {reg.text!r}"
        )
        login = api_helpers.auth_login(
            api_base_url, username=username, password=password
        )
        assert login.status_code == 200, (
            f"make_user: login failed: {login.status_code} {login.text!r}"
        )
        body = login.json()
        return body["user"], body["token"]

    return _make


@pytest.fixture
def nutrition_fact_ids(api_base_url: str, make_user) -> dict[str, int]:
    """Map of seeded nutrition-fact-type name -> id.

    Per `db_schema.md` §6 ids are not part of the contract, so tests must
    look them up via `GET /nutrition-fact-types` rather than hardcoding.
    """
    _user, token = make_user(username="nft_lookup", password="hunter2pwd")
    resp = api_helpers.nutrition_fact_types_list(api_base_url, token=token)
    assert resp.status_code == 200, (
        f"nutrition_fact_ids: GET /nutrition-fact-types failed: "
        f"{resp.status_code} {resp.text!r}"
    )
    body = resp.json()
    items = body.get("items")
    assert isinstance(items, list) and len(items) >= 5, (
        f"Expected >=5 seeded nutrition fact types, got body={body!r}"
    )
    return {item["name"]: item["id"] for item in items}


@pytest.fixture
def make_product(api_base_url: str):
    """Factory: POST a product owned by `token`'s user, return the product dict.

    Phase-6 tests need products both as recipe ingredients and as
    starring/listing fixtures. Per api_spec §6.1, a product needs at
    least one nutrition fact; the factory accepts an explicit
    `nutrition_facts` list so callers shape the product as needed.
    """

    def _make(
        *,
        token: str,
        name: str,
        nutrition_facts: list[dict[str, Any]],
        image_filename: str | None = None,
    ) -> dict:
        body = {
            "name": name,
            "image_filename": image_filename,
            "nutrition_facts": nutrition_facts,
        }
        response = api_helpers.products_create(
            api_base_url, token=token, body=body
        )
        assert response.status_code == 201, (
            f"make_product: POST /products failed: "
            f"{response.status_code} {response.text!r}"
        )
        return response.json()

    return _make


@pytest.fixture
def make_recipe(api_base_url: str):
    """Factory: POST a recipe owned by `token`'s user, return the recipe dict.

    Phase-6 pagination tests seed 25 recipes for one user; the factory
    keeps each test compact. Per api_spec §7.1 the `products` array may
    be empty (a recipe with no products has zero nutrition totals),
    which keeps the seeding step independent of phase-4 product
    creation when the test is only exercising listing semantics.
    """

    def _make(
        *,
        token: str,
        name: str,
        products: list[dict[str, Any]] | None = None,
        description: str | None = None,
        image_filename: str | None = None,
    ) -> dict:
        body = {
            "name": name,
            "description": description,
            "image_filename": image_filename,
            "products": list(products) if products is not None else [],
        }
        response = api_helpers.recipes_create(
            api_base_url, token=token, body=body
        )
        assert response.status_code == 201, (
            f"make_recipe: POST /recipes failed: "
            f"{response.status_code} {response.text!r}"
        )
        return response.json()

    return _make
