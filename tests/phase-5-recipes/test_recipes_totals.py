"""Recipe nutrition-totals integration tests.

Spec: `.specs/ai_gen/api_spec.md` §3.7 (`nutrition_totals_per_serving`
shape), §13 (computation formula).

The §13 formula:

    For each nutrition_fact_type t:
      total_t = sum_{i=1..n} (
        pnf(p_i, t, q_i).amount × (a_i / 100)
      )

where `pnf(p_i, t, q_i)` is the product-nutrition-fact row for product
`p_i`, nutrition fact type `t`, and quantity type `q_i`. If no such row
exists, the contribution is 0. Zero totals are omitted from the
response.

Asserted with `pytest.approx` because amounts are floating point.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import api as api_helpers


def _totals_by_name(
    totals: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index `nutrition_totals_per_serving` by `nutrition_fact_name`."""
    return {t["nutrition_fact_name"]: t for t in totals}


def _make_two_products_chicken_and_rice(
    api_base_url: str,
    token: str,
    nutrition_fact_ids: dict[str, int],
    make_product,
) -> tuple[dict, dict]:
    """The §13 worked-example fixture: P (Chicken) + Q (Rice).

    P has Energy 165 kcal/100g + Protein 31 g/100g.
    Q has Energy 130 kcal/100g + Protein 2.7 g/100g.
    """
    p = make_product(
        token=token,
        name="Chicken Breast",
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
    q = make_product(
        token=token,
        name="Brown Rice",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 130,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 2.7,
            },
        ],
    )
    return p, q


def test_totals_match_worked_example(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """testing_strategy.md §5 phase 5 worked example.

    Recipe R with 200g of P and 100g of Q.
    Expected totals (per serving):
      - Energy = 165 * 2 + 130 * 1 = 460 kcal
      - Protein = 31 * 2 + 2.7 * 1 = 64.7 g
    """
    _user, token = make_user(username="alice_totals", password="hunter2pwd")
    p, q = _make_two_products_chicken_and_rice(
        api_base_url, token, nutrition_fact_ids, make_product
    )

    body = {
        "name": "Worked Example",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 200},
            {"product_id": q["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert created.status_code == 201, created.text
    recipe = created.json()

    totals = recipe.get("nutrition_totals_per_serving")
    assert isinstance(totals, list), (
        f"nutrition_totals_per_serving must be a list, got {type(totals)!r}"
    )
    by_name = _totals_by_name(totals)
    assert set(by_name.keys()) == {"Energy", "Protein"}, (
        f"Expected exactly Energy + Protein totals, got {sorted(by_name)!r}"
    )

    energy = by_name["Energy"]
    assert energy["nutrition_fact_id"] == nutrition_fact_ids["Energy"]
    assert energy["unit"] == "kcal"
    assert float(energy["amount"]) == pytest.approx(460.0)

    protein = by_name["Protein"]
    assert protein["nutrition_fact_id"] == nutrition_fact_ids["Protein"]
    assert protein["unit"] == "g"
    assert float(protein["amount"]) == pytest.approx(64.7)

    # Totals must be identical when re-fetched via GET.
    fetched = api_helpers.recipes_get(
        api_base_url, token=token, recipe_id=recipe["id"]
    )
    assert fetched.status_code == 200, fetched.text
    fetched_totals = _totals_by_name(
        fetched.json()["nutrition_totals_per_serving"]
    )
    assert float(fetched_totals["Energy"]["amount"]) == pytest.approx(460.0)
    assert float(fetched_totals["Protein"]["amount"]) == pytest.approx(64.7)


def test_totals_empty_when_no_products(
    api_base_url: str, make_user
) -> None:
    """api_spec §13: zero totals are omitted; empty recipe → empty totals."""
    _user, token = make_user(username="alice_empty_totals", password="hunter2pwd")

    body = {
        "name": "Empty Totals",
        "products": [],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert created.status_code == 201, created.text
    assert created.json()["nutrition_totals_per_serving"] == []


def test_totals_omit_nutrition_facts_with_zero_contribution(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Product with only Energy → totals must contain ONLY Energy.

    api_spec §13: "Zero totals are omitted." A product missing Protein
    contributes 0 to the Protein total, which the response must drop.
    """
    _user, token = make_user(username="alice_omit_zero", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Energy-Only",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 200,
            }
        ],
    )

    body = {
        "name": "Energy-Only Recipe",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert created.status_code == 201, created.text

    by_name = _totals_by_name(created.json()["nutrition_totals_per_serving"])
    assert set(by_name.keys()) == {"Energy"}, (
        f"Only Energy should be present (Protein/Net Carbs/Fat/Fibers all 0); "
        f"got {sorted(by_name)!r}"
    )
    assert float(by_name["Energy"]["amount"]) == pytest.approx(200.0)


def test_totals_handle_mixed_quantity_types(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Recipe combining a weight product and a volume product.

    Expected Energy = 100 (kcal/100g) * 2 + 50 (kcal/100ml) * 3 = 350 kcal.
    """
    _user, token = make_user(username="alice_mixed_qty", password="hunter2pwd")
    weight_only = make_product(
        token=token,
        name="Solid Stuff",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    )
    volume_only = make_product(
        token=token,
        name="Liquid Stuff",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "volume",
                "amount": 50,
            }
        ],
    )

    body = {
        "name": "Mixed Quantity Types",
        "products": [
            {
                "product_id": weight_only["id"],
                "quantity_type": "weight",
                "amount": 200,
            },
            {
                "product_id": volume_only["id"],
                "quantity_type": "volume",
                "amount": 300,
            },
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert created.status_code == 201, created.text

    by_name = _totals_by_name(created.json()["nutrition_totals_per_serving"])
    assert "Energy" in by_name, by_name
    assert float(by_name["Energy"]["amount"]) == pytest.approx(350.0)


def test_totals_use_only_facts_for_requested_quantity_type(
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """A product with both weight and volume Energy facts must
    contribute only the row that matches the recipe-product's
    `quantity_type` (api_spec §13: `pnf(p_i, t, q_i)` is keyed by
    the recipe-product's `q_i`).

    Product P has Energy=100 weight + Energy=50 volume.
    Recipe references P at weight=200g → Energy = 100 * 2 = 200,
    NOT 50 * 2 = 100.
    """
    _user, token = make_user(username="alice_qty_select", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Dual-Form",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "volume",
                "amount": 50,
            },
        ],
    )

    body = {
        "name": "Weight Only Reference",
        "products": [
            {"product_id": p["id"], "quantity_type": "weight", "amount": 200},
        ],
    }
    created = api_helpers.recipes_create(api_base_url, token=token, body=body)
    assert created.status_code == 201, created.text

    by_name = _totals_by_name(created.json()["nutrition_totals_per_serving"])
    assert "Energy" in by_name, by_name
    assert float(by_name["Energy"]["amount"]) == pytest.approx(200.0), (
        f"Expected the weight-row (100 kcal/100g * 2) to drive Energy, "
        f"got {by_name['Energy']!r}"
    )
