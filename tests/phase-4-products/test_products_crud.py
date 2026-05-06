"""Product CRUD integration tests.

Spec: `.specs/ai_gen/api_spec.md` §3.4, §3.5, §6.1, §6.2, §6.3, §6.4.
Covers the happy-path lifecycle: create, read, full-replace, delete.
Validation, authz, and copy semantics live in their own files.
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


def _facts_set(nutrition_facts: list[dict[str, Any]]) -> set[tuple[int, str, float]]:
    """Comparable set of `(nutrition_fact_id, quantity_type, amount)`."""
    return {
        (f["nutrition_fact_id"], f["quantity_type"], float(f["amount"]))
        for f in nutrition_facts
    }


def _assert_product_shape(
    product: dict[str, Any],
    *,
    expected_owner: dict,
    expected_name: str,
    expected_image: str | None,
    expected_facts: set[tuple[int, str, float]],
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Validate the full Product representation per api_spec §3.5."""
    assert isinstance(product.get("id"), int) and product["id"] > 0, (
        f"Product.id must be a positive integer, got {product.get('id')!r}"
    )
    assert product.get("name") == expected_name, (
        f"Product.name mismatch: expected {expected_name!r}, "
        f"got {product.get('name')!r}"
    )
    assert product.get("image_filename") == expected_image, (
        f"Product.image_filename mismatch: expected {expected_image!r}, "
        f"got {product.get('image_filename')!r}"
    )

    created_by = product.get("created_by")
    assert isinstance(created_by, dict), (
        f"Product.created_by must be a UserRef object, got {created_by!r}"
    )
    assert created_by.get("id") == expected_owner["id"], (
        f"Product.created_by.id mismatch: expected {expected_owner['id']!r}, "
        f"got {created_by.get('id')!r}"
    )
    assert created_by.get("username") == expected_owner["username"], (
        f"Product.created_by.username mismatch: "
        f"expected {expected_owner['username']!r}, "
        f"got {created_by.get('username')!r}"
    )

    assert product.get("import_source") is None, (
        f"User-created Product.import_source must be null, "
        f"got {product.get('import_source')!r}"
    )

    assert_iso_8601_z(product.get("created_at"), field="Product.created_at")

    assert product.get("starred_by_me") is False, (
        f"Phase-4 starred_by_me must be present and false, "
        f"got {product.get('starred_by_me')!r}"
    )

    facts = product.get("nutrition_facts")
    assert isinstance(facts, list), (
        f"Product.nutrition_facts must be an array, got {type(facts)!r}"
    )
    assert _facts_set(facts) == expected_facts, (
        f"Product.nutrition_facts mismatch: "
        f"expected {sorted(expected_facts)!r}, "
        f"got {sorted(_facts_set(facts))!r}"
    )

    # Denormalised name + unit on each fact, per api_spec §3.4.
    id_to_name = {v: k for k, v in nutrition_fact_ids.items()}
    for fact in facts:
        nf_id = fact["nutrition_fact_id"]
        expected_nf_name = id_to_name.get(nf_id)
        assert fact.get("nutrition_fact_name") == expected_nf_name, (
            f"fact.nutrition_fact_name mismatch for id={nf_id}: "
            f"expected {expected_nf_name!r}, got {fact.get('nutrition_fact_name')!r}"
        )
        assert isinstance(fact.get("unit"), str) and fact["unit"], (
            f"fact.unit must be a non-empty string, got {fact.get('unit')!r}"
        )


# ---------------------------------------------------------------------------
# POST /products
# ---------------------------------------------------------------------------


def test_create_product_returns_201_with_full_shape(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    user, token = make_user(username="alice_crud", password="hunter2pwd")

    body = {
        "name": "Chicken Breast",
        "image_filename": "a3f1b2c4-1234-5678-9abc-def012345678.jpg",
        "nutrition_facts": [
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
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}. Body: {response.text!r}"
    )
    assert JSON_MEDIA_TYPE in response.headers.get("content-type", "")

    product = response.json()
    expected_facts = {
        (nutrition_fact_ids["Energy"], "weight", 165.0),
        (nutrition_fact_ids["Protein"], "weight", 31.0),
    }
    _assert_product_shape(
        product,
        expected_owner=user,
        expected_name="Chicken Breast",
        expected_image="a3f1b2c4-1234-5678-9abc-def012345678.jpg",
        expected_facts=expected_facts,
        nutrition_fact_ids=nutrition_fact_ids,
    )

    # api_spec §6.1: Location header set to the new resource. Backend
    # routes are unprefixed (nginx adds the `/api` prefix in production),
    # so the header value is `/products/{id}`.
    location = response.headers.get("location")
    assert location == f"/products/{product['id']}", (
        f"Expected Location: /products/{product['id']!r}, got {location!r}"
    )


def test_create_product_with_null_image_filename(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """api_spec §3.5: image_filename may be null."""
    user, token = make_user(username="alice_no_img", password="hunter2pwd")

    body = {
        "name": "Plain Apple",
        "image_filename": None,
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 52,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}. Body: {response.text!r}"
    )
    assert response.json().get("image_filename") is None


def test_create_product_image_filename_omitted(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """Omitting `image_filename` is equivalent to sending null (api_spec §6.1: not required)."""
    _user, token = make_user(username="alice_omit_img", password="hunter2pwd")

    body = {
        "name": "Plain Banana",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 89,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}. Body: {response.text!r}"
    )
    assert response.json().get("image_filename") is None


# ---------------------------------------------------------------------------
# GET /products/{id}
# ---------------------------------------------------------------------------


def test_get_product_returns_full_shape(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    user, token = make_user(username="alice_get", password="hunter2pwd")

    create_body = {
        "name": "Brown Rice",
        "image_filename": None,
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 130,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Net Carbs"],
                "quantity_type": "weight",
                "amount": 28,
            },
        ],
    }
    created = api_helpers.products_create(
        api_base_url, token=token, body=create_body
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]

    response = api_helpers.products_get(
        api_base_url, token=token, product_id=product_id
    )

    assert response.status_code == 200, (
        f"Expected 200 on GET, got {response.status_code}. Body: {response.text!r}"
    )
    expected_facts = {
        (nutrition_fact_ids["Energy"], "weight", 130.0),
        (nutrition_fact_ids["Net Carbs"], "weight", 28.0),
    }
    _assert_product_shape(
        response.json(),
        expected_owner=user,
        expected_name="Brown Rice",
        expected_image=None,
        expected_facts=expected_facts,
        nutrition_fact_ids=nutrition_fact_ids,
    )


def test_get_unknown_product_returns_404(api_base_url: str, make_user) -> None:
    _user, token = make_user(username="alice_404", password="hunter2pwd")

    response = api_helpers.products_get(
        api_base_url, token=token, product_id=999_999
    )

    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)


# ---------------------------------------------------------------------------
# PUT /products/{id}
# ---------------------------------------------------------------------------


def test_put_product_replaces_facts_fully(
    api_base_url: str,
    make_user,
    nutrition_fact_ids: dict[str, int],
    pg_conn,
) -> None:
    """PUT is a full replacement: facts not in the request must be removed.

    api_spec §6.3: "The replacement is full — nutrition facts not present
    in the request are removed, present ones upserted."
    """
    user, token = make_user(username="alice_put", password="hunter2pwd")

    create_body = {
        "name": "Yogurt Original",
        "image_filename": None,
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 60,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 4,
            },
        ],
    }
    created = api_helpers.products_create(
        api_base_url, token=token, body=create_body
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]

    update_body = {
        "name": "Yogurt Updated",
        "image_filename": "renamed-uuid.png",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "volume",
                "amount": 65,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Fat"],
                "quantity_type": "volume",
                "amount": 3.5,
            },
        ],
    }
    response = api_helpers.products_update(
        api_base_url, token=token, product_id=product_id, body=update_body
    )

    assert response.status_code == 200, (
        f"Expected 200 on PUT, got {response.status_code}. Body: {response.text!r}"
    )
    expected_facts = {
        (nutrition_fact_ids["Energy"], "volume", 65.0),
        (nutrition_fact_ids["Fat"], "volume", 3.5),
    }
    _assert_product_shape(
        response.json(),
        expected_owner=user,
        expected_name="Yogurt Updated",
        expected_image="renamed-uuid.png",
        expected_facts=expected_facts,
        nutrition_fact_ids=nutrition_fact_ids,
    )

    # Direct DB check: prior `(Energy, weight)` and `(Protein, weight)` rows
    # are gone — the replacement is total at the DB layer too.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT nutrition_fact_id, quantity_type, amount "
            "FROM product_nutrition_facts WHERE product_id = %s "
            "ORDER BY nutrition_fact_id, quantity_type;",
            (product_id,),
        )
        rows = cur.fetchall()
    db_facts = {(r[0], r[1], float(r[2])) for r in rows}
    assert db_facts == expected_facts, (
        f"DB facts after PUT mismatch: expected {sorted(expected_facts)!r}, "
        f"got {sorted(db_facts)!r}"
    )


def test_put_unknown_product_returns_404(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="alice_put_404", password="hunter2pwd")

    body = {
        "name": "Ghost",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    }
    response = api_helpers.products_update(
        api_base_url, token=token, product_id=999_999, body=body
    )

    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)


# ---------------------------------------------------------------------------
# DELETE /products/{id}
# ---------------------------------------------------------------------------


def test_delete_product_returns_204_then_404_on_reread(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="alice_del", password="hunter2pwd")

    create_body = {
        "name": "Disposable",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    }
    created = api_helpers.products_create(
        api_base_url, token=token, body=create_body
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]

    response = api_helpers.products_delete(
        api_base_url, token=token, product_id=product_id
    )

    assert response.status_code == 204, (
        f"Expected 204 on DELETE, got {response.status_code}. Body: {response.text!r}"
    )
    assert response.content == b"", (
        f"DELETE 204 must have empty body, got {response.content!r}"
    )

    follow_up = api_helpers.products_get(
        api_base_url, token=token, product_id=product_id
    )
    assert_problem_json(follow_up, status=404, type_uri=ERROR_NOT_FOUND)


def test_delete_already_deleted_returns_404(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """DELETE is not idempotent for products: api_spec §6.4 says 204 then 404."""
    _user, token = make_user(username="alice_del_twice", password="hunter2pwd")

    create_body = {
        "name": "Once",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    }
    created = api_helpers.products_create(
        api_base_url, token=token, body=create_body
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]

    first = api_helpers.products_delete(
        api_base_url, token=token, product_id=product_id
    )
    assert first.status_code == 204, first.text

    second = api_helpers.products_delete(
        api_base_url, token=token, product_id=product_id
    )
    assert_problem_json(second, status=404, type_uri=ERROR_NOT_FOUND)


def test_delete_unknown_product_returns_404(api_base_url: str, make_user) -> None:
    _user, token = make_user(username="alice_del_404", password="hunter2pwd")

    response = api_helpers.products_delete(
        api_base_url, token=token, product_id=999_999
    )

    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)
