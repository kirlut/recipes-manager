"""Phase-9 totals-match-backend test.

Covers `testing_strategy.md` §5 phase 9
(`test_recipe_totals_match_backend.py` — "same fixture as phase-5
totals test, but verified through the UI: read displayed totals,
compare against `pytest.approx`-expected values").

The recipe is seeded **via the API** (not the UI) to keep this test
focused on the *display* of totals, not the creation flow — which is
the job of `test_create_recipe.py`. Then the UI is opened at
`/recipes/{id}` and the rendered totals are compared both against
the published worked-example numbers (Energy 460, Protein 64.7) and
against the backend's own `nutrition_totals_per_serving` payload, to
prove the frontend is rendering exactly what the backend computed.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.helpers import api as api_helpers


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


def test_recipe_detail_totals_match_backend_and_worked_example(
    page: Page,
    app_base_url: str,
    api_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids,
) -> None:
    """Worked example fixture from `api_spec.md` §13:

    Recipe: 200g of P (Energy 165, Protein 31) + 100g of Q (Energy
    130, Protein 2.7) → Energy = 460 kcal, Protein = 64.7 g per
    serving.

    The UI's displayed numbers must match both the published values
    and the values returned by `GET /api/recipes/{id}`.
    """
    _user, token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )

    chicken = make_product(
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
    rice = make_product(
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

    recipe = make_recipe(
        token=token,
        name="Worked Example Bowl",
        products=[
            {
                "product_id": chicken["id"],
                "quantity_type": "weight",
                "amount": 200,
            },
            {
                "product_id": rice["id"],
                "quantity_type": "weight",
                "amount": 100,
            },
        ],
    )
    recipe_id = recipe["id"]

    # Pull the canonical backend totals — what the UI must render.
    fetched = api_helpers.recipes_get(
        api_base_url, token=token, recipe_id=recipe_id
    )
    assert fetched.status_code == 200, fetched.text
    backend_totals_by_name: dict[str, float] = {
        t["nutrition_fact_name"]: float(t["amount"])
        for t in fetched.json()["nutrition_totals_per_serving"]
    }
    assert "Energy" in backend_totals_by_name, (
        f"backend response missing Energy: {backend_totals_by_name!r}"
    )
    assert "Protein" in backend_totals_by_name, (
        f"backend response missing Protein: {backend_totals_by_name!r}"
    )
    # Sanity: the published worked-example numbers — phase-5 already
    # verifies these against the formula; we re-state them here so a
    # mismatch surfaces clearly in the phase-9 failure output too.
    assert backend_totals_by_name["Energy"] == pytest.approx(460.0, rel=1e-3)
    assert backend_totals_by_name["Protein"] == pytest.approx(64.7, rel=1e-3)

    # Open the recipe detail page through the UI.
    _login_via_ui(page, app_base_url, username="alice", password="hunter2pwd")
    page.goto(f"{app_base_url}/recipes/{recipe_id}")

    expect(page.get_by_text("Worked Example Bowl")).to_be_visible()

    # Read the displayed Energy and Protein rows. Implementation
    # renders the totals as a `<table>` per `implementation_plan.md`
    # §Phase 9 ("rendered as a small table with units"); we locate
    # rows by their leading nutrition-fact-type name.
    energy_row = page.get_by_role(
        "row", name=re.compile(r"energy", re.IGNORECASE)
    ).first
    energy_text = energy_row.inner_text()
    energy_ui_value = _parse_leading_number(energy_text)
    assert "kcal" in energy_text.lower(), (
        f"Energy row must show its unit (kcal); got {energy_text!r}"
    )

    protein_row = page.get_by_role(
        "row", name=re.compile(r"protein", re.IGNORECASE)
    ).first
    protein_text = protein_row.inner_text()
    protein_ui_value = _parse_leading_number(protein_text)
    assert re.search(r"\bg\b", protein_text.lower()), (
        f"Protein row must show its unit (g); got {protein_text!r}"
    )

    # The UI numbers must match the backend numbers exactly (modulo
    # float-display rounding, which `pytest.approx(rel=1e-3)` tolerates).
    assert energy_ui_value == pytest.approx(
        backend_totals_by_name["Energy"], rel=1e-3
    ), (
        f"UI Energy {energy_ui_value} must match backend "
        f"{backend_totals_by_name['Energy']}"
    )
    assert protein_ui_value == pytest.approx(
        backend_totals_by_name["Protein"], rel=1e-3
    ), (
        f"UI Protein {protein_ui_value} must match backend "
        f"{backend_totals_by_name['Protein']}"
    )
