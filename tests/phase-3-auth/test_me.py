"""GET /auth/me integration tests.

Spec: `.specs/ai_gen/api_spec.md` §2.2 (`/auth/me`), §2.1 (JWT claims),
§3.1 (User shape), §1.5 (auth header), §4.1 (error type registry).

Phase 3 must reject every flavour of bad credential with `401 Unauthorized`
and Problem+JSON `type=/errors/unauthorized`. The strategy lists three
core cases (missing / malformed / expired); the user-confirmed adjacents
are: no `Bearer ` prefix, wrong-secret signature, and a valid token whose
`sub` references a user that no longer exists.
"""

from __future__ import annotations

import datetime as dt
import re
import time

import httpx
import jwt as pyjwt

from tests.helpers import api as api_helpers

PROBLEM_JSON = "application/problem+json"
ERROR_UNAUTHORIZED = "https://recipes-manager.local/errors/unauthorized"

ISO_8601_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


def _assert_unauthorized(response: httpx.Response) -> dict:
    assert response.status_code == 401, (
        f"Expected 401 from /auth/me, got {response.status_code}. Body: {response.text!r}"
    )
    content_type = response.headers.get("content-type", "")
    assert PROBLEM_JSON in content_type, (
        f"401 must be Problem+JSON; got {content_type!r}. Body: {response.text!r}"
    )
    body = response.json()
    assert body.get("type") == ERROR_UNAUTHORIZED, (
        f"Expected type={ERROR_UNAUTHORIZED!r}, got type={body.get('type')!r}. "
        f"Full body: {body!r}"
    )
    assert body.get("status") == 401, (
        f"Problem+JSON status field should be 401, got {body.get('status')!r}"
    )
    return body


def _encode_jwt(secret: str, *, sub: str, username: str, ttl_seconds: int = 3600) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {"sub": sub, "username": username, "iat": now, "exp": now + ttl_seconds},
        secret,
        algorithm="HS256",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_me_with_valid_token_returns_user(api_base_url: str, make_user) -> None:
    user, token = make_user(username="alice", password="hunter2pwd", full_name="Alice Smith")

    response = api_helpers.auth_me(api_base_url, token=token)

    assert response.status_code == 200, (
        f"Expected 200 from /auth/me with valid token; got {response.status_code} "
        f"{response.text!r}"
    )
    body = response.json()
    assert body.get("id") == user["id"], (
        f"/auth/me should return the authenticated user (id={user['id']}); got id={body.get('id')!r}"
    )
    assert body.get("username") == "alice"
    assert body.get("full_name") == "Alice Smith"
    created_at = body.get("created_at")
    assert isinstance(created_at, str) and ISO_8601_Z_RE.match(created_at), (
        f"User.created_at must be ISO-8601 UTC with Z suffix; got {created_at!r}"
    )
    assert "pwd_hash" not in body and "password" not in body, (
        f"/auth/me must never leak credentials; body={body!r}"
    )


# ---------------------------------------------------------------------------
# Missing / malformed Authorization header
# ---------------------------------------------------------------------------


def test_me_without_authorization_header_returns_401(api_base_url: str) -> None:
    response = api_helpers.auth_me(api_base_url)
    _assert_unauthorized(response)


def test_me_with_authorization_missing_bearer_prefix_returns_401(
    api_base_url: str, jwt_secret: str
) -> None:
    """Spec §1.5: `Authorization: Bearer <jwt>`. Anything else is invalid."""
    token = _encode_jwt(jwt_secret, sub="1", username="alice")

    response = api_helpers.auth_me(api_base_url, raw_authorization=token)
    _assert_unauthorized(response)


def test_me_with_garbage_token_returns_401(api_base_url: str) -> None:
    response = api_helpers.auth_me(api_base_url, token="this-is-not-a-jwt")
    _assert_unauthorized(response)


def test_me_with_token_having_only_two_parts_returns_401(api_base_url: str) -> None:
    """A JWT has three dot-separated parts; two parts is malformed."""
    response = api_helpers.auth_me(api_base_url, token="header.payload")
    _assert_unauthorized(response)


# ---------------------------------------------------------------------------
# Bad signature / bad claims
# ---------------------------------------------------------------------------


def test_me_with_token_signed_by_wrong_secret_returns_401(
    api_base_url: str, make_user
) -> None:
    """Real registered user, but the token is signed with a different secret."""
    user, _real_token = make_user(username="bob", password="hunter2pwd", full_name="Bob")

    forged = _encode_jwt(
        "an-entirely-different-secret-not-the-backend-one",
        sub=str(user["id"]),
        username="bob",
    )

    response = api_helpers.auth_me(api_base_url, token=forged)
    _assert_unauthorized(response)


def test_me_with_expired_token_returns_401(
    api_base_url: str, make_user, jwt_secret: str
) -> None:
    """Forge a JWT signed by the right secret but with `exp` in the past."""
    user, _token = make_user(username="carol", password="hunter2pwd", full_name=None)

    now = int(time.time())
    expired = pyjwt.encode(
        {
            "sub": str(user["id"]),
            "username": "carol",
            "iat": now - 7200,
            "exp": now - 3600,  # 1 hour ago
        },
        jwt_secret,
        algorithm="HS256",
    )

    response = api_helpers.auth_me(api_base_url, token=expired)
    _assert_unauthorized(response)


def test_me_with_token_for_nonexistent_user_returns_401(
    api_base_url: str, jwt_secret: str
) -> None:
    """Valid signature, future exp, but `sub` doesn't correspond to any user.

    The autouse `_clean_db` fixture ensures the users table is empty at
    the start of each test, so id=999999 is guaranteed not to exist.
    """
    forged = _encode_jwt(jwt_secret, sub="999999", username="ghost")

    response = api_helpers.auth_me(api_base_url, token=forged)
    _assert_unauthorized(response)


def test_me_after_24h_jwt_lifetime_boundary(
    api_base_url: str, make_user, jwt_secret: str
) -> None:
    """A token whose `exp` is ~24h+1s in the past — verifies the lifetime
    boundary documented in spec §2.1 is actually enforced and not silently
    extended.
    """
    user, _token = make_user(username="dave", password="hunter2pwd", full_name=None)

    now = int(time.time())
    just_expired = pyjwt.encode(
        {
            "sub": str(user["id"]),
            "username": "dave",
            "iat": now - (24 * 3600 + 60),
            "exp": now - 60,
        },
        jwt_secret,
        algorithm="HS256",
    )

    response = api_helpers.auth_me(api_base_url, token=just_expired)
    _assert_unauthorized(response)


# ---------------------------------------------------------------------------
# Sanity: the issued token is actually accepted (regression guard)
# ---------------------------------------------------------------------------


def test_me_accepts_freshly_issued_token_after_login_roundtrip(api_base_url: str) -> None:
    reg = api_helpers.auth_register(
        api_base_url, username="erin", password="hunter2pwd", full_name="Erin"
    )
    assert reg.status_code == 201

    login = api_helpers.auth_login(
        api_base_url, username="erin", password="hunter2pwd"
    )
    assert login.status_code == 200
    token = login.json()["token"]

    me = api_helpers.auth_me(api_base_url, token=token)
    assert me.status_code == 200, (
        f"/auth/me should accept the token from /auth/login; got {me.status_code} {me.text!r}"
    )

    # Token's expires_at should be in the future.
    expires_at_str = login.json()["expires_at"]
    expires_at = dt.datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    assert expires_at > dt.datetime.now(tz=dt.timezone.utc), (
        f"expires_at should be in the future; got {expires_at_str!r}"
    )
