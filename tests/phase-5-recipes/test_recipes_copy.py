"""Recipe copy integration tests.

Spec: `.specs/ai_gen/api_spec.md` §7.5 — `POST /recipes/{id}/copy`.
Mirrors product-copy semantics (§6.5): any authenticated user can copy
any recipe; the copy is owned by the caller, references the same
`image_filename` (no file duplication), preserves `name` /
`description` and the embedded `recipe_products`, and is **not**
auto-starred. Totals recompute identically.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_NOT_FOUND,
    ERROR_UNAUTHORIZED,
    assert_problem_json,
)


def _products_set(products: list[dict[str, Any]]) -> set[tuple[int, str, float]]:
    return {
        (p["product_id"], p["quantity_type"], float(p["amount"]))
        for p in products
    }


def _totals_by_name(
    totals: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {t["nutrition_fact_name"]: t for t in totals}


def _basic_facts(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 200,
        },
        {
            "nutrition_fact_id": nutrition_fact_ids["Protein"],
            "quantity_type": "weight",
            "amount": 25,
        },
    ]


def _make_source_recipe(
    api_base_url: str,
    token: str,
    *,
    products: list[dict[str, Any]],
    name: str = "Source Recipe",
    description: str | None = "Original.",
    image_filename: str | None = "shared-recipe.jpg",
) -> dict:
    body = {
        "name": name,
        "description": description,
        "image_filename": image_filename,
        "products": products,
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_copy_other_users_recipe(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    user_a, token_a = make_user(username="alice_recipe_copy_src", password="hunter2pwd")
    user_b, token_b = make_user(username="bob_recipe_copy_caller", password="hunter2pwd")

    p1 = make_product(
        token=token_a,
        name="Copy Product 1",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    p2 = make_product(
        token=token_a,
        name="Copy Product 2",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    source = _make_source_recipe(
        api_base_url,
        token_a,
        products=[
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 150},
            {"product_id": p2["id"], "quantity_type": "weight", "amount": 50},
        ],
    )

    response = api_helpers.recipes_copy(
        api_base_url, token=token_b, recipe_id=source["id"]
    )
    assert response.status_code == 201, (
        f"Expected 201 on copy, got {response.status_code}. Body: {response.text!r}"
    )
    copy = response.json()

    # Identity / ownership
    assert isinstance(copy.get("id"), int) and copy["id"] != source["id"], (
        f"Copy must have a fresh id (not equal to source.id={source['id']}); "
        f"got {copy.get('id')!r}"
    )
    assert copy.get("created_by", {}).get("id") == user_b["id"], (
        f"Copy.created_by must be the caller; expected user_b id={user_b['id']}, "
        f"got {copy.get('created_by')!r}"
    )
    assert copy.get("import_source") is None, (
        f"Copy.import_source must be null, got {copy.get('import_source')!r}"
    )
    assert copy.get("starred_by_me") is False, (
        f"Copy must not be auto-starred, got {copy.get('starred_by_me')!r}"
    )

    # Field-level fidelity
    assert copy.get("name") == source["name"]
    assert copy.get("description") == source["description"]
    assert copy.get("image_filename") == source["image_filename"], (
        f"Copy.image_filename must match source (no file duplication); "
        f"expected {source['image_filename']!r}, got {copy.get('image_filename')!r}"
    )

    # recipe_products fidelity
    assert _products_set(copy["products"]) == _products_set(source["products"]), (
        f"Copy products must match source: source={source['products']!r}, "
        f"copy={copy['products']!r}"
    )

    # Totals must recompute to the same values.
    src_totals = _totals_by_name(source["nutrition_totals_per_serving"])
    copy_totals = _totals_by_name(copy["nutrition_totals_per_serving"])
    assert set(src_totals.keys()) == set(copy_totals.keys()), (
        f"Copy totals key set must match source: "
        f"source={sorted(src_totals)!r}, copy={sorted(copy_totals)!r}"
    )
    for name, src_entry in src_totals.items():
        assert float(copy_totals[name]["amount"]) == pytest.approx(
            float(src_entry["amount"])
        ), (
            f"Copy total mismatch for {name!r}: "
            f"source={src_entry!r}, copy={copy_totals[name]!r}"
        )

    # Location header
    location = response.headers.get("location")
    assert location == f"/recipes/{copy['id']}", (
        f"Expected Location: /recipes/{copy['id']!r}, got {location!r}"
    )

    # Source unchanged: same owner, same products, same totals.
    after_source = api_helpers.recipes_get(
        api_base_url, token=token_a, recipe_id=source["id"]
    )
    assert after_source.status_code == 200, after_source.text
    after_body = after_source.json()
    assert after_body["created_by"]["id"] == user_a["id"], (
        f"Source ownership must be unchanged after copy; "
        f"got {after_body['created_by']!r}"
    )
    assert _products_set(after_body["products"]) == _products_set(source["products"])


def test_copy_own_recipe_creates_duplicate(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §7.5 mirrors §6.5: 'Any user can copy any recipe' — including their own."""
    user_a, token_a = make_user(username="alice_self_copy_recipe", password="hunter2pwd")
    p = make_product(
        token=token_a,
        name="Self-Copy Source",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    source = _make_source_recipe(
        api_base_url,
        token_a,
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    )
    response = api_helpers.recipes_copy(
        api_base_url, token=token_a, recipe_id=source["id"]
    )
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != source["id"], (
        f"Self-copy must produce a new id; got {copy['id']} == source {source['id']}"
    )
    assert copy["created_by"]["id"] == user_a["id"]
    assert _products_set(copy["products"]) == _products_set(source["products"])

    # Totals recompute identically for a self-copy.
    src_totals = _totals_by_name(source["nutrition_totals_per_serving"])
    copy_totals = _totals_by_name(copy["nutrition_totals_per_serving"])
    for name, src_entry in src_totals.items():
        assert float(copy_totals[name]["amount"]) == pytest.approx(
            float(src_entry["amount"])
        )


def test_copy_unknown_recipe_returns_404(
    api_base_url: str, make_user
) -> None:
    _user, token = make_user(username="bob_recipe_copy_404", password="hunter2pwd")

    response = api_helpers.recipes_copy(
        api_base_url, token=token, recipe_id=999_999
    )
    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)


def test_copy_without_auth_returns_401(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="alice_recipe_copy_anon_src", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Anon Copy Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    source = _make_source_recipe(
        api_base_url,
        token,
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    )

    response = api_helpers.recipes_copy(
        api_base_url, token=None, recipe_id=source["id"]
    )
    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)
