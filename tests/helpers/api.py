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


# ---------------------------------------------------------------------------
# Phase 5 helpers — recipes.
# ---------------------------------------------------------------------------


def recipes_create(
    base_url: str,
    *,
    token: str | None,
    body: dict[str, Any],
) -> httpx.Response:
    """POST /recipes — see api_spec §7.1.

    `body` is sent verbatim so tests can exercise validation paths
    (missing fields, duplicate product_id, etc.) without normalisation.
    """
    return httpx.post(
        f"{base_url}/recipes",
        json=body,
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_get(
    base_url: str,
    *,
    token: str | None,
    recipe_id: int,
) -> httpx.Response:
    """GET /recipes/{id} — see api_spec §7.2."""
    return httpx.get(
        f"{base_url}/recipes/{recipe_id}",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_update(
    base_url: str,
    *,
    token: str | None,
    recipe_id: int,
    body: dict[str, Any],
) -> httpx.Response:
    """PUT /recipes/{id} — see api_spec §7.3."""
    return httpx.put(
        f"{base_url}/recipes/{recipe_id}",
        json=body,
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_delete(
    base_url: str,
    *,
    token: str | None,
    recipe_id: int,
) -> httpx.Response:
    """DELETE /recipes/{id} — see api_spec §7.4."""
    return httpx.delete(
        f"{base_url}/recipes/{recipe_id}",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_copy(
    base_url: str,
    *,
    token: str | None,
    recipe_id: int,
) -> httpx.Response:
    """POST /recipes/{id}/copy with empty body, per api_spec §7.5."""
    return httpx.post(
        f"{base_url}/recipes/{recipe_id}/copy",
        json={},
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Phase 6 helpers — listing + search + pagination + starring.
# ---------------------------------------------------------------------------


def _list_params(
    *,
    scope: Any = _OMIT,
    q: Any = _OMIT,
    cursor: Any = _OMIT,
    limit: Any = _OMIT,
) -> list[tuple[str, str]]:
    """Build the query-param list, omitting `_OMIT` entries.

    Sentinel-based to let tests pass `scope=""` or `q=""` deliberately
    (different from "field absent"). A list-of-tuples is used over a
    dict so duplicate keys could be sent if a future test needed it.
    """
    params: list[tuple[str, str]] = []
    if scope is not _OMIT:
        params.append(("scope", str(scope)))
    if q is not _OMIT:
        params.append(("q", str(q)))
    if cursor is not _OMIT:
        params.append(("cursor", str(cursor)))
    if limit is not _OMIT:
        params.append(("limit", str(limit)))
    return params


def products_list(
    base_url: str,
    *,
    token: str | None,
    scope: Any = _OMIT,
    q: Any = _OMIT,
    cursor: Any = _OMIT,
    limit: Any = _OMIT,
) -> httpx.Response:
    """GET /products with cursor pagination (api_spec §5, §6.6).

    Any parameter left as the `_OMIT` sentinel is not sent at all, so
    tests can exercise the "missing required param" validation paths.
    """
    return httpx.get(
        f"{base_url}/products",
        params=_list_params(scope=scope, q=q, cursor=cursor, limit=limit),
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_list(
    base_url: str,
    *,
    token: str | None,
    scope: Any = _OMIT,
    q: Any = _OMIT,
    cursor: Any = _OMIT,
    limit: Any = _OMIT,
) -> httpx.Response:
    """GET /recipes with cursor pagination (api_spec §5, §7.6)."""
    return httpx.get(
        f"{base_url}/recipes",
        params=_list_params(scope=scope, q=q, cursor=cursor, limit=limit),
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def list_follow_next(
    base_url: str,
    *,
    token: str | None,
    next_url: str,
) -> httpx.Response:
    """Follow the `next` URL from a paginated list response.

    `api_spec.md` §5.2 returns `next` as a path-style URL (e.g.
    `/api/products?cursor=…&limit=10` or `/products?cursor=…&limit=10`,
    depending on whether the backend prefixes its emitted URLs).
    Backend-only test phases hit FastAPI directly without nginx, so
    we strip an optional leading `/api` before joining onto `base_url`.
    """
    path = next_url
    if path.startswith("http://") or path.startswith("https://"):
        # Absolute URL; use verbatim.
        return httpx.get(path, headers=_auth_headers(token), timeout=_TIMEOUT)
    if path.startswith("/api/"):
        path = path[len("/api") :]  # leaves the leading `/`
    if not path.startswith("/"):
        path = "/" + path
    return httpx.get(
        f"{base_url}{path}",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_star(
    base_url: str,
    *,
    token: str | None,
    product_id: int,
) -> httpx.Response:
    """PUT /products/{id}/star — idempotent star (api_spec §8.2)."""
    return httpx.put(
        f"{base_url}/products/{product_id}/star",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def products_unstar(
    base_url: str,
    *,
    token: str | None,
    product_id: int,
) -> httpx.Response:
    """DELETE /products/{id}/star — idempotent unstar (api_spec §8.2)."""
    return httpx.delete(
        f"{base_url}/products/{product_id}/star",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_star(
    base_url: str,
    *,
    token: str | None,
    recipe_id: int,
) -> httpx.Response:
    """PUT /recipes/{id}/star — idempotent star (api_spec §8.1)."""
    return httpx.put(
        f"{base_url}/recipes/{recipe_id}/star",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


def recipes_unstar(
    base_url: str,
    *,
    token: str | None,
    recipe_id: int,
) -> httpx.Response:
    """DELETE /recipes/{id}/star — idempotent unstar (api_spec §8.1)."""
    return httpx.delete(
        f"{base_url}/recipes/{recipe_id}/star",
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Phase 7 helpers — shopping list.
# ---------------------------------------------------------------------------


def shopping_list_compute(
    base_url: str,
    *,
    token: str | None,
    body: dict[str, Any],
) -> httpx.Response:
    """POST /shopping-list — see api_spec §9.1.

    `body` is sent verbatim so tests can exercise validation paths
    (empty items, missing items, duplicate recipe_id, servings <= 0,
    unknown recipe_id, not-accessible recipe_id, etc.) without
    normalisation.
    """
    return httpx.post(
        f"{base_url}/shopping-list",
        json=body,
        headers=_auth_headers(token),
        timeout=_TIMEOUT,
    )
