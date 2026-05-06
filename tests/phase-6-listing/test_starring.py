"""Star/unstar integration tests.

Spec: `.specs/ai_gen/api_spec.md` §8 (starring), §6.6 / §7.6 (`scope=starred`),
§3.5 / §3.7 (`starred_by_me`). Starring is **per-user** and **idempotent**:
re-starring is a no-op (still 204), unstarring an already-unstarred resource
is also 204.

Each test creates the resource as User A and stars/unstars as User B so
the per-user nature of stars is exercised by default. Tests use `pg_conn`
to assert the absence of duplicate rows after repeated PUTs.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_NOT_FOUND,
    assert_pagination_envelope,
    assert_problem_json,
)


def _basic_facts(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 100,
        }
    ]


# ---------------------------------------------------------------------------
# Products: full star → list → detail-flag → unstar → idempotency cycle.
# ---------------------------------------------------------------------------


def test_product_star_full_lifecycle(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
    pg_conn,
) -> None:
    """End-to-end: star, see in `scope=starred`, see flag flip, unstar, repeat."""
    user_a, token_a = make_user(username="alice_owns_product", password="hunter2pwd")
    product = make_product(
        token=token_a,
        name="Starred Apple",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    user_b, token_b = make_user(username="bob_stars_product", password="hunter2pwd")

    # 1. PUT star → 204, empty body.
    star = api_helpers.products_star(
        api_base_url, token=token_b, product_id=product["id"]
    )
    assert star.status_code == 204, (
        f"PUT /products/{product['id']}/star expected 204, "
        f"got {star.status_code}: {star.text!r}"
    )
    assert star.content == b"", (
        f"PUT /star 204 must have empty body, got {star.content!r}"
    )

    # 2. GET /products?scope=starred for User B contains the product.
    listed = api_helpers.products_list(api_base_url, token=token_b, scope="starred")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert_pagination_envelope(body, expect_next=False)
    starred_ids = [item["id"] for item in body["items"]]
    assert product["id"] in starred_ids, (
        f"Bob's `scope=starred` must include product {product['id']}, "
        f"got {starred_ids!r}"
    )
    matched = next(item for item in body["items"] if item["id"] == product["id"])
    assert matched.get("starred_by_me") is True, (
        f"List item under `scope=starred` must show `starred_by_me=true`, "
        f"got {matched!r}"
    )

    # 3. GET /products/{id} for User B shows starred_by_me=true.
    detail_b = api_helpers.products_get(
        api_base_url, token=token_b, product_id=product["id"]
    )
    assert detail_b.status_code == 200, detail_b.text
    assert detail_b.json().get("starred_by_me") is True, (
        f"Detail GET for starring user must show starred_by_me=true, "
        f"got {detail_b.json()!r}"
    )

    # 4. GET /products/{id} for User A (the owner who has not starred) is false.
    detail_a = api_helpers.products_get(
        api_base_url, token=token_a, product_id=product["id"]
    )
    assert detail_a.status_code == 200, detail_a.text
    assert detail_a.json().get("starred_by_me") is False, (
        f"starred_by_me is per-user; the non-starring caller must see "
        f"false. Got {detail_a.json()!r}"
    )
    # And User A's own `scope=starred` is empty.
    starred_a = api_helpers.products_list(
        api_base_url, token=token_a, scope="starred"
    )
    assert starred_a.status_code == 200, starred_a.text
    assert starred_a.json().get("items") == [], (
        f"Owner has not starred, so their `scope=starred` must be empty. "
        f"Got {starred_a.json()!r}"
    )

    # 5. Re-PUT star → 204 (idempotent). Verify there's still only one row
    # in product_stars for (user_b, product).
    re_star = api_helpers.products_star(
        api_base_url, token=token_b, product_id=product["id"]
    )
    assert re_star.status_code == 204, (
        f"Re-PUT /star must remain 204 (idempotent), "
        f"got {re_star.status_code}: {re_star.text!r}"
    )
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM product_stars "
            "WHERE user_id = %s AND product_id = %s;",
            (user_b["id"], product["id"]),
        )
        (count,) = cur.fetchone()
    assert count == 1, (
        f"Re-starring must not insert a duplicate row in product_stars; "
        f"expected exactly 1 row for (user={user_b['id']}, "
        f"product={product['id']}), got {count}"
    )

    # 6. DELETE star → 204; detail flag flips back; scope=starred no longer contains it.
    unstar = api_helpers.products_unstar(
        api_base_url, token=token_b, product_id=product["id"]
    )
    assert unstar.status_code == 204, (
        f"DELETE /star expected 204, got {unstar.status_code}: {unstar.text!r}"
    )
    detail_after = api_helpers.products_get(
        api_base_url, token=token_b, product_id=product["id"]
    )
    assert detail_after.status_code == 200, detail_after.text
    assert detail_after.json().get("starred_by_me") is False, (
        f"After unstar, detail must show starred_by_me=false, "
        f"got {detail_after.json()!r}"
    )
    listed_after = api_helpers.products_list(
        api_base_url, token=token_b, scope="starred"
    )
    assert listed_after.status_code == 200, listed_after.text
    assert listed_after.json().get("items") == [], (
        f"After unstar, `scope=starred` must be empty, "
        f"got {listed_after.json()!r}"
    )

    # 7. Re-DELETE star → 204 (idempotent on already-unstarred).
    re_unstar = api_helpers.products_unstar(
        api_base_url, token=token_b, product_id=product["id"]
    )
    assert re_unstar.status_code == 204, (
        f"Re-DELETE /star on already-unstarred must remain 204 "
        f"(idempotent), got {re_unstar.status_code}: {re_unstar.text!r}"
    )


def test_star_unknown_product_returns_404(
    api_base_url: str,
    make_user,
) -> None:
    _user, token = make_user(username="alice_unknown_product", password="hunter2pwd")
    star = api_helpers.products_star(
        api_base_url, token=token, product_id=999_999
    )
    assert_problem_json(star, status=404, type_uri=ERROR_NOT_FOUND)

    unstar = api_helpers.products_unstar(
        api_base_url, token=token, product_id=999_999
    )
    assert_problem_json(unstar, status=404, type_uri=ERROR_NOT_FOUND)


# ---------------------------------------------------------------------------
# Recipes: symmetric coverage to the products lifecycle test.
# ---------------------------------------------------------------------------


def test_recipe_star_full_lifecycle(
    api_base_url: str,
    make_user,
    make_recipe,
    pg_conn,
) -> None:
    user_a, token_a = make_user(username="alice_owns_recipe", password="hunter2pwd")
    recipe = make_recipe(token=token_a, name="Starred Pasta")

    user_b, token_b = make_user(username="bob_stars_recipe", password="hunter2pwd")

    star = api_helpers.recipes_star(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert star.status_code == 204, (
        f"PUT /recipes/{recipe['id']}/star expected 204, "
        f"got {star.status_code}: {star.text!r}"
    )

    listed = api_helpers.recipes_list(api_base_url, token=token_b, scope="starred")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert_pagination_envelope(body, expect_next=False)
    starred_ids = [item["id"] for item in body["items"]]
    assert recipe["id"] in starred_ids, (
        f"Bob's recipe `scope=starred` must include recipe {recipe['id']}, "
        f"got {starred_ids!r}"
    )

    detail_b = api_helpers.recipes_get(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert detail_b.status_code == 200, detail_b.text
    assert detail_b.json().get("starred_by_me") is True, (
        f"Recipe detail for starring user must show starred_by_me=true, "
        f"got {detail_b.json()!r}"
    )

    detail_a = api_helpers.recipes_get(
        api_base_url, token=token_a, recipe_id=recipe["id"]
    )
    assert detail_a.status_code == 200, detail_a.text
    assert detail_a.json().get("starred_by_me") is False, (
        f"Recipe starred_by_me is per-user; owner who hasn't starred "
        f"must see false. Got {detail_a.json()!r}"
    )

    re_star = api_helpers.recipes_star(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert re_star.status_code == 204, (
        f"Re-PUT recipe /star must remain 204, "
        f"got {re_star.status_code}: {re_star.text!r}"
    )
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM recipe_stars "
            "WHERE user_id = %s AND recipe_id = %s;",
            (user_b["id"], recipe["id"]),
        )
        (count,) = cur.fetchone()
    assert count == 1, (
        f"Re-starring must not duplicate the recipe_stars row; "
        f"expected 1, got {count}"
    )

    unstar = api_helpers.recipes_unstar(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert unstar.status_code == 204, (
        f"DELETE recipe /star expected 204, "
        f"got {unstar.status_code}: {unstar.text!r}"
    )
    detail_after = api_helpers.recipes_get(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert detail_after.json().get("starred_by_me") is False
    listed_after = api_helpers.recipes_list(
        api_base_url, token=token_b, scope="starred"
    )
    assert listed_after.json().get("items") == []

    re_unstar = api_helpers.recipes_unstar(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert re_unstar.status_code == 204, (
        f"Re-DELETE recipe /star must remain 204 (idempotent), "
        f"got {re_unstar.status_code}: {re_unstar.text!r}"
    )


def test_star_unknown_recipe_returns_404(
    api_base_url: str,
    make_user,
) -> None:
    _user, token = make_user(username="alice_unknown_recipe", password="hunter2pwd")
    star = api_helpers.recipes_star(
        api_base_url, token=token, recipe_id=999_999
    )
    assert_problem_json(star, status=404, type_uri=ERROR_NOT_FOUND)

    unstar = api_helpers.recipes_unstar(
        api_base_url, token=token, recipe_id=999_999
    )
    assert_problem_json(unstar, status=404, type_uri=ERROR_NOT_FOUND)
