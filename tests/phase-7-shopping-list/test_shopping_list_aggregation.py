"""Shopping-list aggregation integration tests.

Spec: `.specs/ai_gen/api_spec.md` §9.1 (request/response shape, sort
order, `unit` derivation, aggregation rule), §13 (the per-product
formula). The canonical worked example here matches
`testing_strategy.md` §5 phase 7.

Aggregation rule: rows are grouped by `(product_id, quantity_type)`,
totals scaled by the per-recipe `servings` count. `unit` is `"g"` for
`weight` and `"ml"` for `volume`. Output is sorted by
`(product_name ASC, quantity_type ASC)` for deterministic order.

Asserted with `pytest.approx` on numeric fields because amounts are
floating point.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import api as api_helpers


def _energy_weight_fact(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    """Minimal facts list — every product needs ≥1 fact (api_spec §6.1).

    Shopping-list output ignores nutrition facts entirely (api_spec §9.1),
    so the value here is irrelevant to assertions; we just need the
    product to be creatable.
    """
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "weight",
            "amount": 100,
        }
    ]


def _energy_volume_fact(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": nutrition_fact_ids["Energy"],
            "quantity_type": "volume",
            "amount": 50,
        }
    ]


def _energy_both_facts(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [
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
    ]


# ---------------------------------------------------------------------------
# The canonical worked example from testing_strategy.md §5 phase 7.
# ---------------------------------------------------------------------------


def test_shopping_list_worked_example(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """testing_strategy.md §5 phase 7 worked example.

    Recipe R1: 100 g Chicken + 200 g Rice.
    Recipe R2: 150 g Chicken + 50 ml Olive Oil.
    POST /shopping-list {items: [{R1, 2}, {R2, 1}]} →
      - Brown Rice    weight g  400  (200 * 2)
      - Chicken Breast weight g  350  (100 * 2 + 150 * 1)
      - Olive Oil     volume ml  50  (50 * 1)
    Sorted by (product_name ASC, quantity_type ASC).
    """
    user, token = make_user(username="alice_shop_worked", password="hunter2pwd")

    chicken = make_product(
        token=token,
        name="Chicken Breast",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    rice = make_product(
        token=token,
        name="Brown Rice",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    olive_oil = make_product(
        token=token,
        name="Olive Oil",
        nutrition_facts=_energy_volume_fact(nutrition_fact_ids),
    )

    r1 = make_recipe(
        token=token,
        name="Chicken Rice Bowl",
        products=[
            {"product_id": chicken["id"], "quantity_type": "weight", "amount": 100},
            {"product_id": rice["id"], "quantity_type": "weight", "amount": 200},
        ],
    )
    r2 = make_recipe(
        token=token,
        name="Olive Oil Chicken",
        products=[
            {"product_id": chicken["id"], "quantity_type": "weight", "amount": 150},
            {"product_id": olive_oil["id"], "quantity_type": "volume", "amount": 50},
        ],
    )

    body = {
        "items": [
            {"recipe_id": r1["id"], "servings": 2},
            {"recipe_id": r2["id"], "servings": 1},
        ]
    }
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert response.status_code == 200, (
        f"Expected 200 from POST /shopping-list, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    assert "application/json" in response.headers.get("content-type", "")

    payload = response.json()
    assert isinstance(payload, dict), (
        f"Shopping list response must be a JSON object, got {type(payload).__name__}: {payload!r}"
    )
    items = payload.get("items")
    assert isinstance(items, list), (
        f"Shopping list response must include `items` list, got {payload!r}"
    )
    assert len(items) == 3, (
        f"Three distinct (product, quantity_type) groups expected; "
        f"got {len(items)}: {items!r}"
    )

    # api_spec §9.1: sorted by (product_name ASC, quantity_type ASC).
    expected_order = [
        (rice["id"], "weight", "g", 400.0, "Brown Rice"),
        (chicken["id"], "weight", "g", 350.0, "Chicken Breast"),
        (olive_oil["id"], "volume", "ml", 50.0, "Olive Oil"),
    ]
    for got, (pid, qty, unit, total, name) in zip(items, expected_order):
        assert got.get("product_id") == pid, (
            f"product_id mismatch in row {got!r}; expected {pid}"
        )
        assert got.get("product_name") == name, (
            f"product_name mismatch in row {got!r}; expected {name!r}"
        )
        assert got.get("quantity_type") == qty, (
            f"quantity_type mismatch in row {got!r}; expected {qty!r}"
        )
        assert got.get("unit") == unit, (
            f"unit must derive from quantity_type per api_spec §9.1 "
            f"(`g` for weight, `ml` for volume); row {got!r}"
        )
        assert float(got.get("total_amount")) == pytest.approx(total), (
            f"total_amount mismatch in row {got!r}; expected {total}"
        )
        # api_spec §9.1: image filename echoed; products created without
        # one must report null.
        assert "product_image_filename" in got, (
            f"row must carry `product_image_filename` key, got {got!r}"
        )
        assert got["product_image_filename"] is None, (
            f"product_image_filename must be null when source product "
            f"has none; got {got!r}"
        )

    # Sanity: the response envelope must NOT carry pagination keys —
    # api_spec §9.1 has a flat `{"items": [...]}` shape, no `self`/`next`.
    assert "self" not in payload, (
        f"shopping-list response must not carry pagination `self`, got {payload!r}"
    )
    assert "next" not in payload, (
        f"shopping-list response must not carry pagination `next`, got {payload!r}"
    )

    # Owner can hit their own shopping list (smoke that the call exercised
    # User A's own recipes, not a starred-by relationship).
    assert user["id"] is not None


# ---------------------------------------------------------------------------
# Fractional servings (api_spec §9.1 example uses servings: 1.5).
# ---------------------------------------------------------------------------


def test_shopping_list_accepts_fractional_servings(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §9.1: `servings` is `> 0`, fractional allowed."""
    _user, token = make_user(username="alice_shop_frac", password="hunter2pwd")
    p = make_product(
        token=token,
        name="Tofu",
        nutrition_facts=_energy_weight_fact(nutrition_fact_ids),
    )
    r = make_recipe(
        token=token,
        name="Tofu Plate",
        products=[
            {"product_id": p["id"], "quantity_type": "weight", "amount": 100},
        ],
    )

    body = {"items": [{"recipe_id": r["id"], "servings": 1.5}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert response.status_code == 200, (
        f"Expected 200 from fractional-servings request, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    items = response.json()["items"]
    assert len(items) == 1, items
    row = items[0]
    assert row["product_id"] == p["id"]
    assert row["quantity_type"] == "weight"
    assert row["unit"] == "g"
    assert float(row["total_amount"]) == pytest.approx(150.0), (
        f"100 g x 1.5 servings must equal 150 g; got {row!r}"
    )


# ---------------------------------------------------------------------------
# Empty-products recipes contribute nothing.
# ---------------------------------------------------------------------------


def test_shopping_list_empty_recipe_yields_empty_items(
    api_base_url: str,
    make_user,
    make_recipe,
) -> None:
    """A recipe whose `products: []` contributes nothing to the totals.

    api_spec §7.1 explicitly allows empty `products`; api_spec §9.1
    aggregates only over `recipe_products` rows, so the resulting items
    array is empty.
    """
    _user, token = make_user(username="alice_shop_empty", password="hunter2pwd")
    r = make_recipe(token=token, name="Concept Recipe")  # no products

    body = {"items": [{"recipe_id": r["id"], "servings": 3}]}
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert response.status_code == 200, (
        f"Empty-recipe shopping list must succeed (200), "
        f"got {response.status_code}: {response.text!r}"
    )
    payload = response.json()
    assert payload.get("items") == [], (
        f"Empty recipe contributes no rows; expected items=[], got {payload!r}"
    )


# ---------------------------------------------------------------------------
# Same product in multiple recipes with DIFFERENT quantity_type → two rows.
# ---------------------------------------------------------------------------


def test_shopping_list_keeps_quantity_types_separate_for_same_product(
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """api_spec §9.1: groups by `(product_id, quantity_type)`. Different
    quantity_types of the same product yield separate rows because the
    units (`g` vs `ml`) are not commensurable.
    """
    _user, token = make_user(username="alice_shop_dual", password="hunter2pwd")

    dual = make_product(
        token=token,
        name="Dual-Form Ingredient",
        image_filename="dual.jpg",
        nutrition_facts=_energy_both_facts(nutrition_fact_ids),
    )

    r_weight = make_recipe(
        token=token,
        name="Weight Use",
        products=[
            {"product_id": dual["id"], "quantity_type": "weight", "amount": 100},
        ],
    )
    r_volume = make_recipe(
        token=token,
        name="Volume Use",
        products=[
            {"product_id": dual["id"], "quantity_type": "volume", "amount": 200},
        ],
    )

    body = {
        "items": [
            {"recipe_id": r_weight["id"], "servings": 2},
            {"recipe_id": r_volume["id"], "servings": 1},
        ]
    }
    response = api_helpers.shopping_list_compute(
        api_base_url, token=token, body=body
    )
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text!r}"
    )
    items = response.json()["items"]
    assert len(items) == 2, (
        f"Same product at two quantity_types must produce two rows; "
        f"got {len(items)}: {items!r}"
    )

    # Sort order: product_name ASC, quantity_type ASC. Both rows share the
    # same product_name, so volume comes before weight alphabetically.
    by_qty = {row["quantity_type"]: row for row in items}
    assert set(by_qty.keys()) == {"weight", "volume"}, (
        f"Both quantity_types must be represented, got {set(by_qty)!r}"
    )

    weight_row = by_qty["weight"]
    assert weight_row["product_id"] == dual["id"]
    assert weight_row["unit"] == "g"
    assert float(weight_row["total_amount"]) == pytest.approx(200.0)
    assert weight_row.get("product_image_filename") == "dual.jpg", (
        f"product_image_filename must echo the source product's filename; "
        f"got {weight_row!r}"
    )

    volume_row = by_qty["volume"]
    assert volume_row["product_id"] == dual["id"]
    assert volume_row["unit"] == "ml"
    assert float(volume_row["total_amount"]) == pytest.approx(200.0), (
        f"200 ml * 1 serving = 200 ml; got {volume_row!r}"
    )

    # And the order is volume-first (alphabetical within shared name).
    assert items[0]["quantity_type"] == "volume", (
        f"Sort order is (product_name ASC, quantity_type ASC); "
        f"`volume` < `weight` so the volume row must come first. "
        f"Got items={items!r}"
    )
