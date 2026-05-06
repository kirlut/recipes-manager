"""Recipe CRUD integration tests.

Spec: `.specs/ai_gen/api_spec.md` §3.6, §3.7, §7.1, §7.2, §7.3, §7.4.
Covers the happy-path lifecycle: create, read, full-replace, delete.
Validation, totals, authz, and copy semantics live in their own files.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    JSON_MEDIA_TYPE,
    ERROR_NOT_FOUND,
    assert_iso_8601_z,
    assert_problem_json,
)


def _products_set(products: list[dict[str, Any]]) -> set[tuple[int, str, float]]:
    """Comparable set of `(product_id, quantity_type, amount)`."""
    return {
        (p["product_id"], p["quantity_type"], float(p["amount"]))
        for p in products
    }


def _assert_recipe_shape(
    recipe: dict[str, Any],
    *,
    expected_owner: dict,
    expected_name: str,
    expected_description: str | None,
    expected_image: str | None,
    expected_products: set[tuple[int, str, float]],
    products_by_id: dict[int, dict[str, Any]],
) -> None:
    """Validate the full Recipe representation per api_spec §3.7."""
    assert isinstance(recipe.get("id"), int) and recipe["id"] > 0, (
        f"Recipe.id must be a positive integer, got {recipe.get('id')!r}"
    )
    assert recipe.get("name") == expected_name, (
        f"Recipe.name mismatch: expected {expected_name!r}, "
        f"got {recipe.get('name')!r}"
    )
    assert recipe.get("description") == expected_description, (
        f"Recipe.description mismatch: expected {expected_description!r}, "
        f"got {recipe.get('description')!r}"
    )
    assert recipe.get("image_filename") == expected_image, (
        f"Recipe.image_filename mismatch: expected {expected_image!r}, "
        f"got {recipe.get('image_filename')!r}"
    )

    created_by = recipe.get("created_by")
    assert isinstance(created_by, dict), (
        f"Recipe.created_by must be a UserRef object, got {created_by!r}"
    )
    assert created_by.get("id") == expected_owner["id"], (
        f"Recipe.created_by.id mismatch: expected {expected_owner['id']!r}, "
        f"got {created_by.get('id')!r}"
    )
    assert created_by.get("username") == expected_owner["username"], (
        f"Recipe.created_by.username mismatch: "
        f"expected {expected_owner['username']!r}, "
        f"got {created_by.get('username')!r}"
    )

    assert recipe.get("import_source") is None, (
        f"User-created Recipe.import_source must be null, "
        f"got {recipe.get('import_source')!r}"
    )

    assert_iso_8601_z(recipe.get("created_at"), field="Recipe.created_at")

    assert recipe.get("starred_by_me") is False, (
        f"Phase-5 starred_by_me must be present and false, "
        f"got {recipe.get('starred_by_me')!r}"
    )

    products = recipe.get("products")
    assert isinstance(products, list), (
        f"Recipe.products must be an array, got {type(products)!r}"
    )
    assert _products_set(products) == expected_products, (
        f"Recipe.products mismatch: "
        f"expected {sorted(expected_products)!r}, "
        f"got {sorted(_products_set(products))!r}"
    )

    # Denormalised name + image_filename per api_spec §3.6.
    for rp in products:
        pid = rp["product_id"]
        source = products_by_id.get(pid)
        assert source is not None, (
            f"Recipe.products contains unexpected product_id={pid!r}; "
            f"known ids: {sorted(products_by_id)!r}"
        )
        assert rp.get("product_name") == source["name"], (
            f"recipe-product.product_name mismatch for product_id={pid}: "
            f"expected {source['name']!r}, got {rp.get('product_name')!r}"
        )
        assert rp.get("product_image_filename") == source["image_filename"], (
            f"recipe-product.product_image_filename mismatch for "
            f"product_id={pid}: expected {source['image_filename']!r}, "
            f"got {rp.get('product_image_filename')!r}"
        )

    totals = recipe.get("nutrition_totals_per_serving")
    assert isinstance(totals, list), (
        f"Recipe.nutrition_totals_per_serving must be an array, "
        f"got {type(totals)!r}"
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
# POST /recipes
# ---------------------------------------------------------------------------


def test_create_recipe_returns_201_with_full_shape(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    user, token = make_user(username="alice_recipe_crud", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Chicken Breast",
        image_filename="chicken-uuid.jpg",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 165,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 31,
            },
        ],
    )
    p2 = make_product(
        token=token,
        name="Brown Rice",
        image_filename=None,
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 130,
            }
        ],
    )

    body = {
        "name": "Grilled Chicken Bowl",
        "description": "Quick weekday dinner.",
        "image_filename": "bowl-uuid.png",
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 200},
            {"product_id": p2["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}. Body: {response.text!r}"
    )
    assert JSON_MEDIA_TYPE in response.headers.get("content-type", "")

    recipe = response.json()
    expected_products = {
        (p1["id"], "weight", 200.0),
        (p2["id"], "weight", 100.0),
    }
    _assert_recipe_shape(
        recipe,
        expected_owner=user,
        expected_name="Grilled Chicken Bowl",
        expected_description="Quick weekday dinner.",
        expected_image="bowl-uuid.png",
        expected_products=expected_products,
        products_by_id={p1["id"]: p1, p2["id"]: p2},
    )

    location = response.headers.get("location")
    assert location == f"/recipes/{recipe['id']}", (
        f"Expected Location: /recipes/{recipe['id']!r}, got {location!r}"
    )


def test_create_recipe_with_no_products(
    api_base_url: str, make_user
) -> None:
    """api_spec §7.1: products may be empty; totals are then [] (api_spec §13)."""
    user, token = make_user(username="alice_empty_recipe", password="hunter2pwd")

    body = {
        "name": "Empty Plate",
        "description": None,
        "image_filename": None,
        "products": [],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, (
        f"Expected 201 for empty products, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    recipe = response.json()
    _assert_recipe_shape(
        recipe,
        expected_owner=user,
        expected_name="Empty Plate",
        expected_description=None,
        expected_image=None,
        expected_products=set(),
        products_by_id={},
    )
    assert recipe.get("nutrition_totals_per_serving") == [], (
        f"Empty recipe must have empty totals, got "
        f"{recipe.get('nutrition_totals_per_serving')!r}"
    )


def test_create_recipe_with_null_image_and_description(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    user, token = make_user(username="alice_null_fields", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Apple",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Null-Fields Recipe",
        "description": None,
        "image_filename": None,
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 50},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, response.text
    recipe = response.json()
    assert recipe.get("description") is None
    assert recipe.get("image_filename") is None


def test_create_recipe_omitting_optional_fields(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §7.1: `description` and `image_filename` are not required."""
    _user, token = make_user(username="alice_omit_fields", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Banana",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Omitted Fields Recipe",
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 75},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, response.text
    recipe = response.json()
    assert recipe.get("description") is None
    assert recipe.get("image_filename") is None


# ---------------------------------------------------------------------------
# GET /recipes/{id}
# ---------------------------------------------------------------------------


def test_get_recipe_returns_full_shape(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    user, token = make_user(username="alice_get_recipe", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Tomato",
        image_filename="tomato.jpg",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 18,
            }
        ],
    )

    create_body = {
        "name": "Tomato Salad",
        "description": "Just tomatoes.",
        "image_filename": "salad.jpg",
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 150},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=create_body)
    assert created.status_code == 201, created.text
    recipe_id = created.json()["id"]

    response = api_helpers.recipes_get(
        api_base_url, token=token, recipe_id=recipe_id
    )
    assert response.status_code == 200, (
        f"Expected 200 on GET, got {response.status_code}. Body: {response.text!r}"
    )
    _assert_recipe_shape(
        response.json(),
        expected_owner=user,
        expected_name="Tomato Salad",
        expected_description="Just tomatoes.",
        expected_image="salad.jpg",
        expected_products={(p1["id"], "weight", 150.0)},
        products_by_id={p1["id"]: p1},
    )


def test_get_unknown_recipe_returns_404(api_base_url: str, make_user) -> None:
    _user, token = make_user(username="alice_recipe_404", password="hunter2pwd")

    response = api_helpers.recipes_get(
        api_base_url, token=token, recipe_id=999_999
    )
    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)


# ---------------------------------------------------------------------------
# PUT /recipes/{id}
# ---------------------------------------------------------------------------


def test_put_recipe_replaces_products_fully(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
    pg_conn,
) -> None:
    """PUT is a full replacement: products not in the request must be removed.

    api_spec §7.3: body shape identical to POST; replacement is total.
    """
    user, token = make_user(username="alice_put_recipe", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Onion",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    p2 = make_product(
        token=token,
        name="Garlic",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )
    p3 = make_product(
        token=token,
        name="Carrot",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    create_body = {
        "name": "Aromatics Mix",
        "description": "v1",
        "image_filename": None,
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 50},
            {"product_id": p2["id"], "quantity_type": "weight", "amount": 10},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=create_body)
    assert created.status_code == 201, created.text
    recipe_id = created.json()["id"]

    update_body = {
        "name": "Carrot Solo",
        "description": "v2",
        "image_filename": "carrot.jpg",
        "products": [
            {"product_id": p3["id"], "quantity_type": "weight", "amount": 200},
        ],
    }
    response = api_helpers.recipes_update(
        api_base_url, token=token, recipe_id=recipe_id, body=update_body
    )
    assert response.status_code == 200, (
        f"Expected 200 on PUT, got {response.status_code}. Body: {response.text!r}"
    )
    expected_products = {(p3["id"], "weight", 200.0)}
    _assert_recipe_shape(
        response.json(),
        expected_owner=user,
        expected_name="Carrot Solo",
        expected_description="v2",
        expected_image="carrot.jpg",
        expected_products=expected_products,
        products_by_id={p3["id"]: p3},
    )

    # Direct DB check: prior `recipe_products` rows for p1/p2 are gone.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT product_id, quantity_type, amount "
            "FROM recipe_products WHERE recipe_id = %s "
            "ORDER BY product_id;",
            (recipe_id,),
        )
        rows = cur.fetchall()
    db_products = {(r[0], r[1], float(r[2])) for r in rows}
    assert db_products == expected_products, (
        f"DB recipe_products after PUT mismatch: "
        f"expected {sorted(expected_products)!r}, got {sorted(db_products)!r}"
    )


def test_put_unknown_recipe_returns_404(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="alice_put_recipe_404", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Phantom",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Ghost Recipe",
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    response = api_helpers.recipes_update(
        api_base_url, token=token, recipe_id=999_999, body=body
    )
    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)


# ---------------------------------------------------------------------------
# DELETE /recipes/{id}
# ---------------------------------------------------------------------------


def test_delete_recipe_returns_204_then_404_on_reread(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="alice_del_recipe", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Disposable",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    create_body = {
        "name": "Disposable Recipe",
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=create_body)
    assert created.status_code == 201, created.text
    recipe_id = created.json()["id"]

    response = api_helpers.recipes_delete(
        api_base_url, token=token, recipe_id=recipe_id
    )
    assert response.status_code == 204, (
        f"Expected 204 on DELETE, got {response.status_code}. Body: {response.text!r}"
    )
    assert response.content == b"", (
        f"DELETE 204 must have empty body, got {response.content!r}"
    )

    follow_up = api_helpers.recipes_get(
        api_base_url, token=token, recipe_id=recipe_id
    )
    assert_problem_json(follow_up, status=404, type_uri=ERROR_NOT_FOUND)


def test_delete_already_deleted_recipe_returns_404(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §7.4: 204 then 404 on the second DELETE (matches §6.4 semantics)."""
    _user, token = make_user(username="alice_del_recipe_twice", password="hunter2pwd")
    p1 = make_product(
        token=token,
        name="Once",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    create_body = {
        "name": "Once Only",
        "products": [
            {"product_id": p1["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=create_body)
    assert created.status_code == 201, created.text
    recipe_id = created.json()["id"]

    first = api_helpers.recipes_delete(
        api_base_url, token=token, recipe_id=recipe_id
    )
    assert first.status_code == 204, first.text

    second = api_helpers.recipes_delete(
        api_base_url, token=token, recipe_id=recipe_id
    )
    assert_problem_json(second, status=404, type_uri=ERROR_NOT_FOUND)


def test_delete_unknown_recipe_returns_404(api_base_url: str, make_user) -> None:
    _user, token = make_user(username="alice_del_recipe_404", password="hunter2pwd")

    response = api_helpers.recipes_delete(
        api_base_url, token=token, recipe_id=999_999
    )
    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)
