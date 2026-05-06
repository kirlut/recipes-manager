"""Recipe semantic-validation tests (422 cases).

Spec: `.specs/ai_gen/api_spec.md` §7.1, §7.3, §4 (Problem+JSON), §4.1
(error registry).

Covers the three 422 cases enumerated in §7.1:
  - `/errors/quantity-type-mismatch` (the case explicitly named in
    `testing_strategy.md` §5 phase 5),
  - `/errors/duplicate-recipe-product`,
  - `/errors/validation` with `violations` referencing unknown
    `product_id`.

Also covers Pydantic-level validation (400) for `amount > 0`.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_DUPLICATE_RECIPE_PRODUCT,
    ERROR_QUANTITY_TYPE_MISMATCH,
    ERROR_VALIDATION,
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
# Quantity-type-mismatch (422 + /errors/quantity-type-mismatch)
# ---------------------------------------------------------------------------


def test_recipe_with_unsupported_quantity_type_returns_422(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """testing_strategy.md §5 phase 5 quantity-type-mismatch case.

    Product P has only weight facts. Recipe references P at
    `quantity_type=volume` → 422 + `/errors/quantity-type-mismatch`
    with `extensions.product_id == P.id` and
    `extensions.requested_quantity_type == "volume"`.
    """
    _user, token = make_user(username="vee_qty_mismatch", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Weight-Only Product",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Bad Quantity Recipe",
        "products": [
            {
                "product_id": p["id"],
                "quantity_type": "volume",  # P has no volume fact rows.
                "amount": 100,
            }
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    body_out = assert_problem_json(
        response, status=422, type_uri=ERROR_QUANTITY_TYPE_MISMATCH
    )
    extensions = body_out.get("extensions") or {}
    assert extensions.get("product_id") == p["id"], (
        f"extensions.product_id must equal {p['id']!r}, "
        f"got {extensions.get('product_id')!r}"
    )
    assert extensions.get("requested_quantity_type") == "volume", (
        f"extensions.requested_quantity_type must be 'volume', "
        f"got {extensions.get('requested_quantity_type')!r}"
    )


# ---------------------------------------------------------------------------
# Duplicate recipe-product (422 + /errors/duplicate-recipe-product)
# ---------------------------------------------------------------------------


def test_recipe_with_duplicate_product_returns_422(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §7.1: 'No duplicate `product_id`.' → 422 +
    `/errors/duplicate-recipe-product`."""
    _user, token = make_user(username="vee_dup_product", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Doubled Up",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Duplicate Product Recipe",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
            {"product_id": p["id"], "quantity_type": "weight", "amount": 50},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert_problem_json(
        response, status=422, type_uri=ERROR_DUPLICATE_RECIPE_PRODUCT
    )


# ---------------------------------------------------------------------------
# Unknown product_id (422 + /errors/validation with violations)
# ---------------------------------------------------------------------------


def test_recipe_with_unknown_product_returns_validation_error(
    api_base_url: str,
    make_user,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §7.1: unknown `product_id` produces 422 + violations
    referencing the offending field path."""
    _user, token = make_user(username="vee_unknown_product", password="hunter2pwd")

    body = {
        "name": "Bogus Product Recipe",
        "products": [
            {"product_id": 999_999, "quantity_type": "weight", "amount": 100},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    body_out = assert_problem_json(
        response, status=422, type_uri=ERROR_VALIDATION
    )
    extensions = body_out.get("extensions") or {}
    violations = extensions.get("violations")
    assert isinstance(violations, list) and violations, (
        f"Expected non-empty extensions.violations, got {extensions!r}"
    )
    assert any(
        "products" in (v.get("field") or "")
        and "product_id" in (v.get("field") or "")
        for v in violations
    ), (
        f"Expected a violation referencing products.*.product_id, "
        f"got {violations!r}"
    )


# ---------------------------------------------------------------------------
# amount must be > 0 (Pydantic-level 400 + /errors/validation)
# ---------------------------------------------------------------------------


def test_recipe_with_zero_amount_returns_validation_error(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §7.1: `amount > 0`. Pydantic constraint → 400, but
    422 is also acceptable as long as type=/errors/validation."""
    _user, token = make_user(username="vee_zero_amount", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Zero-Amount Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Zero Amount Recipe",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 0},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    assert response.status_code in (400, 422), (
        f"Expected 400 or 422 for amount=0, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    assert "application/problem+json" in response.headers.get("content-type", "")
    assert response.json().get("type") == ERROR_VALIDATION, (
        f"Expected type={ERROR_VALIDATION!r}, got {response.json().get('type')!r}"
    )


def test_recipe_with_negative_amount_returns_validation_error(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    _user, token = make_user(username="vee_neg_amount", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Neg-Amount Target",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    body = {
        "name": "Negative Amount Recipe",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": -1},
        ],
    }
    response = api_helpers.recipes_create(api_base_url, token=token, body=body)

    assert response.status_code in (400, 422), (
        f"Expected 400 or 422 for amount=-1, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    assert "application/problem+json" in response.headers.get("content-type", "")
    assert response.json().get("type") == ERROR_VALIDATION


# ---------------------------------------------------------------------------
# PUT mirrors POST validation (api_spec §7.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "unsupported_quantity_type",
        "duplicate_product",
        "unknown_product",
    ],
)
def test_put_validation_mirrors_post(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
    case: str,
) -> None:
    """api_spec §7.3: PUT shares POST's validation contract."""
    _user, token = make_user(username=f"vee_put_{case}", password="hunter2pwd")
    p_weight = make_product(
        token=token,
        name="PUT Weight-Only",
        nutrition_facts=_basic_facts(nutrition_fact_ids),
    )

    create_body = {
        "name": "PUT Initial",
        "products": [
            {"product_id": p_weight["id"], "quantity_type": "weight", "amount": 50},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=create_body)
    assert created.status_code == 201, created.text
    recipe_id = created.json()["id"]

    if case == "unsupported_quantity_type":
        bad = {
            "name": "PUT Initial",
            "products": [
                {
                    "product_id": p_weight["id"],
                    "quantity_type": "volume",
                    "amount": 50,
                },
            ],
        }
        expected_type = ERROR_QUANTITY_TYPE_MISMATCH
    elif case == "duplicate_product":
        bad = {
            "name": "PUT Initial",
            "products": [
                {
                    "product_id": p_weight["id"],
                    "quantity_type": "weight",
                    "amount": 25,
                },
                {
                    "product_id": p_weight["id"],
                    "quantity_type": "weight",
                    "amount": 25,
                },
            ],
        }
        expected_type = ERROR_DUPLICATE_RECIPE_PRODUCT
    else:  # unknown_product
        bad = {
            "name": "PUT Initial",
            "products": [
                {
                    "product_id": 999_999,
                    "quantity_type": "weight",
                    "amount": 100,
                },
            ],
        }
        expected_type = ERROR_VALIDATION

    response = api_helpers.recipes_update(
        api_base_url, token=token, recipe_id=recipe_id, body=bad
    )
    assert_problem_json(response, status=422, type_uri=expected_type)
