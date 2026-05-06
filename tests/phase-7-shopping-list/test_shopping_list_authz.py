"""Shopping-list authorization integration tests.

Spec: `.specs/ai_gen/api_spec.md` §9.1 (a recipe can be requested only
if the caller owns it OR has starred it; otherwise 422 with
`/errors/validation`), §1.5 / §15 (auth required on POST /shopping-list).

The "not-accessible recipe → 422" assertion is the canonical case from
`testing_strategy.md` §5 phase 7.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_UNAUTHORIZED,
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


# ---------------------------------------------------------------------------
# Not-owned + not-starred → 422 + /errors/validation.
# ---------------------------------------------------------------------------


def test_shopping_list_rejects_not_accessible_recipe(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """testing_strategy.md §5 phase 7: User B includes A's recipe without
    starring it → 422 + `/errors/validation`.

    Per api_spec §9.1, the body shape is the same `/errors/validation`
    URI used elsewhere; the per-violation context (which `recipe_id` was
    rejected) is carried under `extensions.violations`.
    """
    user_a, token_a = make_user(username="alice_owns_recipe", password="hunter2pwd")
    p = make_product(
        token=token_a,
        name="Owned Product",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    r = make_recipe(
        token=token_a,
        name="A's Recipe",
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    )

    user_b, token_b = make_user(username="bob_no_access", password="hunter2pwd")
    body = {"items": [{"recipe_id": r["id"], "servings": 1}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token_b, body=body
    )

    body_out = assert_problem_json(
        response, status=422, type_uri=ERROR_VALIDATION
    )
    # Soft check: when violations are present, they must reference the
    # offending recipe_id so callers can render an actionable message.
    extensions = body_out.get("extensions") or {}
    violations = extensions.get("violations")
    if violations is not None:
        assert isinstance(violations, list) and violations, (
            f"`extensions.violations` (when present) must be a non-empty "
            f"list, got {extensions!r}"
        )
        assert any(
            "recipe_id" in (v.get("field") or "")
            or str(r["id"]) in (v.get("message") or "")
            for v in violations
        ), (
            f"At least one violation must reference recipe_id={r['id']}, "
            f"got {violations!r}"
        )

    # Caller's identity is already authenticated (token_b is valid) so the
    # rejection is on the not-accessible rule, not on auth.
    assert user_b["id"] != user_a["id"]


# ---------------------------------------------------------------------------
# Starred recipe is accessible → 200.
# ---------------------------------------------------------------------------


def test_shopping_list_allows_starred_recipe(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §9.1: recipe accessible if owned **or** starred by the
    caller. User B stars A's recipe and then computes a shopping list."""
    _user_a, token_a = make_user(username="alice_starred_for_b", password="hunter2pwd")
    p = make_product(
        token=token_a,
        name="Sweet Potato",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    r = make_recipe(
        token=token_a,
        name="A's Starred Recipe",
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 250},
        ],
    )

    _user_b, token_b = make_user(username="bob_stars_for_shop", password="hunter2pwd")
    star = api_helpers.recipes_star(
        api_base_url, token=token_b, recipe_id=r["id"]
    )
    assert star.status_code == 204, (
        f"Pre-step PUT /recipes/{r['id']}/star expected 204, "
        f"got {star.status_code}: {star.text!r}"
    )

    body = {"items": [{"recipe_id": r["id"], "servings": 4}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token_b, body=body
    )
    assert response.status_code == 200, (
        f"Starring a recipe must grant shopping-list access; "
        f"expected 200, got {response.status_code}: {response.text!r}"
    )
    items = response.json()["items"]
    assert len(items) == 1, items
    row = items[0]
    assert row["product_id"] == p["id"]
    assert row["quantity_type"] == "weight"
    assert row["unit"] == "g"
    assert float(row["total_amount"]) == pytest.approx(1000.0), (
        f"250 g x 4 servings = 1000 g; got {row!r}"
    )


# ---------------------------------------------------------------------------
# Owner of every recipe is allowed → 200 (smoke).
# ---------------------------------------------------------------------------


def test_shopping_list_allows_caller_owned_recipe(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Smoke: caller-owned recipe is accessible without an explicit star."""
    _user, token = make_user(username="alice_owns_only", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Lentils",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    r = make_recipe(
        token=token,
        name="Lentil Soup",
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 75},
        ],
    )

    body = {"items": [{"recipe_id": r["id"], "servings": 2}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert float(items[0]["total_amount"]) == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Unauthenticated → 401 + /errors/unauthorized.
# ---------------------------------------------------------------------------


def test_shopping_list_without_token_returns_401(
    api_base_url: str,
) -> None:
    """api_spec §15: POST /shopping-list requires authentication."""
    body = {"items": [{"recipe_id": 1, "servings": 1}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=None, body=body
    )
    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Mixed-access list (one owned, one inaccessible) is rejected as a whole.
# ---------------------------------------------------------------------------


def test_shopping_list_rejects_when_any_recipe_not_accessible(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """A request mixing one accessible and one inaccessible recipe must
    fail as a whole (api_spec §9.1: the rule applies per-item, but a
    violation in any item rejects the request)."""
    user_a, token_a = make_user(username="alice_mix_owner", password="hunter2pwd")
    p_a = make_product(
        token=token_a,
        name="A's Product",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    r_a = make_recipe(
        token=token_a,
        name="A's Locked Recipe",
        products=[
            {"product_id": p_a["id"], "quantity_type": "weight", "amount": 50},
        ],
    )

    _user_b, token_b = make_user(username="bob_mix", password="hunter2pwd")
    p_b = make_product(
        token=token_b,
        name="B's Product",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    r_b = make_recipe(
        token=token_b,
        name="B's Recipe",
        products=[
            {"product_id": p_b["id"], "quantity_type": "weight", "amount": 50},
        ],
    )

    body = {
        "items": [
            {"recipe_id": r_b["id"], "servings": 1},  # accessible (owned)
            {"recipe_id": r_a["id"], "servings": 1},  # inaccessible
        ]
    }
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token_b, body=body
    )
    assert_problem_json(response, status=422, type_uri=ERROR_VALIDATION)

    # Sanity: user_a and user_b are distinct so the inaccessibility is
    # genuine.
    assert user_a["id"] != _user_b["id"]
