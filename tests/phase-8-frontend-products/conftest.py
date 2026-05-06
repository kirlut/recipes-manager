"""Phase-8 (frontend foundations + auth + products UI) test fixtures.

Stack: postgres (host port 15432) + backend (in-network only) + nginx
(host port 8080) — production-shaped per `testing_strategy.md` §4 §6.
Tests drive Chromium via `pytest-playwright` against
`http://127.0.0.1:8080`; backend seeding goes through the same nginx
hop (`http://127.0.0.1:8080/api/...`) so we exercise the real proxy
configuration on every test.

Each phase folder is required to be self-contained
(`testing_strategy.md` §3), so the user-/product-/nutrition-fact
factories are duplicated here rather than imported from another phase
folder.
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
os.environ.setdefault("HOST_PORT", "8080")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

from tests.helpers import api as api_helpers  # noqa: E402
from tests.helpers.db import db_url, truncate_all  # noqa: E402
from tests.helpers.images import JPEG_BYTES, PNG_BYTES  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    """Honour the `HEADLESS=0` env-var convention from
    `testing_strategy.md` §9 by translating it to pytest-playwright's
    `--headed` option. Standard pytest-playwright also accepts the
    `HEADFUL` env var, but the strategy doc names `HEADLESS=0`, so we
    bridge here without the user needing to know either.
    """
    if os.environ.get("HEADLESS") == "0":
        config.option.headed = True


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    """Wipe user-generated rows between tests; preserve nutrition_fact_types."""
    truncate_all()
    yield


@pytest.fixture
def host_port() -> str:
    return os.environ["HOST_PORT"]


@pytest.fixture
def app_base_url(host_port: str) -> str:
    """Public-facing nginx URL — used by Playwright `page.goto(...)`."""
    return f"http://127.0.0.1:{host_port}"


@pytest.fixture
def api_base_url(app_base_url: str) -> str:
    """Backend URL via nginx, with the `/api` prefix included.

    Pass this directly into `tests.helpers.api.*`: those helpers build
    e.g. `f"{base_url}/auth/register"`, which yields
    `http://127.0.0.1:8080/api/auth/register` — the correct
    nginx-fronted URL (`api_spec.md` §1.1).
    """
    return f"{app_base_url}/api"


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
    """Factory: register + log in a user, return `(user_dict, token)`.

    Each call creates a fresh user via the public API (through nginx).
    Pass a unique username per call within a single test to avoid 409s.
    """

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

    Per `db_schema.md` §6 the assigned ids are not part of the
    contract; tests look them up via `GET /nutrition-fact-types`
    rather than hardcoding.
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

    Per `api_spec.md` §6.1 every product must carry ≥1 nutrition fact;
    callers pass the `nutrition_facts` list explicitly so each test
    shapes the product as needed.
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
def make_image_filename(api_base_url: str):
    """Factory: upload a tiny in-memory image, return the assigned filename.

    Used to seed products with `image_filename` set without going
    through the UI form. The bytes come from
    `tests/helpers/images.py` (JPEG_BYTES / PNG_BYTES) — small but
    valid headers per `api_spec.md` §10.1.
    """

    def _make(*, token: str, kind: str = "jpeg") -> str:
        if kind == "jpeg":
            content, content_type, filename = (
                JPEG_BYTES,
                "image/jpeg",
                "seed.jpg",
            )
        elif kind == "png":
            content, content_type, filename = (
                PNG_BYTES,
                "image/png",
                "seed.png",
            )
        else:
            raise ValueError(f"unsupported image kind: {kind!r}")
        response = api_helpers.uploads_image(
            api_base_url,
            token=token,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        assert response.status_code == 201, (
            f"make_image_filename: POST /uploads/images failed: "
            f"{response.status_code} {response.text!r}"
        )
        body = response.json()
        assert isinstance(body, dict) and "filename" in body, (
            f"upload response missing `filename`: {body!r}"
        )
        return body["filename"]

    return _make


# ---------------------------------------------------------------------------
# Playwright fixtures.
# ---------------------------------------------------------------------------


# Default browser context size for desktop-shaped tests. The
# `pytest-playwright` `page` fixture uses Playwright's own default
# (1280x720 in current versions); we don't override the default
# globally so every desktop test sees the same viewport.

# Used as the small-screen breakpoint by the mobile-layout tests.
# DaisyUI's `md:` breakpoint kicks in at 768px (Tailwind default), so
# 360x640 (a common phone size) is comfortably below it.
MOBILE_VIEWPORT = {"width": 360, "height": 640}


@pytest.fixture
def mobile_page(context):
    """Yield a fresh Playwright `page` with a 360x640 viewport.

    The default `page` fixture from `pytest-playwright` uses a desktop
    viewport (1280x720). Mobile-layout tests use this fixture to
    exercise the small-screen breakpoint per `implementation_plan.md`
    §Phase 8 ("hamburger menu on small screens; full sidebar on md+").
    """
    page = context.new_page()
    page.set_viewport_size(MOBILE_VIEWPORT)
    try:
        yield page
    finally:
        page.close()
