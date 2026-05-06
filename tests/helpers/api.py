"""Thin HTTP helpers for backend endpoints.

The repo's `api_spec.md §1.1` defines that backend FastAPI routes are
unprefixed (the `/api/` prefix is added by nginx in production). Backend-
only test phases (3-7) bind FastAPI directly to a host port, so callers
pass a `base_url` like `http://127.0.0.1:18000` and these helpers append
the unprefixed path (e.g. `/auth/login`, `/products`, `/uploads/images`)
straight onto it.
"""

from __future__ import annotations

from typing import Any

import httpx

_TIMEOUT = 10.0

# Sentinel for "field omitted from JSON body" vs. "field present but null".
# Tests need to distinguish the two for the optional `full_name` field.
_OMIT: Any = object()


def auth_register(
    base_url: str,
    *,
    username: str,
    password: str,
    full_name: Any = _OMIT,
) -> httpx.Response:
    """POST /auth/register.

    `full_name` semantics:
    - default (`_OMIT`): omit the field entirely from the JSON body.
    - `None`: send `"full_name": null`.
    - any string: send the string.
    """
    body: dict[str, Any] = {"username": username, "password": password}
    if full_name is not _OMIT:
        body["full_name"] = full_name
    return httpx.post(f"{base_url}/auth/register", json=body, timeout=_TIMEOUT)


def auth_login(base_url: str, *, username: str, password: str) -> httpx.Response:
    """POST /auth/login."""
    return httpx.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=_TIMEOUT,
    )


def auth_me(base_url: str, *, token: str | None = None, raw_authorization: str | None = None) -> httpx.Response:
    """GET /auth/me.

    Use `token` to send `Authorization: Bearer <token>`. Use `raw_authorization`
    to send a header value verbatim (for the no-`Bearer ` and similar cases).
    Pass neither to send no `Authorization` header at all.
    """
    headers: dict[str, str] = {}
    if token is not None and raw_authorization is not None:
        raise ValueError("pass token OR raw_authorization, not both")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    elif raw_authorization is not None:
        headers["Authorization"] = raw_authorization
    return httpx.get(f"{base_url}/auth/me", headers=headers, timeout=_TIMEOUT)


# ---------------------------------------------------------------------------
# Phase 4 helpers — products, uploads, nutrition fact types.
# ---------------------------------------------------------------------------


def _auth_headers(token: str | None) -> dict[str, str]:
    """`Authorization: Bearer <token>` if a token is given, else no header.

    Pass `token=None` to exercise the unauthenticated 401 path.
    """
    if token is None:
        return {}
    return {"Authorization": f"Bearer {token}"}


def nutrition_fact_types_list(base_url: str, *, token: str | None) -> httpx.Response:
    """GET /nutrition-fact-types — read-only list of seeded types."""
    return httpx.get(
        f"{base_url}/nutrition-fact-types",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_create(
    base_url: str,
    *,
    token: str | None,
    body: dict[str, Any],
) -> httpx.Response:
    """POST /products.

    `body` is sent verbatim. Tests pass partial/invalid bodies on purpose
    to cover the validation paths; do not normalise here.
    """
    return httpx.post(
        f"{base_url}/products",
        json=body,
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_get(
    base_url: str,
    *,
    token: str | None,
    product_id: int,
) -> httpx.Response:
    return httpx.get(
        f"{base_url}/products/{product_id}",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_update(
    base_url: str,
    *,
    token: str | None,
    product_id: int,
    body: dict[str, Any],
) -> httpx.Response:
    return httpx.put(
        f"{base_url}/products/{product_id}",
        json=body,
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_delete(
    base_url: str,
    *,
    token: str | None,
    product_id: int,
) -> httpx.Response:
    return httpx.delete(
        f"{base_url}/products/{product_id}",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_copy(
    base_url: str,
    *,
    token: str | None,
    product_id: int,
) -> httpx.Response:
    """POST /products/{id}/copy with empty body, per api_spec §6.5."""
    return httpx.post(
        f"{base_url}/products/{product_id}/copy",
        json={},
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def uploads_image(
    base_url: str,
    *,
    token: str | None,
    filename: str | None,
    content: bytes,
    content_type: str,
) -> httpx.Response:
    """POST /uploads/images with a multipart `file` part (api_spec §10.1).

    Pass `filename=None` to send a file part without a `filename=` parameter
    (some clients omit it; the backend must still accept the bytes).
    """
    files = {"file": (filename, content, content_type)}
    return httpx.post(
        f"{base_url}/uploads/images",
        files=files,
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def uploads_image_no_part(
    base_url: str,
    *,
    token: str | None,
) -> httpx.Response:
    """POST /uploads/images without the required `file` form part.

    The backend should reject with 400 `/errors/validation` since `file`
    is the sole required form field per api_spec §10.1.
    """
    return httpx.post(
        f"{base_url}/uploads/images",
        files={"not_file": ("ignored", b"", "application/octet-stream")},
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )
