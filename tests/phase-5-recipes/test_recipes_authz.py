"""Recipe authorization integration tests.

Spec: `.specs/ai_gen/api_spec.md` §1.5 (auth required), §7 (read open
to any authenticated user; PUT/DELETE owner-only), §15 (authorization
summary). Mirrors `tests/phase-4-products/test_products_authz.py`.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_FORBIDDEN_NOT_OWNER,
    ERROR_UNAUTHORIZED,
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


def _make_recipe(
    api_base_url: str,
    token: str,
    *,
    product_id: int,
    name: str = "Owner's Recipe",
    description: str | None = "Owner-only edits.",
) -> dict:
    body = {
        "name": name,
        "description": description,
        "image_filename": "owner-recipe.jpg",
        "products": [
            {"product_id": product_id, "quantity_type": "weight", "amount": 100},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Unauthenticated requests
# ---------------------------------------------------------------------------


def test_create_without_token_returns_401(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="authz_create_owner_recipe", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Anon Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Anon Recipe Attempt",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=None, body=body)
    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_get_without_token_returns_401(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="authz_get_recipe_owner", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Anon Read Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    recipe = _make_recipe(api_base_url, token, product_id=p["id"])

    response = api_helpers.recipes_get(
        api_base_url, token=None, recipe_id=recipe["id"]
    )
    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_update_without_token_returns_401(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="authz_put_recipe_owner", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Anon Edit Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    recipe = _make_recipe(api_base_url, token, product_id=p["id"])

    body = {
        "name": "Anon Edit",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 50},
        ],
    }
    response = api_helpers.recipes_update(
        api_base_url, token=None, recipe_id=recipe["id"], body=body
    )
    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_delete_without_token_returns_401(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="authz_del_recipe_owner", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Anon Delete Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    recipe = _make_recipe(api_base_url, token, product_id=p["id"])

    response = api_helpers.recipes_delete(
        api_base_url, token=None, recipe_id=recipe["id"]
    )
    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Cross-user access: read open, mutate forbidden
# ---------------------------------------------------------------------------


def test_other_user_can_read_recipe(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §15: GET is open to any authenticated user."""
    user_a, token_a = make_user(username="alice_recipe_authz", password="hunter2pwd")
    _user_b, token_b = make_user(username="bob_recipe_authz", password="hunter2pwd")

    p = make_product(
        token=token_a,
        name="Read-Open Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    recipe = _make_recipe(api_base_url, token_a, product_id=p["id"])

    response = api_helpers.recipes_get(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert response.status_code == 200, (
        f"Expected 200 on cross-user GET, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    body = response.json()
    assert body.get("created_by", {}).get("id") == user_a["id"], (
        f"Cross-user GET should still surface the original owner; "
        f"body.created_by={body.get('created_by')!r}"
    )
    assert body.get("starred_by_me") is False, (
        f"User B has not starred Alice's recipe, expected starred_by_me=False, "
        f"got {body.get('starred_by_me')!r}"
    )


def test_other_user_put_returns_403_and_data_unchanged(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    user_a, token_a = make_user(username="alice_put_recipe_owner", password="hunter2pwd")
    _user_b, token_b = make_user(username="bob_put_recipe_attacker", password="hunter2pwd")

    p_a = make_product(
        token=token_a,
        name="Alice's Product",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    p_b = make_product(
        token=token_b,
        name="Bob's Product",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    recipe = _make_recipe(api_base_url, token_a, product_id=p_a["id"])

    update_body = {
        "name": "Bob Hijack",
        "description": "Pwned",
        "image_filename": "bob-pwn.png",
        "products": [
            {"product_id": p_b["id"], "quantity_type": "weight", "amount": 1},
        ],
    }
    response = api_helpers.recipes_update(
        api_base_url, token=token_b, recipe_id=recipe["id"], body=update_body
    )
    assert_problem_json(
        response, status=403, type_uri=ERROR_FORBIDDEN_NOT_OWNER
    )

    # Re-read as the owner — data must be exactly as Alice left it.
    after = api_helpers.recipes_get(
        api_base_url, token=token_a, recipe_id=recipe["id"]
    )
    assert after.status_code == 200, after.text
    after_body = after.json()
    assert after_body["name"] == recipe["name"], (
        f"403 PUT must not have mutated name; was {recipe['name']!r}, "
        f"got {after_body['name']!r}"
    )
    assert after_body["description"] == recipe["description"], (
        f"403 PUT must not have mutated description; was {recipe['description']!r}, "
        f"got {after_body['description']!r}"
    )
    assert after_body["image_filename"] == recipe["image_filename"], (
        f"403 PUT must not have mutated image_filename; "
        f"was {recipe['image_filename']!r}, got {after_body['image_filename']!r}"
    )
    assert after_body["created_by"]["id"] == user_a["id"]
    after_products = {(rp["product_id"], rp["quantity_type"], float(rp["amount"]))
                      for rp in after_body["products"]}
    assert after_products == {(p_a["id"], "weight", 100.0)}, (
        f"403 PUT must not have mutated recipe_products; got {after_products!r}"
    )


def test_other_user_delete_returns_403_and_recipe_remains(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user_a, token_a = make_user(username="alice_del_recipe_owner", password="hunter2pwd")
    _user_b, token_b = make_user(username="bob_del_recipe_attacker", password="hunter2pwd")

    p = make_product(
        token=token_a,
        name="Alice's Survivor",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    recipe = _make_recipe(api_base_url, token_a, product_id=p["id"])

    response = api_helpers.recipes_delete(
        api_base_url, token=token_b, recipe_id=recipe["id"]
    )
    assert_problem_json(
        response, status=403, type_uri=ERROR_FORBIDDEN_NOT_OWNER
    )

    after = api_helpers.recipes_get(
        api_base_url, token=token_a, recipe_id=recipe["id"]
    )
    assert after.status_code == 200, (
        f"Recipe must still exist after a forbidden DELETE attempt; "
        f"GET returned {after.status_code} {after.text!r}"
    )
