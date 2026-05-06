"""Cursor-based pagination integration tests.

Spec: `.specs/ai_gen/api_spec.md` §5 (pagination), §6.6 (`GET /products`),
§7.6 (`GET /recipes`). The strategy doc anchors this file to the
"25 recipes for User A, scope=mine&limit=10" walkthrough; we add a
default-limit smoke test, an empty-result smoke test, and a smoke
parity check on `GET /products` so both list endpoints are exercised.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    JSON_MEDIA_TYPE,
    assert_pagination_envelope,
)


# ---------------------------------------------------------------------------
# Helpers — keep the tests focused on behaviour rather than plumbing.
# ---------------------------------------------------------------------------


def _seed_recipes(make_recipe, *, token: str, count: int) -> list[dict]:
    """Create `count` recipes with distinct names; return them in creation order.

    api_spec §5.3 specifies chronological lists are sorted
    `(created_at DESC, id DESC)`. Postgres `now()` is monotonic enough at
    microsecond granularity that creation order matches descending sort
    order (newest first). The list returned here is **creation order**
    (oldest first); callers reverse it when comparing against listing
    output.
    """
    recipes: list[dict] = []
    for i in range(count):
        # Zero-pad so names sort lexicographically and any debugging
        # output is easy to scan.
        recipes.append(
            make_recipe(token=token, name=f"Recipe {i:03d}")
        )
    return recipes


def _seed_products(
    make_product, *, token: str, nutrition_fact_ids: dict[str, int], count: int
) -> list[dict]:
    """Create `count` products with the minimal required nutrition fact."""
    facts = [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 100,
        }
    ]
    products: list[dict] = []
    for i in range(count):
        products.append(
            make_product(
                token=token,
                name=f"Product {i:03d}",
                nutrition_facts=facts,
            )
        )
    return products


def _walk_pages(
    api_base_url: str,
    *,
    token: str,
    first: Any,
) -> list[dict]:
    """Walk `next` links starting from a parsed first-page body, return
    the concatenated `items` list across every page.

    Asserts the envelope shape on each page; raises if a page omits
    `items`. Stops when a page has no `next` field. Caps at 100 pages
    to keep a misbehaving server from hanging the test.
    """
    accumulated: list[dict] = list(first["items"])
    body: dict = first
    pages_walked = 1
    while "next" in body:
        pages_walked += 1
        assert pages_walked <= 100, (
            f"Refusing to follow more than 100 pages — server likely "
            f"emitting a non-terminating cursor. Last body: {body!r}"
        )
        response = api_helpers.list_follow_next(
            api_base_url, token=token, next_url=body["next"]
        )
        assert response.status_code == 200, (
            f"GET {body['next']!r} expected 200, "
            f"got {response.status_code}. Body: {response.text!r}"
        )
        body = response.json()
        assert isinstance(body.get("items"), list), (
            f"Page following {body!r} missing `items` list"
        )
        accumulated.extend(body["items"])
    return accumulated


# ---------------------------------------------------------------------------
# 25-recipe walkthrough — the canonical scenario from testing_strategy.md §5.
# ---------------------------------------------------------------------------


def test_recipes_scope_mine_paginates_25_in_pages_of_10(
    api_base_url: str,
    make_user,
    make_recipe,
) -> None:
    user, token = make_user(username="alice_pag_recipes", password="hunter2pwd")
    seeded = _seed_recipes(make_recipe, token=token, count=25)
    seeded_ids = [r["id"] for r in seeded]

    response = api_helpers.recipes_list(
        api_base_url, token=token, scope="mine", limit=10
    )
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text!r}"
    )
    assert JSON_MEDIA_TYPE in response.headers.get("content-type", "")

    page1 = response.json()
    assert_pagination_envelope(page1, expect_next=True)
    assert len(page1["items"]) == 10, (
        f"Page 1 must have exactly 10 items at limit=10, "
        f"got {len(page1['items'])}: {page1['items']!r}"
    )
    page1_ids = [item["id"] for item in page1["items"]]

    response2 = api_helpers.list_follow_next(
        api_base_url, token=token, next_url=page1["next"]
    )
    assert response2.status_code == 200, response2.text
    page2 = response2.json()
    assert_pagination_envelope(page2, expect_next=True)
    assert len(page2["items"]) == 10, (
        f"Page 2 must have exactly 10 items, got {len(page2['items'])}"
    )
    page2_ids = [item["id"] for item in page2["items"]]

    response3 = api_helpers.list_follow_next(
        api_base_url, token=token, next_url=page2["next"]
    )
    assert response3.status_code == 200, response3.text
    page3 = response3.json()
    assert_pagination_envelope(page3, expect_next=False)
    assert len(page3["items"]) == 5, (
        f"Page 3 (final) must have exactly 5 items "
        f"(25 - 10 - 10), got {len(page3['items'])}"
    )
    page3_ids = [item["id"] for item in page3["items"]]

    # No overlap across pages.
    assert len(set(page1_ids) & set(page2_ids)) == 0, (
        f"Pages 1 and 2 must not overlap. "
        f"Page 1: {page1_ids!r}, Page 2: {page2_ids!r}"
    )
    assert len(set(page2_ids) & set(page3_ids)) == 0, (
        f"Pages 2 and 3 must not overlap. "
        f"Page 2: {page2_ids!r}, Page 3: {page3_ids!r}"
    )
    assert len(set(page1_ids) & set(page3_ids)) == 0, (
        f"Pages 1 and 3 must not overlap"
    )

    # Union equals seeded set.
    union_ids = set(page1_ids) | set(page2_ids) | set(page3_ids)
    assert union_ids == set(seeded_ids), (
        f"Union of pages must equal seeded recipe ids. "
        f"Missing: {set(seeded_ids) - union_ids!r}, "
        f"Extra: {union_ids - set(seeded_ids)!r}"
    )

    # Sort order is descending by creation order — newest first overall.
    walked_ids = page1_ids + page2_ids + page3_ids
    expected_order = list(reversed(seeded_ids))
    assert walked_ids == expected_order, (
        f"Pagination must traverse recipes newest-first per "
        f"api_spec §5.3 (`created_at DESC, id DESC`). "
        f"Walked: {walked_ids!r}, expected: {expected_order!r}"
    )

    # Every list item shows it belongs to the caller. api_spec §6.6 lists
    # a `created_by` UserRef on each list item; recipes mirror products
    # per §7.6, so `created_by.id` should equal the caller's id.
    for item in page1["items"] + page2["items"] + page3["items"]:
        created_by = item.get("created_by")
        assert isinstance(created_by, dict), (
            f"List item must include `created_by` UserRef, got {item!r}"
        )
        assert created_by.get("id") == user["id"], (
            f"`scope=mine` items must be owned by caller id={user['id']}, "
            f"got created_by={created_by!r} on item={item!r}"
        )


# ---------------------------------------------------------------------------
# Default-limit and empty-result smoke tests.
# ---------------------------------------------------------------------------


def test_recipes_scope_mine_default_limit_is_20(
    api_base_url: str,
    make_user,
    make_recipe,
) -> None:
    """api_spec §5.1: default `limit` is 20."""
    _user, token = make_user(username="alice_default_limit", password="hunter2pwd")
    _seed_recipes(make_recipe, token=token, count=25)

    response = api_helpers.recipes_list(api_base_url, token=token, scope="mine")
    assert response.status_code == 200, response.text
    body = response.json()
    assert_pagination_envelope(body, expect_next=True)
    assert len(body["items"]) == 20, (
        f"Default limit must be 20 per api_spec §5.1, "
        f"got {len(body['items'])}"
    )


def test_recipes_scope_mine_empty_when_user_has_no_recipes(
    api_base_url: str,
    make_user,
) -> None:
    _user, token = make_user(username="alice_empty_mine", password="hunter2pwd")

    response = api_helpers.recipes_list(api_base_url, token=token, scope="mine")
    assert response.status_code == 200, response.text
    body = response.json()
    assert_pagination_envelope(body, expect_next=False)
    assert body["items"] == [], (
        f"Empty `scope=mine` must return `items=[]`, got {body['items']!r}"
    )


def test_products_scope_mine_paginates_independently_of_recipes(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Smoke parity for `GET /products?scope=mine`.

    Mirrors the recipe walkthrough at a smaller scale (12 products, page
    size 5 → 5 + 5 + 2). Confirms the envelope, no-overlap, full-coverage
    properties hold for the products endpoint as well.
    """
    user, token = make_user(username="alice_pag_products", password="hunter2pwd")
    seeded = _seed_products(
        make_product,
        token=token,
        nutrition_fact_ids=nutrition_fact_ids,
        count=12,
    )
    seeded_ids = [p["id"] for p in seeded]

    response = api_helpers.products_list(
        api_base_url, token=token, scope="mine", limit=5
    )
    assert response.status_code == 200, response.text
    page1 = response.json()
    assert_pagination_envelope(page1, expect_next=True)
    assert len(page1["items"]) == 5

    walked = _walk_pages(api_base_url, token=token, first=page1)
    walked_ids = [item["id"] for item in walked]

    assert sorted(walked_ids) == sorted(seeded_ids), (
        f"Products paginator must yield exactly the seeded set. "
        f"Missing: {sorted(set(seeded_ids) - set(walked_ids))!r}, "
        f"Extra: {sorted(set(walked_ids) - set(seeded_ids))!r}"
    )
    assert len(walked_ids) == len(set(walked_ids)) == 12, (
        f"Products paginator must return each id exactly once, "
        f"got {walked_ids!r}"
    )
    assert walked_ids == list(reversed(seeded_ids)), (
        f"Products `scope=mine` order must be newest-first. "
        f"Walked: {walked_ids!r}"
    )

    for item in walked:
        assert item.get("created_by", {}).get("id") == user["id"]
