"""Shared response-shape assertions for integration tests.

Phase-3 test files inlined these constants and helpers. From phase 4
onward we import them so the six new test files don't each carry their
own copy. Phase-3 tests continue to use their inline copies (frozen, by
the rule that tests aren't edited during later phases).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"
JSON_MEDIA_TYPE = "application/json"

ISO_8601_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)

UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_ERROR_BASE = "https://recipes-manager.local/errors"

ERROR_VALIDATION = f"{_ERROR_BASE}/validation"
ERROR_INVALID_CURSOR = f"{_ERROR_BASE}/invalid-cursor"
ERROR_UNAUTHORIZED = f"{_ERROR_BASE}/unauthorized"
ERROR_FORBIDDEN_NOT_OWNER = f"{_ERROR_BASE}/forbidden-not-owner"
ERROR_NOT_FOUND = f"{_ERROR_BASE}/not-found"
ERROR_CONFLICT_USERNAME = f"{_ERROR_BASE}/conflict-username"
ERROR_CONFLICT = f"{_ERROR_BASE}/conflict"
ERROR_PAYLOAD_TOO_LARGE = f"{_ERROR_BASE}/payload-too-large"
ERROR_UNSUPPORTED_MEDIA_TYPE = f"{_ERROR_BASE}/unsupported-media-type"
ERROR_NO_NUTRITION_FACTS = f"{_ERROR_BASE}/no-nutrition-facts"
ERROR_DUPLICATE_NUTRITION_FACT = f"{_ERROR_BASE}/duplicate-nutrition-fact"
ERROR_INTERNAL = f"{_ERROR_BASE}/internal"


def assert_problem_json(
    response: httpx.Response, *, status: int, type_uri: str
) -> dict[str, Any]:
    """Assert the response is a Problem+JSON envelope per api_spec §4.

    Returns the parsed body for follow-up assertions (e.g. on
    ``extensions.violations``).
    """
    assert response.status_code == status, (
        f"Expected status {status}, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    content_type = response.headers.get("content-type", "")
    assert PROBLEM_JSON_MEDIA_TYPE in content_type, (
        f"Expected {PROBLEM_JSON_MEDIA_TYPE} content-type, got {content_type!r}. "
        f"Body: {response.text!r}"
    )
    body = response.json()
    assert body.get("type") == type_uri, (
        f"Expected Problem+JSON type={type_uri!r}, "
        f"got type={body.get('type')!r}. Full body: {body!r}"
    )
    assert body.get("status") == status, (
        f"Problem+JSON status field should mirror HTTP status {status}, "
        f"got {body.get('status')!r}"
    )
    return body


def assert_iso_8601_z(value: Any, *, field: str) -> None:
    """Assert a value matches ISO-8601 with `Z` UTC suffix per api_spec §1.3."""
    assert isinstance(value, str) and ISO_8601_Z_RE.match(value), (
        f"{field} must be ISO-8601 UTC with Z suffix, got {value!r}"
    )
