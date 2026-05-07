"""Phase-9 shopping-list flow via the UI.

Covers `testing_strategy.md` §5 phase 9 (`test_shopping_list.py` —
"select two recipes, set servings, click compute, the displayed
shopping list matches manually-computed totals").

Reuses the canonical worked example from
`tests/phase-7-shopping-list/test_shopping_list_aggregation.py`
(also enshrined in `testing_strategy.md` §5 phase 7):
- R1: 100g Chicken + 200g Rice
- R2: 150g Chicken + 50ml Olive Oil
- POST /shopping-list { items: [{R1, 2}, {R2, 1}] }
  → Brown Rice    weight g  400  (200 * 2)
  → Chicken Breast weight g  350  (100 * 2 + 150 * 1)
  → Olive Oil     volume ml  50  (50 * 1)

Sort order is `(product_name ASC, quantity_type ASC)` per
`api_spec.md` §9.1.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect


def _login_via_ui(
    page: Page, app_base_url: str, *, username: str, password: str
) -> None:
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)


def _parse_leading_number(text: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    assert match is not None, f"no numeric value found in {text!r}"
    return float(match.group(0))


def _energy_weight_fact(nutrition_fact_ids: dict[str, int]) -> list[dict[str, Any]]:
    """Minimal nutrition fact list — every product needs ≥1 fact
    (`api_spec.md` §6.1). Shopping-list output ignores nutrition facts
    entirely (`api_spec.md` §9.1), so the value is irrelevant to this
    test's assertions; we only need the products to be creatable.
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


def _select_recipe_in_picker(
    page: Page,
    *,
    recipe_name: str,
    servings: float,
) -> None:
    """Open the recipe-picker modal, click the recipe by name, then
    set its servings input.

    Per `implementation_plan.md` §Phase 9, the page exposes an "Add
    recipe" button that opens a modal listing the user's own + starred
    recipes; clicking a recipe in the modal adds it to the selection
    list with a `servings` input (default 1). We match leniently on
    accessible names so wording variations don't break the test.
    """
    page.get_by_role(
        "button", name=re.compile(r"add\s+recipe", re.IGNORECASE)
    ).click()

    # Modal listing should expose each recipe as a clickable
    # button / option / list item — match leniently.
    page.get_by_role("button", name=re.compile(re.escape(recipe_name))).or_(
        page.get_by_role("option", name=re.compile(re.escape(recipe_name)))
    ).first.click()

    # The selected recipe must now show up with a servings input.
    # Implementations differ in label phrasing — match leniently. We
    # target the most recently added row by taking the last visible
    # input; default is 1 per the implementation plan, and we
    # overwrite it.
    if servings != 1:
        servings_input = page.get_by_label(
            re.compile(r"servings?", re.IGNORECASE)
        ).last
        servings_input.fill(str(servings))


def test_shopping_list_two_recipes_match_worked_example(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids: dict[str, int],
) -> None:
    """Worked example from `testing_strategy.md` §5 phase 7, verified
    through the UI. Alice owns both recipes (the simpler accessibility
    case — `api_spec.md` §9.1 also accepts starred recipes, but
    "owns" is enough to exercise the UI happy path).
    """
    _user, token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )

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
            {
                "product_id": chicken["id"],
                "quantity_type": "weight",
                "amount": 100,
            },
            {
                "product_id": rice["id"],
                "quantity_type": "weight",
                "amount": 200,
            },
        ],
    )
    r2 = make_recipe(
        token=token,
        name="Olive Oil Chicken",
        products=[
            {
                "product_id": chicken["id"],
                "quantity_type": "weight",
                "amount": 150,
            },
            {
                "product_id": olive_oil["id"],
                "quantity_type": "volume",
                "amount": 50,
            },
        ],
    )

    _login_via_ui(page, app_base_url, username="alice", password="hunter2pwd")

    # Navigate to the Shopping List section. `implementation_plan.md`
    # §Phase 9 mandates a nav entry; match leniently on text.
    page.get_by_role(
        "link", name=re.compile(r"shopping", re.IGNORECASE)
    ).first.click()
    page.wait_for_url(re.compile(r"/shopping-list(?:[/?#]|$)"))

    # Add R1 with 2 servings, R2 with 1 serving.
    _select_recipe_in_picker(page, recipe_name="Chicken Rice Bowl", servings=2)
    _select_recipe_in_picker(page, recipe_name="Olive Oil Chicken", servings=1)

    # Click Compute (regex-match the button) and capture the response.
    with page.expect_response(
        lambda r: r.url.endswith("/api/shopping-list")
        and r.request.method == "POST"
        and r.status == 200
    ) as response_info:
        page.get_by_role(
            "button", name=re.compile(r"compute|generate", re.IGNORECASE)
        ).first.click()
    api_items = response_info.value.json()["items"]
    assert len(api_items) == 3, (
        f"backend should aggregate to 3 rows, got {api_items!r}"
    )

    # The displayed table must echo the API's items in order.
    # `api_spec.md` §9.1: sort order is (product_name ASC,
    # quantity_type ASC). For this fixture that yields:
    expected_rows = [
        ("Brown Rice", "weight", "g", 400.0),
        ("Chicken Breast", "weight", "g", 350.0),
        ("Olive Oil", "volume", "ml", 50.0),
    ]

    # Sanity: the API itself must return rows in the specified order
    # before we even look at the UI — protects against a backend
    # regression masking as a UI bug.
    api_keys = [
        (row["product_name"], row["quantity_type"]) for row in api_items
    ]
    assert api_keys == [(name, qty) for name, qty, _u, _t in expected_rows], (
        f"backend sort-order regression: got {api_keys!r}"
    )

    # Each expected row must render in the table with the correct
    # amount and unit. We locate by product name and read the row's
    # text content so the assertion survives layout / class changes.
    for product_name, quantity_type, unit, total in expected_rows:
        row = page.get_by_role(
            "row", name=re.compile(re.escape(product_name))
        ).first
        expect(row).to_be_visible()
        row_text = row.inner_text()
        assert _parse_leading_number(_strip_name(row_text, product_name)) == pytest.approx(
            total
        ), (
            f"row {product_name!r} expected amount ≈ {total}, got "
            f"text={row_text!r}"
        )
        assert quantity_type.lower() in row_text.lower(), (
            f"row {product_name!r} must show quantity_type "
            f"{quantity_type!r}, got {row_text!r}"
        )
        assert _row_shows_unit(row_text, unit), (
            f"row {product_name!r} must show unit {unit!r}, got "
            f"{row_text!r}"
        )


def _strip_name(row_text: str, product_name: str) -> str:
    """Remove the product-name occurrence from the row text so the
    leading numeric parser doesn't trip on digits in the name.

    No phase-9 fixture name carries digits, but stripping the name is
    cheap insurance against future fixture changes.
    """
    return row_text.replace(product_name, "")


def _row_shows_unit(row_text: str, unit: str) -> bool:
    """Match `g` / `ml` as a standalone token in the row text.

    `g` would otherwise false-match every other letter; require a
    word-boundary match.
    """
    return re.search(rf"\b{re.escape(unit)}\b", row_text) is not None
