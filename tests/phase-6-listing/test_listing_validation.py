"""Listing endpoint parameter contract.

Spec: `.specs/ai_gen/api_spec.md` §5.1 (limit + cursor), §6.6 / §7.6
(`scope`, `q`), §4.1 (error registry). Each invalid parameter case is
parametrised across `/products` and `/recipes` so the symmetry of the
two endpoints is enforced explicitly.

The strategy doc for Phase 6 doesn't enumerate this file by name, but
`testing_strategy.md` §5 says "Implementation in each phase must produce
**at least** these files, but may add more." Splitting the contract
checks out of `test_pagination.py` keeps each file focused.
"""

from __future__ import annotations

import base64
import json
from typing import Callable

import httpx
import pytest

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_INVALID_CURSOR,
    ERROR_UNAUTHORIZED,
    ERROR_VALIDATION,
    assert_problem_json,
)


# ---------------------------------------------------------------------------
# Fixtures shared across this file.
# ---------------------------------------------------------------------------

ListFn = Callable[..., httpx.Response]


@pytest.fixture
def list_fns(api_base_url: str) -> list[tuple[str, ListFn]]:
    """`(label, callable)` pairs for the two list endpoints.

    Tests use this to parametrise across `/products` and `/recipes`.
    The label is used in assertion messages so the failing endpoint is
    immediately obvious.
    """

    def call_products(**kwargs) -> httpx.Response:
        return api_helpers.products_list(api_base_url, **kwargs)

    def call_recipes(**kwargs) -> httpx.Response:
        return api_helpers.recipes_list(api_base_url, **kwargs)

    return [("products", call_products), ("recipes", call_recipes)]


# ---------------------------------------------------------------------------
# scope: required, must be one of mine/starred/search.
# ---------------------------------------------------------------------------


def test_missing_scope_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    _user, token = make_user(username="alice_missing_scope", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token)
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] missing `scope` should return 400, "
            f"got {response.status_code} body={response.text!r}"
        )


def test_invalid_scope_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    """`scope` is constrained to `mine|starred|search` per api_spec §6.6/§7.6."""
    _user, token = make_user(username="alice_invalid_scope", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token, scope="everyone")
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] invalid scope=everyone must 400, "
            f"got {response.status_code}: {response.text!r}"
        )


# ---------------------------------------------------------------------------
# q: required when scope=search, must be 1-200 chars.
# ---------------------------------------------------------------------------


def test_search_without_q_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    _user, token = make_user(username="alice_search_no_q", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token, scope="search")
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] scope=search without `q` must 400, "
            f"got {response.status_code}: {response.text!r}"
        )


def test_search_with_empty_q_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    """api_spec §6.6: `q` is 1-200 chars when scope=search; empty rejected."""
    _user, token = make_user(username="alice_search_empty_q", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token, scope="search", q="")
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] scope=search&q= (empty) must 400, "
            f"got {response.status_code}: {response.text!r}"
        )


# ---------------------------------------------------------------------------
# limit: integer in [1, 100].
# ---------------------------------------------------------------------------


def test_limit_zero_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    _user, token = make_user(username="alice_limit_zero", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token, scope="mine", limit=0)
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] limit=0 must 400, got {response.status_code}: {response.text!r}"
        )


def test_limit_above_100_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    _user, token = make_user(username="alice_limit_101", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token, scope="mine", limit=101)
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] limit=101 must 400, got {response.status_code}: {response.text!r}"
        )


def test_limit_non_integer_returns_400(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    _user, token = make_user(username="alice_limit_abc", password="hunter2pwd")
    for label, call in list_fns:
        response = call(token=token, scope="mine", limit="abc")
        assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)
        assert response.status_code == 400, (
            f"[{label}] limit=abc must 400, got {response.status_code}: {response.text!r}"
        )


# ---------------------------------------------------------------------------
# cursor: opaque base64url; foreign or malformed cursors → 400 invalid-cursor.
# ---------------------------------------------------------------------------


def test_malformed_cursor_returns_400_invalid_cursor(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    """api_spec §5.1, §5.3: undecodable cursors produce `/errors/invalid-cursor`."""
    _user, token = make_user(username="alice_bad_cursor", password="hunter2pwd")
    # `!!` is not a valid base64url character; payload is also not JSON.
    bad_cursor = "not-base64!!"
    for label, call in list_fns:
        response = call(token=token, scope="mine", cursor=bad_cursor)
        assert_problem_json(response, status=400, type_uri=ERROR_INVALID_CURSOR)
        assert response.status_code == 400, (
            f"[{label}] malformed cursor must 400 with invalid-cursor type, "
            f"got {response.status_code}: {response.text!r}"
        )


def test_cursor_with_wrong_kind_returns_400_invalid_cursor(
    list_fns: list[tuple[str, ListFn]],
    make_user,
) -> None:
    """api_spec §5.3: a cursor whose `k` doesn't match the endpoint's expected
    sort produces `/errors/invalid-cursor`. We craft a `sim_id` cursor (the
    search-mode shape) and pass it to a chronological `scope=mine` request.
    """
    _user, token = make_user(username="alice_wrong_cursor", password="hunter2pwd")
    payload = {"k": "sim_id", "v": [0.5, 1]}
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    for label, call in list_fns:
        response = call(token=token, scope="mine", cursor=encoded)
        assert_problem_json(response, status=400, type_uri=ERROR_INVALID_CURSOR)
        assert response.status_code == 400, (
            f"[{label}] wrong-kind cursor must 400 with invalid-cursor, "
            f"got {response.status_code}: {response.text!r}"
        )


# ---------------------------------------------------------------------------
# Auth: listing requires a valid bearer token (api_spec §1.5, §15).
# ---------------------------------------------------------------------------


def test_listing_without_token_returns_401(
    list_fns: list[tuple[str, ListFn]],
) -> None:
    for label, call in list_fns:
        response = call(token=None, scope="mine")
        assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)
        assert response.status_code == 401, (
            f"[{label}] anonymous listing must 401, "
            f"got {response.status_code}: {response.text!r}"
        )
