"""pg_trgm-based search across `/products` and `/recipes`.

Spec: `.specs/ai_gen/api_spec.md` §6.6 / §7.6 (`scope=search`),
§5.3 (cursor sort key for search mode), `db_schema.md` §5.1
(GIST trigram indexes), `system_spec.md` §3.2 ("Search covers all
recipes and products in the database, including those created by other
users"). The test compose pins `SEARCH_SIMILARITY_THRESHOLD=0.3`, so
"Beef Brisket" is excluded from a `q=chicken` search.

Tests assert on which items appear (and which do not), not on raw
similarity scores — the spec defines threshold + ordering, but pg_trgm
similarity values themselves are not part of the contract.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import api as api_helpers
from tests.helpers.asserts import assert_pagination_envelope


def _basic_facts(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 100,
        }
    ]


# ---------------------------------------------------------------------------
# Products search — the canonical scenario from testing_strategy.md §5.
# ---------------------------------------------------------------------------


def test_products_search_returns_chicken_and_excludes_beef(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Two chicken products + one beef product; `q=chicken` returns both
    chickens, excludes the beef (similarity to `chicken` is below the
    0.3 default threshold).
    """
    _user_a, token_a = make_user(username="alice_search", password="hunter2pwd")
    facts = _basic_facts(nutrition_fact_ids)

    chicken_breast = make_product(
        token=token_a, name="Chicken Breast", nutrition_facts=facts
    )
    chicken_thigh = make_product(
        token=token_a, name="Chicken Thigh", nutrition_facts=facts
    )
    beef_brisket = make_product(
        token=token_a, name="Beef Brisket", nutrition_facts=facts
    )

    # User B searches across the database.
    _user_b, token_b = make_user(username="bob_search", password="hunter2pwd")
    response = api_helpers.products_list(
        api_base_url, token=token_b, scope="search", q="chicken"
    )
    assert response.status_code == 200, (
        f"Expected 200 on search, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    body = response.json()
    assert_pagination_envelope(body, expect_next=False)
    result_ids = {item["id"] for item in body["items"]}

    assert chicken_breast["id"] in result_ids, (
        f"Chicken Breast must appear in q=chicken results, got {result_ids!r}"
    )
    assert chicken_thigh["id"] in result_ids, (
        f"Chicken Thigh must appear in q=chicken results, got {result_ids!r}"
    )
    assert beef_brisket["id"] not in result_ids, (
        f"Beef Brisket must be filtered out below the 0.3 similarity "
        f"threshold for q=chicken, got {result_ids!r}"
    )

    # api_spec §5.3: search mode sorts by `(similarity DESC, id ASC)`.
    # Both chicken names share the leading "Chicken " trigrams equally,
    # so we assert they are the two most-similar items rather than
    # locking in a relative order between the two near-ties.
    assert len(body["items"]) >= 2, (
        f"Expected at least the two Chicken products in results, "
        f"got {len(body['items'])}: {body['items']!r}"
    )
    top_two_ids = {body["items"][0]["id"], body["items"][1]["id"]}
    assert top_two_ids == {chicken_breast["id"], chicken_thigh["id"]}, (
        f"Top two results must be the two Chicken products by similarity, "
        f"got top_two_ids={top_two_ids!r}, full results={body['items']!r}"
    )


def test_products_search_no_match_returns_empty(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user_a, token_a = make_user(username="alice_search_empty", password="hunter2pwd")
    make_product(
        token=token_a,
        name="Chicken Breast",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    _user_b, token_b = make_user(username="bob_search_empty", password="hunter2pwd")
    response = api_helpers.products_list(
        api_base_url, token=token_b, scope="search", q="zzznosuchword"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert_pagination_envelope(body, expect_next=False)
    assert body["items"] == [], (
        f"Search for an unrelated term must return empty items, "
        f"got {body['items']!r}"
    )


def test_products_search_is_global_across_users(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """`system_spec.md` §3.2: search covers products created by other users."""
    user_a, token_a = make_user(username="alice_global", password="hunter2pwd")
    product_a = make_product(
        token=token_a,
        name="Quinoa Salad Mix",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    _user_b, token_b = make_user(username="bob_global", password="hunter2pwd")
    response = api_helpers.products_list(
        api_base_url, token=token_b, scope="search", q="quinoa"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    result_ids = {item["id"] for item in body["items"]}
    assert product_a["id"] in result_ids, (
        f"User B's `q=quinoa` search must surface User A's product, "
        f"got {result_ids!r}"
    )

    # The list-item shape (api_spec §6.6) includes `created_by`; verify
    # it correctly identifies the original creator, not the searcher.
    matched = next(item for item in body["items"] if item["id"] == product_a["id"])
    assert matched.get("created_by", {}).get("id") == user_a["id"], (
        f"Search results must show original `created_by`, got {matched!r}"
    )


# ---------------------------------------------------------------------------
# Recipes search — parity smoke test.
# ---------------------------------------------------------------------------


def test_recipes_search_returns_chicken_and_excludes_beef(
    api_base_url: str,
    make_user,
    make_recipe,
) -> None:
    """Symmetric to the products test, against `GET /recipes?scope=search`.

    Recipes use the same `pg_trgm` GIST index on `name` per
    `db_schema.md` §5.1, so the threshold gate must behave identically.
    """
    _user_a, token_a = make_user(username="alice_recipes_search", password="hunter2pwd")
    chicken_bowl = make_recipe(token=token_a, name="Chicken Bowl")
    chicken_soup = make_recipe(token=token_a, name="Chicken Soup")
    beef_stew = make_recipe(token=token_a, name="Beef Stew")

    _user_b, token_b = make_user(username="bob_recipes_search", password="hunter2pwd")
    response = api_helpers.recipes_list(
        api_base_url, token=token_b, scope="search", q="chicken"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert_pagination_envelope(body, expect_next=False)
    result_ids = {item["id"] for item in body["items"]}

    assert chicken_bowl["id"] in result_ids, (
        f"Chicken Bowl must appear in q=chicken recipe search, "
        f"got {result_ids!r}"
    )
    assert chicken_soup["id"] in result_ids, (
        f"Chicken Soup must appear in q=chicken recipe search, "
        f"got {result_ids!r}"
    )
    assert beef_stew["id"] not in result_ids, (
        f"Beef Stew must be filtered out below 0.3 threshold, "
        f"got {result_ids!r}"
    )
