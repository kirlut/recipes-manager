"""Shopping-list request-shape and semantic validation tests.

Spec: `.specs/ai_gen/api_spec.md` §9.1 (request shape, validation
matrix), §4 / §4.1 (Problem+JSON registry). Body-shape failures
produce 400 + `/errors/validation`; the semantic 422 cases (duplicate
`recipe_id`, unknown `recipe_id`) produce 422 + `/errors/validation`
per the resolved decision in the phase-7 plan (no dedicated URI in §4.1
for shopping-list duplicates; the implementer raises a
`ServiceValidationError` with `violations`).

testing_strategy.md §5 phase 7 enumerates: empty `items` → 400;
duplicate `recipe_id` → 422; `servings <= 0` → 400. This file covers
those plus a few near-neighbour cases (missing fields, negative
servings, unknown recipe id) so the API contract is locked down.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_VALIDATION,
    assert_problem_json,
)


def _energy_weight_fact(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 100,
        }
    ]


def _make_owned_recipe(
    api_base_url: str,
    token: str,
    nutrition_fact_ids: dict[str, int],
    make_product,
    make_recipe,
) -> dict:
    """Helper: produce a single accessible recipe for the duplicate /
    valid-shape tests so the only failing condition is the one under
    test."""
    p = make_product(
        token=token,
        name="Validation Product",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    return make_recipe(
        token=token,
        name="Validation Recipe",
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    )


# ---------------------------------------------------------------------------
# Body-shape (400 + /errors/validation).
# ---------------------------------------------------------------------------


def test_empty_items_returns_400(
    api_base_url: str,
    make_user,
) -> None:
    """testing_strategy.md §5 phase 7: empty `items` → 400."""
    _user, token = make_user(username="alice_empty_items", password="hunter2pwd")
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body={"items": []}
    )
    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_missing_items_field_returns_400(
    api_base_url: str,
    make_user,
) -> None:
    """api_spec §9.1: `items` is required."""
    _user, token = make_user(username="alice_no_items", password="hunter2pwd")
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body={}
    )
    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_servings_zero_returns_400(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """testing_strategy.md §5 phase 7: `servings <= 0` → 400.

    Pydantic-level constraint (`gt=0`). Status is 400 and type is
    `/errors/validation` per api_spec §4.1.
    """
    _user, token = make_user(username="alice_zero_servings", password="hunter2pwd")
    r = _make_owned_recipe(
        api_base_url, token, nutrition_fact_ids, make_product, make_recipe
    )

    body = {"items": [{"recipe_id": r["id"], "servings": 0}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_servings_negative_returns_400(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §9.1: `servings > 0`. Negative value rejected at body
    validation."""
    _user, token = make_user(username="alice_neg_servings", password="hunter2pwd")
    r = _make_owned_recipe(
        api_base_url, token, nutrition_fact_ids, make_product, make_recipe
    )

    body = {"items": [{"recipe_id": r["id"], "servings": -2}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_servings_missing_returns_400(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """`servings` is a required field on each item."""
    _user, token = make_user(username="alice_miss_servings", password="hunter2pwd")
    r = _make_owned_recipe(
        api_base_url, token, nutrition_fact_ids, make_product, make_recipe
    )

    body = {"items": [{"recipe_id": r["id"]}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_recipe_id_missing_returns_400(
    api_base_url: str,
    make_user,
) -> None:
    """`recipe_id` is required per item (api_spec §9.1)."""
    _user, token = make_user(username="alice_miss_recipe_id", password="hunter2pwd")
    body = {"items": [{"servings": 1}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


# ---------------------------------------------------------------------------
# Semantic 422 cases (duplicate, unknown).
# ---------------------------------------------------------------------------


def test_duplicate_recipe_id_returns_422(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """testing_strategy.md §5 phase 7: duplicate `recipe_id` → 422.

    Per the phase-7 plan's resolved decision: 422 + `/errors/validation`
    (api_spec §4.1 has no dedicated `/errors/duplicate-recipe-id` URI).
    """
    _user, token = make_user(username="alice_dup_recipe", password="hunter2pwd")
    r = _make_owned_recipe(
        api_base_url, token, nutrition_fact_ids, make_product, make_recipe
    )

    body = {
        "items": [
            {"recipe_id": r["id"], "servings": 1},
            {"recipe_id": r["id"], "servings": 2},
        ]
    }
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    body_out = assert_problem_json(
        response, status=422, type_uri=ERROR_VALIDATION
    )
    # Soft check on violations when the implementer surfaces them.
    extensions = body_out.get("extensions") or {}
    violations = extensions.get("violations")
    if violations is not None:
        assert isinstance(violations, list) and violations, (
            f"`extensions.violations` (when present) must be non-empty, "
            f"got {extensions!r}"
        )
        assert any(
            "recipe_id" in (v.get("field") or "")
            or str(r["id"]) in (v.get("message") or "")
            for v in violations
        ), (
            f"At least one violation should reference recipe_id={r['id']}, "
            f"got {violations!r}"
        )


def test_unknown_recipe_id_returns_422(
    api_base_url: str,
    make_user,
) -> None:
    """api_spec §9.1: unknown recipe → 422.

    Aligned with phase-5 unknown `product_id` precedent: 422 +
    `/errors/validation` (`ServiceValidationError` with violations).
    """
    _user, token = make_user(username="alice_unknown_recipe", password="hunter2pwd")
    body = {"items": [{"recipe_id": 999_999, "servings": 1}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    body_out = assert_problem_json(
        response, status=422, type_uri=ERROR_VALIDATION
    )
    # Soft check on violations.
    extensions = body_out.get("extensions") or {}
    violations = extensions.get("violations")
    if violations is not None:
        assert isinstance(violations, list) and violations
