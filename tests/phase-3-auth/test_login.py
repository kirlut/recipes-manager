"""POST /auth/login integration tests.

Spec: `.specs/ai_gen/api_spec.md` §2.2 (login), §2.1 (JWT claims),
§3.1 (User shape), §4.1 (error type registry).

Notes on `expires_at`: §2.1 says JWT lifetime is 24 hours from issuance;
§2.2 shows `expires_at` as ISO 8601 in UTC. We assert the returned value
is ~24h ahead of the request time (with a generous tolerance for clock
skew, slow CI, and the test's own latency).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import httpx
import jwt as pyjwt

from tests.helpers import api as api_helpers

PROBLEM_JSON = "application/problem+json"
ERROR_UNAUTHORIZED = "https://recipes-manager.local/errors/unauthorized"

ISO_8601_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)

JWT_TTL_HOURS = 24
EXPIRES_AT_TOLERANCE_S = 5 * 60  # 5 minutes either side of the expected exp


def _assert_problem_json(response: httpx.Response, *, status: int, type_uri: str) -> dict:
    assert response.status_code == status, (
        f"Expected status {status}, got {response.status_code}. Body: {response.text!r}"
    )
    content_type = response.headers.get("content-type", "")
    assert PROBLEM_JSON in content_type, (
        f"Expected {PROBLEM_JSON} content-type, got {content_type!r}. "
        f"Body: {response.text!r}"
    )
    body = response.json()
    assert body.get("type") == type_uri, (
        f"Expected Problem+JSON type={type_uri!r}, got type={body.get('type')!r}. "
        f"Full body: {body!r}"
    )
    return body


def _parse_iso_z(s: str) -> dt.datetime:
    """Accept the strict `...Z` form the spec mandates."""
    assert ISO_8601_Z_RE.match(s), f"Not an ISO-8601 UTC string with Z suffix: {s!r}"
    # Python's fromisoformat does not accept 'Z' before 3.11 — but we require 3.12.
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_login_happy_path_returns_token_and_user(api_base_url: str, jwt_secret: str) -> None:
    reg = api_helpers.auth_register(
        api_base_url, username="alice", password="hunter2pwd", full_name="Alice Smith"
    )
    assert reg.status_code == 201, (
        f"Setup: register must succeed; got {reg.status_code} {reg.text!r}"
    )
    expected_user_id = reg.json()["id"]

    sent_at = dt.datetime.now(tz=dt.timezone.utc)
    response = api_helpers.auth_login(
        api_base_url, username="alice", password="hunter2pwd"
    )

    assert response.status_code == 200, (
        f"Expected 200 from /auth/login happy path, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    body = response.json()

    # Top-level shape
    assert set(body.keys()) >= {"token", "expires_at", "user"}, (
        f"Login response missing required keys; got keys={sorted(body)}"
    )

    # Token is a non-empty string and decodes with the test secret.
    token: str = body["token"]
    assert isinstance(token, str) and token, f"Login token must be a non-empty string, got {token!r}"

    decoded: dict[str, Any] = pyjwt.decode(token, jwt_secret, algorithms=["HS256"])
    assert decoded.get("sub") == str(expected_user_id), (
        f"JWT.sub should be the user id as a string per spec §2.1; "
        f"expected {expected_user_id!r} (str), got {decoded.get('sub')!r}"
    )
    assert decoded.get("username") == "alice", (
        f"JWT.username should be the registered username; got {decoded.get('username')!r}"
    )
    assert "iat" in decoded and "exp" in decoded, (
        f"JWT must include iat and exp; decoded={decoded!r}"
    )
    assert decoded["exp"] - decoded["iat"] == JWT_TTL_HOURS * 3600, (
        f"JWT lifetime must be exactly 24h per spec §2.1; "
        f"got {decoded['exp'] - decoded['iat']}s"
    )

    # expires_at is ~24h from sent_at, in ISO 8601 UTC `Z` form.
    expires_at = _parse_iso_z(body["expires_at"])
    expected_expiry = sent_at + dt.timedelta(hours=JWT_TTL_HOURS)
    delta_s = abs((expires_at - expected_expiry).total_seconds())
    assert delta_s <= EXPIRES_AT_TOLERANCE_S, (
        f"expires_at should be ~24h from request time; "
        f"got {expires_at.isoformat()}, expected near {expected_expiry.isoformat()}, "
        f"delta={delta_s}s"
    )

    # User shape
    user = body["user"]
    assert user.get("id") == expected_user_id
    assert user.get("username") == "alice"
    assert user.get("full_name") == "Alice Smith"
    assert isinstance(user.get("created_at"), str) and ISO_8601_Z_RE.match(user["created_at"])
    assert "pwd_hash" not in user
    assert "password" not in user


# ---------------------------------------------------------------------------
# Wrong password / unknown username -> 401, no enumeration
# ---------------------------------------------------------------------------


def test_login_wrong_password_returns_401(api_base_url: str) -> None:
    reg = api_helpers.auth_register(
        api_base_url, username="bob", password="hunter2pwd", full_name="Bob"
    )
    assert reg.status_code == 201

    response = api_helpers.auth_login(
        api_base_url, username="bob", password="wrong-password"
    )

    body = _assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)
    assert "token" not in body, (
        f"401 response must not leak a token; body={body!r}"
    )


def test_login_unknown_username_returns_401(api_base_url: str) -> None:
    response = api_helpers.auth_login(
        api_base_url, username="nobody-here", password="hunter2pwd"
    )

    _assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_login_unknown_username_and_wrong_password_share_error_type(api_base_url: str) -> None:
    """Spec §2.2: 'the API does not differentiate, to avoid username enumeration.'

    Both branches must return the **same** Problem+JSON `type`. We don't
    assert byte-equal bodies (the `instance` field will match either way,
    and `detail` may legitimately omit specifics) — only that the type URI
    is identical.
    """
    reg = api_helpers.auth_register(
        api_base_url, username="carol", password="hunter2pwd", full_name=None
    )
    assert reg.status_code == 201

    wrong_pwd = api_helpers.auth_login(
        api_base_url, username="carol", password="wrong-password"
    )
    unknown_user = api_helpers.auth_login(
        api_base_url, username="someone-else", password="hunter2pwd"
    )

    assert wrong_pwd.status_code == 401, (
        f"wrong password should be 401; got {wrong_pwd.status_code} {wrong_pwd.text!r}"
    )
    assert unknown_user.status_code == 401, (
        f"unknown user should be 401; got {unknown_user.status_code} {unknown_user.text!r}"
    )
    assert wrong_pwd.json().get("type") == unknown_user.json().get("type"), (
        "Login error type must not differ between wrong-password and unknown-username "
        "(prevents username enumeration). Got "
        f"wrong_pwd.type={wrong_pwd.json().get('type')!r} vs "
        f"unknown_user.type={unknown_user.json().get('type')!r}"
    )


# ---------------------------------------------------------------------------
# Malformed body -> 400 (sanity, not the focus of phase 3)
# ---------------------------------------------------------------------------


def test_login_missing_password_returns_400(api_base_url: str) -> None:
    response = httpx.post(
        f"{api_base_url}/auth/login",
        json={"username": "alice"},
        timeout=10.0,
    )

    assert response.status_code == 400, (
        f"Expected 400 for missing password; got {response.status_code} {response.text!r}"
    )
    content_type = response.headers.get("content-type", "")
    assert PROBLEM_JSON in content_type, (
        f"Expected {PROBLEM_JSON} content-type on 400; got {content_type!r}"
    )
