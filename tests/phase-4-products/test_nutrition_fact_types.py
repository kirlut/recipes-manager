"""GET /nutrition-fact-types integration tests.

Spec: `.specs/ai_gen/api_spec.md` §11 (read-only seeded list, no
pagination), §3.3 (NutritionFactType shape), §1.5 (auth required).
Seed contents: `db_schema.md` §6.
"""

from __future__ import annotations

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    JSON_MEDIA_TYPE,
    ERROR_UNAUTHORIZED,
    assert_problem_json,
)

EXPECTED_SEED = {
    "Energy": "kcal",
    "Protein": "g",
    "Net Carbs": "g",
    "Fat": "g",
    "Fibers": "g",
}


def test_unauthenticated_returns_401(api_base_url: str) -> None:
    response = api_helpers.nutrition_fact_types_list(api_base_url, token=None)

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_returns_seeded_list(api_base_url: str, make_user) -> None:
    _user, token = make_user(username="nft_reader", password="hunter2pwd")

    response = api_helpers.nutrition_fact_types_list(api_base_url, token=token)

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text!r}"
    )
    assert JSON_MEDIA_TYPE in response.headers.get("content-type", ""), (
        f"Expected JSON content-type, got {response.headers.get('content-type')!r}"
    )
    body = response.json()

    # Per api_spec §11.1: the list endpoint returns `items` only — no `next`,
    # no `cursor` (it's small and bounded, deliberately unpaginated).
    assert "items" in body, f"Response missing 'items' field: {body!r}"
    assert "next" not in body, (
        f"GET /nutrition-fact-types must not be paginated; got 'next' in {body!r}"
    )
    assert "cursor" not in body, (
        f"GET /nutrition-fact-types must not be paginated; got 'cursor' in {body!r}"
    )

    items = body["items"]
    assert isinstance(items, list), f"items must be an array, got {type(items)!r}"

    by_name = {item["name"]: item for item in items}
    assert set(by_name.keys()) == set(EXPECTED_SEED.keys()), (
        f"Seeded names mismatch: expected {sorted(EXPECTED_SEED)!r}, "
        f"got {sorted(by_name)!r}"
    )

    seen_ids: set[int] = set()
    for name, expected_unit in EXPECTED_SEED.items():
        item = by_name[name]
        assert item.get("unit") == expected_unit, (
            f"{name}: expected unit={expected_unit!r}, "
            f"got {item.get('unit')!r}"
        )
        item_id = item.get("id")
        assert isinstance(item_id, int) and item_id > 0, (
            f"{name}: id must be positive int, got {item_id!r}"
        )
        assert item_id not in seen_ids, (
            f"Duplicate id {item_id} across nutrition fact types: {items!r}"
        )
        seen_ids.add(item_id)


def test_response_is_stable_across_calls(api_base_url: str, make_user) -> None:
    """Re-reading after no mutation returns identical ids (per
    db_schema.md §6, ids are not the contract — but they must be stable
    while the row exists)."""
    _user, token = make_user(username="nft_stable", password="hunter2pwd")

    first = api_helpers.nutrition_fact_types_list(api_base_url, token=token).json()
    second = api_helpers.nutrition_fact_types_list(api_base_url, token=token).json()

    first_by_name = {item["name"]: item["id"] for item in first["items"]}
    second_by_name = {item["name"]: item["id"] for item in second["items"]}
    assert first_by_name == second_by_name, (
        f"NFT ids changed between calls: first={first_by_name!r}, "
        f"second={second_by_name!r}"
    )
