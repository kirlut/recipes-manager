"""Thin HTTP helpers for auth endpoints.

The repo's `api_spec.md §1.1` defines that backend FastAPI routes are
unprefixed (the `/api/` prefix is added by nginx in production). Backend-
only test phases (3-7) bind FastAPI directly to a host port, so callers
pass a `base_url` like `http://127.0.0.1:18000` and these helpers append
`/auth/*` straight onto it.
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
