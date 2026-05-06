"""POST /auth/register integration tests.

Spec: `.specs/ai_gen/api_spec.md` §2.2 (register), §3.1 (User shape),
§4 (Problem+JSON), §4.1 (error type registry).
"""

from __future__ import annotations

import re

import httpx

from tests.helpers import api as api_helpers

PROBLEM_JSON = "application/problem+json"
ERROR_VALIDATION = "https://recipes-manager.local/errors/validation"
ERROR_CONFLICT_USERNAME = "https://recipes-manager.local/errors/conflict-username"

ISO_8601_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


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
    assert body.get("status") == status, (
        f"Problem+JSON status field should mirror HTTP status {status}, "
        f"got {body.get('status')!r}"
    )
    return body


def _assert_user_shape(user: dict, *, expected_username: str, expected_full_name: str | None) -> None:
    """User representation per `api_spec.md §3.1`."""
    assert isinstance(user, dict), f"Expected User to be an object, got {type(user)!r}"
    assert "id" in user and isinstance(user["id"], int) and user["id"] > 0, (
        f"User.id must be a positive integer, got {user.get('id')!r}"
    )
    assert user.get("username") == expected_username, (
        f"User.username mismatch: expected {expected_username!r}, got {user.get('username')!r}"
    )
    assert user.get("full_name") == expected_full_name, (
        f"User.full_name mismatch: expected {expected_full_name!r}, got {user.get('full_name')!r}"
    )
    created_at = user.get("created_at")
    assert isinstance(created_at, str) and ISO_8601_Z_RE.match(created_at), (
        f"User.created_at must be ISO-8601 UTC with Z suffix, got {created_at!r}"
    )
    assert "pwd_hash" not in user, (
        f"User response must never include pwd_hash; full body: {user!r}"
    )
    assert "password" not in user, (
        f"User response must never include password; full body: {user!r}"
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_register_happy_path_returns_201_and_user(api_base_url: str) -> None:
    response = api_helpers.auth_register(
        api_base_url,
        username="alice",
        password="hunter2pwd",
        full_name="Alice Smith",
    )

    assert response.status_code == 201, (
        f"Expected 201 from /auth/register happy path, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    assert "application/json" in response.headers.get("content-type", ""), (
        f"Expected JSON response on 201, got {response.headers.get('content-type')!r}"
    )

    _assert_user_shape(response.json(), expected_username="alice", expected_full_name="Alice Smith")


def test_register_does_not_return_jwt(api_base_url: str) -> None:
    """Per spec §2.2: 'No JWT issued; client must call /login next.'"""
    response = api_helpers.auth_register(
        api_base_url, username="bob", password="hunter2pwd", full_name=None
    )

    assert response.status_code == 201
    body = response.json()
    assert "token" not in body, (
        f"/auth/register must not issue a JWT; body contains 'token': {body!r}"
    )


def test_register_full_name_omitted_is_accepted(api_base_url: str) -> None:
    response = api_helpers.auth_register(
        api_base_url, username="carol", password="hunter2pwd"
    )

    assert response.status_code == 201, (
        f"full_name omitted should be accepted; got {response.status_code} {response.text!r}"
    )
    _assert_user_shape(response.json(), expected_username="carol", expected_full_name=None)


def test_register_full_name_explicit_null_is_accepted(api_base_url: str) -> None:
    response = api_helpers.auth_register(
        api_base_url, username="dave", password="hunter2pwd", full_name=None
    )

    assert response.status_code == 201, (
        f"full_name=null should be accepted; got {response.status_code} {response.text!r}"
    )
    _assert_user_shape(response.json(), expected_username="dave", expected_full_name=None)


# ---------------------------------------------------------------------------
# Duplicate username -> 409 /errors/conflict-username
# ---------------------------------------------------------------------------


def test_register_duplicate_username_returns_409_conflict(api_base_url: str) -> None:
    first = api_helpers.auth_register(
        api_base_url, username="erin", password="hunter2pwd", full_name="Erin"
    )
    assert first.status_code == 201, (
        f"Setup: first registration must succeed; got {first.status_code} {first.text!r}"
    )

    second = api_helpers.auth_register(
        api_base_url, username="erin", password="anotherpwd123", full_name="Other Erin"
    )

    _assert_problem_json(second, status=409, type_uri=ERROR_CONFLICT_USERNAME)


# ---------------------------------------------------------------------------
# Validation -> 400 /errors/validation
# ---------------------------------------------------------------------------


def test_register_short_password_returns_400_validation(api_base_url: str) -> None:
    response = api_helpers.auth_register(
        api_base_url, username="frank", password="short"  # 5 chars; min is 8
    )

    _assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_register_password_at_min_length_is_accepted(api_base_url: str) -> None:
    """Min length per spec is 8."""
    response = api_helpers.auth_register(
        api_base_url, username="grace", password="x" * 8, full_name=None
    )

    assert response.status_code == 201, (
        f"8-char password is the documented minimum; got {response.status_code} {response.text!r}"
    )


def test_register_username_with_disallowed_chars_returns_400(api_base_url: str) -> None:
    """Spec: username must match `^[a-zA-Z0-9_.-]+$`."""
    response = api_helpers.auth_register(
        api_base_url,
        username="bad name!",  # space and `!` are disallowed
        password="hunter2pwd",
    )

    _assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_register_username_too_short_returns_400(api_base_url: str) -> None:
    """Spec: username 3-50 chars."""
    response = api_helpers.auth_register(
        api_base_url, username="ab", password="hunter2pwd"
    )

    _assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_register_username_too_long_returns_400(api_base_url: str) -> None:
    """Spec: username 3-50 chars."""
    response = api_helpers.auth_register(
        api_base_url,
        username="z" * 51,
        password="hunter2pwd",
    )

    _assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_register_missing_username_returns_400(api_base_url: str) -> None:
    response = httpx.post(
        f"{api_base_url}/auth/register",
        json={"password": "hunter2pwd"},
        timeout=10.0,
    )

    _assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_register_missing_password_returns_400(api_base_url: str) -> None:
    response = httpx.post(
        f"{api_base_url}/auth/register",
        json={"username": "harry"},
        timeout=10.0,
    )

    _assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
