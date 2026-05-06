"""Product validation integration tests.

Spec: `.specs/ai_gen/api_spec.md` §6.1, §6.3, §4 (Problem+JSON), §4.1
(error registry). Covers semantic validation (`/errors/no-nutrition-facts`,
`/errors/duplicate-nutrition-fact`) and request-shape validation
(`/errors/validation` with `extensions.violations`).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_DUPLICATE_NUTRITION_FACT,
    ERROR_NO_NUTRITION_FACTS,
    ERROR_VALIDATION,
    assert_problem_json,
)


def _valid_facts(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 100,
        }
    ]


# ---------------------------------------------------------------------------
# Empty / duplicate / unknown nutrition fact rules
# ---------------------------------------------------------------------------


def test_create_with_empty_nutrition_facts_returns_422(
    api_base_url: str, make_user
) -> None:
    """api_spec §6.1: every product needs >= 1 fact."""
    _user, token = make_user(username="vee_empty", password="hunter2pwd")

    body = {
        "name": "No Facts",
        "image_filename": None,
        "nutrition_facts": [],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert_problem_json(response, status=422, type_uri=ERROR_NO_NUTRITION_FACTS)


def test_create_with_duplicate_id_quantity_type_returns_422(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """api_spec §6.1: no `(nutrition_fact_id, quantity_type)` duplicates per product."""
    _user, token = make_user(username="vee_dup", password="hunter2pwd")

    body = {
        "name": "Duplicated",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 200,  # different amount, but same (id, qty)
            },
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert_problem_json(response, status=422, type_uri=ERROR_DUPLICATE_NUTRITION_FACT)


def test_create_same_id_different_quantity_type_is_allowed(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """db_schema §4.4: composite PK is `(product_id, nutrition_fact_id, quantity_type)`,
    so the same fact id may appear once per quantity_type."""
    _user, token = make_user(username="vee_diff_qty", password="hunter2pwd")

    body = {
        "name": "Energy in Both Forms",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "volume",
                "amount": 80,
            },
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert response.status_code == 201, (
        f"Same id with two different quantity_types must succeed; "
        f"got {response.status_code}. Body: {response.text!r}"
    )


def test_create_with_unknown_nutrition_fact_id_returns_validation_error(
    api_base_url: str, make_user
) -> None:
    """api_spec §6.1: unknown `nutrition_fact_id` produces 422 with `violations`.

    The implementation may surface this as a foreign-key style validation
    error; the contract requires `type=/errors/validation` and a
    `violations` array referencing the offending field path.
    """
    _user, token = make_user(username="vee_unknown_fk", password="hunter2pwd")

    body = {
        "name": "Bogus FK",
        "nutrition_facts": [
            {
                "nutrition_fact_id": 999_999,  # nonexistent
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    body_out = assert_problem_json(
        response, status=422, type_uri=ERROR_VALIDATION
    )
    extensions = body_out.get("extensions") or {}
    violations = extensions.get("violations")
    assert isinstance(violations, list) and violations, (
        f"Expected non-empty extensions.violations, got {extensions!r}"
    )
    # At least one violation must mention the offending field path.
    assert any(
        "nutrition_facts" in (v.get("field") or "")
        and "nutrition_fact_id" in (v.get("field") or "")
        for v in violations
    ), (
        f"Expected a violation referencing nutrition_facts.*.nutrition_fact_id, "
        f"got {violations!r}"
    )


# ---------------------------------------------------------------------------
# Body shape / Pydantic-level validation (status 400)
# ---------------------------------------------------------------------------


def test_create_missing_name_returns_400(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="vee_no_name", password="hunter2pwd")

    body = {
        "nutrition_facts": _valid_facts(nutrition_fact_ids),
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_create_empty_name_returns_400(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """api_spec §6.1: name must be 1-200 chars after trimming."""
    _user, token = make_user(username="vee_blank_name", password="hunter2pwd")

    body = {
        "name": "   ",
        "nutrition_facts": _valid_facts(nutrition_fact_ids),
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_create_negative_amount_returns_validation_error(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """api_spec §6.1: amount must be >= 0. Either 400 (Pydantic constraint)
    or 422 (semantic) is acceptable as long as type=/errors/validation."""
    _user, token = make_user(username="vee_neg", password="hunter2pwd")

    body = {
        "name": "Negative Amount",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": -1,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert response.status_code in (400, 422), (
        f"Expected 400 or 422 for negative amount, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    assert "application/problem+json" in response.headers.get("content-type", "")
    assert response.json().get("type") == ERROR_VALIDATION, (
        f"Expected type={ERROR_VALIDATION!r}, got {response.json().get('type')!r}"
    )


def test_create_invalid_quantity_type_returns_400(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """quantity_type must be `weight` or `volume`."""
    _user, token = make_user(username="vee_bad_qty", password="hunter2pwd")

    body = {
        "name": "Wrong Qty Type",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "mass",  # invalid enum
                "amount": 100,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)

    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


# ---------------------------------------------------------------------------
# Same validation rules apply on PUT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "empty_facts",
        "duplicate_facts",
        "unknown_fk",
    ],
)
def test_put_validation_mirrors_post(
    api_base_url: str,
    make_user,
    nutrition_fact_ids: dict[str, int],
    case: str,
) -> None:
    """api_spec §6.3: PUT shares POST's validation contract.

    Single test per semantic case — full coverage of edge cases is on the
    create side; this just confirms the same pipeline runs on update.
    """
    _user, token = make_user(username=f"vee_put_{case}", password="hunter2pwd")

    create_body = {
        "name": "Initial",
        "nutrition_facts": _valid_facts(nutrition_fact_ids),
    }
    created = api_helpers.products_create(
        api_base_url, token=token, body=create_body
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]

    if case == "empty_facts":
        bad = {"name": "Initial", "nutrition_facts": []}
        expected_type = ERROR_NO_NUTRITION_FACTS
        expected_status = 422
    elif case == "duplicate_facts":
        bad = {
            "name": "Initial",
            "nutrition_facts": [
                {
                    "nutrition_fact_id": nutrition_fact_ids["Energy"],
                    "quantity_type": "weight",
                    "amount": 1,
                },
                {
                    "nutrition_fact_id": nutrition_fact_ids["Energy"],
                    "quantity_type": "weight",
                    "amount": 2,
                },
            ],
        }
        expected_type = ERROR_DUPLICATE_NUTRITION_FACT
        expected_status = 422
    else:  # unknown_fk
        bad = {
            "name": "Initial",
            "nutrition_facts": [
                {
                    "nutrition_fact_id": 999_999,
                    "quantity_type": "weight",
                    "amount": 100,
                }
            ],
        }
        expected_type = ERROR_VALIDATION
        expected_status = 422

    response = api_helpers.products_update(
        api_base_url, token=token, product_id=product_id, body=bad
    )
    assert_problem_json(response, status=expected_status, type_uri=expected_type)
