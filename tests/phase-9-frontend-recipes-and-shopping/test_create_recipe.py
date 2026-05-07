"""Phase-9 recipe creation flow via the UI.

Covers `testing_strategy.md` §5 phase 9 (`test_create_recipe.py` —
"create a recipe, assert detail page shows the products list and
computed totals").

Drives the form from the New Recipe page (per `implementation_plan.md`
§Phase 9 the recipe form has name, description, image, plus a
products sub-form with autocomplete picker, quantity-type radios, and
amount). After submit, the redirected detail page must display the
products list and the computed `nutrition_totals_per_serving`.
"""

from __future__ import annotations

import re

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
    """Pull the first number out of a string like '460 kcal' or '64.7 g'.

    Recipe-totals UI labels each row with both a numeric amount and a
    unit (`api_spec.md` §3.7 — `unit` is denormalised in the response);
    callers compare via `pytest.approx` against pre-computed values.
    """
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    assert match is not None, f"no numeric value found in {text!r}"
    return float(match.group(0))


def _add_recipe_product(
    page: Page,
    *,
    product_name: str,
    quantity_type: str,
    amount: float,
) -> None:
    """Drive the recipe form's product sub-form: search a product,
    select it, choose the quantity_type radio, fill the amount.

    The exact widgetry (autocomplete vs. typeahead, radio vs. select)
    is left to the implementation; this helper matches leniently on
    accessible names so small wording changes do not break the test.
    `implementation_plan.md` §Phase 9 specifies a "ProductPicker"
    autocomplete over `/api/products?scope=search` and a
    "QuantityTypeRadio" component.
    """
    # Open the picker. Implementation may render it as a button on the
    # form or inside an "Add product" affordance — we accept either.
    page.get_by_role("button", name=re.compile(r"add\s+product", re.IGNORECASE)).click()

    # The picker exposes a search input (combobox / searchbox role).
    # `page.expect_response` synchronizes on the search API call so we
    # don't race the React debounce (300 ms per phase 8 conftest).
    search_box = page.get_by_role("combobox").or_(
        page.get_by_role("searchbox")
    ).last
    with page.expect_response(
        lambda r: "/api/products" in r.url
        and "scope=search" in r.url
        and r.status == 200
    ):
        search_box.fill(product_name)

    # Click the matching option from the picker. Implementation may
    # render options as `role=option` (combobox) or as buttons / list
    # items — we match the first element whose text contains the name.
    page.get_by_role("option", name=re.compile(re.escape(product_name))).or_(
        page.get_by_role("button", name=re.compile(re.escape(product_name)))
    ).first.click()

    # Pick the quantity_type. The radio's accessible name is expected
    # to read "weight" / "volume" or the corresponding unit "g" / "ml".
    qty_label = re.compile(
        rf"^(?:{quantity_type}|{'g' if quantity_type == 'weight' else 'ml'})$",
        re.IGNORECASE,
    )
    page.get_by_role("radio", name=qty_label).check()

    # Fill the amount. Multiple amount inputs may be on the page (one
    # per added product); we target the most recently added row by
    # taking the last visible Amount input.
    page.get_by_label(re.compile(r"^amount$", re.IGNORECASE)).last.fill(str(amount))


def test_create_recipe_via_ui_shows_products_and_totals(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids,
    pg_conn,
) -> None:
    """Sign in, create a recipe with two products, and confirm the
    detail page renders both products and the per-serving totals.

    Recipe data uses the §13 worked example so the expected totals
    (Energy 460 kcal, Protein 64.7 g) match the formula's published
    output. Uniquely-named products keep the autocomplete unambiguous
    above the 0.3 similarity threshold.
    """
    user, token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )

    # Seed two products via the API so the picker has something to
    # find. Names contain a unique "Phase9" prefix to comfortably clear
    # `pg_trgm`'s 0.3 similarity threshold without colliding with each
    # other.
    chicken = make_product(
        token=token,
        name="Phase9 Chicken Breast",
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
    rice = make_product(
        token=token,
        name="Phase9 Brown Rice",
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

    _login_via_ui(page, app_base_url, username="alice", password="hunter2pwd")

    # Navigate to the Recipes section. Implementation_plan §Phase 9
    # specifies adding a "Recipes" nav entry to the Layout.
    page.get_by_role("link", name=re.compile(r"recipes", re.IGNORECASE)).first.click()

    # Click the New Recipe affordance. May be a link or a button.
    page.get_by_role("link", name=re.compile(r"new", re.IGNORECASE)).or_(
        page.get_by_role("button", name=re.compile(r"new", re.IGNORECASE))
    ).first.click()

    # Fill the basic fields.
    page.get_by_label(re.compile(r"^name$", re.IGNORECASE)).fill(
        "Worked Example Bowl"
    )

    # Add both recipe-products via the picker.
    _add_recipe_product(
        page,
        product_name="Phase9 Chicken Breast",
        quantity_type="weight",
        amount=200,
    )
    _add_recipe_product(
        page,
        product_name="Phase9 Brown Rice",
        quantity_type="weight",
        amount=100,
    )

    # Submit and capture the create response so we can fish the new
    # recipe id out of it for cross-checks.
    with page.expect_response(
        lambda r: r.url.endswith("/api/recipes")
        and r.request.method == "POST"
        and r.status == 201
    ) as response_info:
        page.get_by_role("button", name=re.compile(r"^save$", re.IGNORECASE)).click()
    created_recipe = response_info.value.json()
    recipe_id = created_recipe["id"]

    # Detail page redirect.
    page.wait_for_url(re.compile(rf"/recipes/{recipe_id}(?:[/?#]|$)"))

    # Recipe name visible.
    expect(page.get_by_text("Worked Example Bowl")).to_be_visible()

    # Both product names appear in the products list.
    expect(page.get_by_text("Phase9 Chicken Breast")).to_be_visible()
    expect(page.get_by_text("Phase9 Brown Rice")).to_be_visible()

    # Totals: per `api_spec.md` §13 worked example,
    # Energy = 165 * 2 + 130 * 1 = 460 kcal;
    # Protein = 31 * 2 + 2.7 * 1 = 64.7 g.
    # The totals are rendered in a small table with a heading like
    # "Totals" / "Per serving" — match leniently and locate rows by
    # nutrition-fact-type name.
    energy_row = page.get_by_role(
        "row", name=re.compile(r"energy", re.IGNORECASE)
    ).first
    energy_text = energy_row.inner_text()
    assert _parse_leading_number(energy_text) == pytest.approx(460.0, rel=1e-3), (
        f"Expected Energy ≈ 460 in totals row, got text={energy_text!r}"
    )
    assert "kcal" in energy_text.lower(), (
        f"Energy unit must be displayed (kcal); got {energy_text!r}"
    )

    protein_row = page.get_by_role(
        "row", name=re.compile(r"protein", re.IGNORECASE)
    ).first
    protein_text = protein_row.inner_text()
    assert _parse_leading_number(protein_text) == pytest.approx(64.7, rel=1e-3), (
        f"Expected Protein ≈ 64.7 in totals row, got text={protein_text!r}"
    )
    assert re.search(r"\bg\b", protein_text.lower()), (
        f"Protein unit must be displayed (g); got {protein_text!r}"
    )

    # DB cross-check: one recipe row owned by alice, two recipe_products
    # rows referencing the seeded products.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, created_by_user_id FROM recipes "
            "WHERE id = %s",
            (recipe_id,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1, f"expected exactly 1 recipe row, got {rows!r}"
    db_id, db_name, db_owner = rows[0]
    assert db_name == "Worked Example Bowl"
    assert db_owner == user["id"], (
        f"recipe must be owned by the logged-in user; got owner={db_owner!r}, "
        f"expected={user['id']!r}"
    )

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT product_id, quantity_type, amount "
            "FROM recipe_products WHERE recipe_id = %s "
            "ORDER BY product_id",
            (recipe_id,),
        )
        rp_rows = cur.fetchall()
    assert len(rp_rows) == 2, (
        f"expected exactly 2 recipe_products rows, got {rp_rows!r}"
    )
    rp_by_product = {row[0]: (row[1], float(row[2])) for row in rp_rows}
    assert rp_by_product[chicken["id"]] == ("weight", 200.0), (
        f"chicken row mismatch: {rp_by_product[chicken['id']]!r}"
    )
    assert rp_by_product[rice["id"]] == ("weight", 100.0), (
        f"rice row mismatch: {rp_by_product[rice['id']]!r}"
    )
