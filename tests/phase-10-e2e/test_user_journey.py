"""Phase-10 final E2E user journey.

Covers `testing_strategy.md` §5 phase 10 (`test_user_journey.py` — a
single ~30-step Playwright test that wires together every layer of the
system: register → product authoring with image upload → recipe
authoring → cross-user search/star/copy/edit → multi-recipe shopping
list with numeric assertions).

This phase introduces no new feature code (`implementation_plan.md`
§Phase 10). Any failure here must be fixed in the relevant earlier
phase, not by patching this test.

### Journey shape

Step numbers match the testing-strategy enumeration. Two users (Alice =
A, Bob = B). Products use an `E2E ` prefix so the `pg_trgm` 0.3
similarity gate is comfortably cleared and the alphabetical sort over
shopping-list rows is predictable (Brown < Chicken < Quinoa).

| Owner | Product               | Facts                                  | Image          |
|-------|-----------------------|----------------------------------------|----------------|
| Alice | E2E Chicken Breast P1 | weight: Energy 165, Protein 31         | uploaded JPEG  |
| Alice | E2E Brown Rice P2     | weight: Energy 130, Net Carbs 28       | none           |
| Alice | E2E Olive Oil P3      | volume: Energy 884, Fat 100            | none           |
| Bob   | E2E Quinoa P4         | weight: Energy 120, Protein 4          | none           |

Recipes:
- Alice's R1 = 200g P1 + 150g P2 (per-serving totals — `api_spec.md` §13:
  amount × (a/100) — Energy 525 kcal, Protein 62 g, Net Carbs 42 g).
- Bob's R2 = R1.copy(), then swap P2 → P4 (per-serving Energy 510 kcal,
  Protein 68 g).

Shopping list `POST /shopping-list { items: [{R1, 1}, {R2, 3}] }`,
sorted by `(product_name ASC, quantity_type ASC)`:
- E2E Brown Rice    weight g  150  (= 150 × 1 from R1)
- E2E Chicken Breast weight g 800  (= 200 × 1 + 200 × 3)
- E2E Quinoa        weight g  450  (= 150 × 3 from R2)

(Per `api_spec.md` §9.1, B can include R1 because B starred it in step
8; R2 is owned outright. The journey exercises both branches of the
owned-or-starred shopping-list authz rule.)
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, Response, expect

from tests.helpers.images import JPEG_BYTES


# ---------------------------------------------------------------------------
# Lenient locator regexes. Implementations may render labels with minor
# wording differences ("Logout" vs. "Log out", "Save" vs. "Create",
# etc.) — every UI assertion here matches case-insensitively.
# ---------------------------------------------------------------------------

LOGOUT_NAME_RE = re.compile(r"log\s*out", re.IGNORECASE)
NEW_RE = re.compile(r"new", re.IGNORECASE)
SAVE_RE = re.compile(r"^(?:save|create|update|submit)$", re.IGNORECASE)
ADD_PRODUCT_RE = re.compile(r"add\s+product", re.IGNORECASE)
ADD_WEIGHT_FACT_RE = re.compile(r"add\s+weight\s+fact", re.IGNORECASE)
ADD_VOLUME_FACT_RE = re.compile(r"add\s+volume\s+fact", re.IGNORECASE)
ADD_RECIPE_RE = re.compile(r"add\s+recipe", re.IGNORECASE)
COMPUTE_RE = re.compile(r"compute|generate", re.IGNORECASE)
COPY_RE = re.compile(r"^copy$", re.IGNORECASE)
EDIT_RE = re.compile(r"^edit$", re.IGNORECASE)
STAR_RE = re.compile(r"^(?:star|unstar|favou?rite)$", re.IGNORECASE)
REMOVE_RE = re.compile(r"^(?:remove|delete|x)$", re.IGNORECASE)
AMOUNT_RE = re.compile(r"^amount$", re.IGNORECASE)
NAME_RE = re.compile(r"^name$", re.IGNORECASE)
SERVINGS_RE = re.compile(r"servings?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Generic UI helpers (kept inline rather than imported from another phase
# folder per `testing_strategy.md` §3 — each phase must be
# self-contained).
# ---------------------------------------------------------------------------


def _parse_leading_number(text: str) -> float:
    """Pull the first number from a string like '460 kcal' / '64.7 g'."""
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    assert match is not None, f"no numeric value found in {text!r}"
    return float(match.group(0))


def _row_shows_unit(row_text: str, unit: str) -> bool:
    """Match unit (`g` / `ml` / `kcal`) as a standalone token."""
    return re.search(rf"\b{re.escape(unit)}\b", row_text) is not None


def _strip_name(row_text: str, *names: str) -> str:
    """Remove product/fact-type names from row text so digits in the
    name (none today, but cheap insurance for future fixtures) don't
    fool `_parse_leading_number`.
    """
    out = row_text
    for n in names:
        out = out.replace(n, "")
    return out


def _register_via_ui(
    page: Page,
    app_base_url: str,
    *,
    username: str,
    password: str,
    full_name: str,
) -> None:
    """Drive the /register form. Implementation may either auto-login
    + redirect or send the user to /login — both are acceptable per
    `api_spec.md` §2.2 (register returns 201 without a token). We log
    in explicitly afterwards if needed so the assertions downstream
    have a known authed state.
    """
    page.goto(f"{app_base_url}/register")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_label("Full name").fill(full_name)
    page.get_by_role("button", name="Register").click()
    if "/login" in page.url or "/register" in page.url:
        _login_via_ui(page, app_base_url, username=username, password=password)
    page.wait_for_url(lambda url: "/login" not in url and "/register" not in url)
    expect(page.get_by_text(username)).to_be_visible()


def _login_via_ui(
    page: Page, app_base_url: str, *, username: str, password: str
) -> None:
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)


def _logout_via_ui(page: Page) -> None:
    """Click the Logout affordance. May be a top-level button or a
    `role=menuitem` inside a user menu — try both shapes per the
    phase-8 `test_register_login.py` precedent.
    """
    logout = page.get_by_role("button", name=LOGOUT_NAME_RE)
    if logout.count() == 0 or not logout.first.is_visible():
        logout = page.get_by_role("menuitem", name=LOGOUT_NAME_RE)
        if logout.count() == 0 or not logout.first.is_visible():
            # Open a probable user menu: any button whose accessible name
            # is a known username. Use the first visible one — the menu
            # only exposes the current user's username.
            for candidate in ("alice", "bob"):
                btn = page.get_by_role("button", name=candidate)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    break
            logout = page.get_by_role("menuitem", name=LOGOUT_NAME_RE)
    logout.first.click()
    page.wait_for_url(lambda url: url.rstrip("/").endswith("/login"))


def _add_recipe_product(
    page: Page,
    *,
    product_name: str,
    quantity_type: str,
    amount: float,
) -> None:
    """Drive the recipe form's product sub-form. Mirrors the helper in
    `tests/phase-9-frontend-recipes-and-shopping/test_create_recipe.py`.

    `implementation_plan.md` §Phase 9 mandates a "ProductPicker"
    autocomplete over `/api/products?scope=search` and a
    "QuantityTypeRadio" for choosing weight/volume.
    """
    page.get_by_role("button", name=ADD_PRODUCT_RE).click()

    search_box = page.get_by_role("combobox").or_(
        page.get_by_role("searchbox")
    ).last
    with page.expect_response(
        lambda r: "/api/products" in r.url
        and "scope=search" in r.url
        and r.status == 200
    ):
        search_box.fill(product_name)

    page.get_by_role("option", name=re.compile(re.escape(product_name))).or_(
        page.get_by_role("button", name=re.compile(re.escape(product_name)))
    ).first.click()

    qty_label = re.compile(
        rf"^(?:{quantity_type}|{'g' if quantity_type == 'weight' else 'ml'})$",
        re.IGNORECASE,
    )
    page.get_by_role("radio", name=qty_label).check()
    page.get_by_label(AMOUNT_RE).last.fill(str(amount))


def _select_recipe_in_picker(
    page: Page,
    *,
    recipe_name: str,
    servings: float,
) -> None:
    """Open the recipe-picker modal, click the recipe by name, set
    its servings input. Mirrors the helper in
    `tests/phase-9-frontend-recipes-and-shopping/test_shopping_list.py`.
    """
    page.get_by_role("button", name=ADD_RECIPE_RE).click()
    page.get_by_role("button", name=re.compile(re.escape(recipe_name))).or_(
        page.get_by_role("option", name=re.compile(re.escape(recipe_name)))
    ).first.click()
    if servings != 1:
        page.get_by_label(SERVINGS_RE).last.fill(str(servings))


# ---------------------------------------------------------------------------
# Energy / Protein / Net Carbs row matching for recipe-detail totals.
# Locating by `role=row` plus the fact-type name lets the assertion
# survive layout / class changes — phase-9 `test_create_recipe.py` uses
# the same pattern.
# ---------------------------------------------------------------------------


def _assert_total_row(
    page: Page,
    *,
    fact_name: str,
    expected_amount: float,
    expected_unit: str,
) -> None:
    row = page.get_by_role("row", name=re.compile(fact_name, re.IGNORECASE)).first
    expect(row).to_be_visible()
    text = row.inner_text()
    stripped = _strip_name(text, fact_name)
    assert _parse_leading_number(stripped) == pytest.approx(
        expected_amount, rel=1e-3
    ), (
        f"{fact_name} row expected ≈ {expected_amount}, got text={text!r}"
    )
    assert _row_shows_unit(text, expected_unit), (
        f"{fact_name} row must show unit {expected_unit!r}, got {text!r}"
    )


# ---------------------------------------------------------------------------
# The journey.
# ---------------------------------------------------------------------------


# Generous timeout: this single test creates products, recipes, copies,
# edits and computes a shopping list. Even on slow CI hardware the
# Playwright-default 30 s isn't enough for the ~30-step path. The
# pytest-default per-test timeout is "no limit" but adding a marker
# would require pytest-timeout; we instead lengthen Playwright's
# action / navigation timeouts inside the test.


def test_user_journey_register_through_shopping_list(
    page: Page,
    app_base_url: str,
    api_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids: dict[str, int],
    pg_conn,
) -> None:
    """End-to-end multi-user journey.

    See module docstring for the worked numbers. Each step has a brief
    inline comment cross-referencing `testing_strategy.md` §5 phase 10.
    """
    # Lengthen Playwright's default action/navigation timeout — the
    # journey is long; one slow step shouldn't fail the whole run.
    page.set_default_timeout(15_000)
    page.set_default_navigation_timeout(15_000)

    # ------------------------------------------------------------------
    # Step 1. Register Alice via the UI.
    # ------------------------------------------------------------------
    _register_via_ui(
        page,
        app_base_url,
        username="alice",
        password="hunter2pwd",
        full_name="Alice Smith",
    )
    # API sanity: the user row exists and has the captured token.
    alice_token = page.evaluate("() => window.localStorage.getItem('auth_token')")
    assert alice_token, "auth_token must be set in localStorage after register/login"
    me = httpx.get(
        f"{api_base_url}/auth/me",
        headers={"Authorization": f"Bearer {alice_token}"},
        timeout=10.0,
    )
    assert me.status_code == 200, f"GET /auth/me failed: {me.status_code} {me.text!r}"
    alice = me.json()
    assert alice["username"] == "alice"

    # ------------------------------------------------------------------
    # Step 2a. Alice creates P1 ("E2E Chicken Breast") via the UI form,
    # uploading a JPEG. This is the journey's only product-form pass —
    # P2/P3 are seeded via API to keep the journey under ~30 steps
    # (the form flow is exhaustively covered by phase-8
    # `test_create_product.py`).
    # ------------------------------------------------------------------
    page.get_by_role("link", name="My Products").click()
    page.get_by_role("link", name=re.compile(r"new\s+product", re.IGNORECASE)).or_(
        page.get_by_role("button", name=re.compile(r"new\s+product", re.IGNORECASE))
    ).first.click()
    page.wait_for_url(re.compile(r"/products/new(?:[/?#]|$)"))

    page.get_by_label(NAME_RE).fill("E2E Chicken Breast")

    # Image upload — Playwright FilePayload shape (see phase-8 test).
    page.locator('input[type="file"]').set_input_files(
        files=[
            {
                "name": "chicken.jpg",
                "mimeType": "image/jpeg",
                "buffer": JPEG_BYTES,
            }
        ]
    )

    # Two weight nutrition facts: Energy 165, Protein 31. Implementation
    # surfaces two collapsible sub-forms (weight, volume) per
    # `implementation_plan.md` §Phase 8.
    page.get_by_role("button", name=ADD_WEIGHT_FACT_RE).click()
    page.get_by_label(re.compile(r"nutrition\s+fact", re.IGNORECASE)).last.select_option(
        label="Energy"
    )
    page.get_by_label(AMOUNT_RE).last.fill("165")

    page.get_by_role("button", name=ADD_WEIGHT_FACT_RE).click()
    page.get_by_label(re.compile(r"nutrition\s+fact", re.IGNORECASE)).last.select_option(
        label="Protein"
    )
    page.get_by_label(AMOUNT_RE).last.fill("31")

    with page.expect_response(
        lambda r: r.url.endswith("/api/products")
        and r.request.method == "POST"
        and r.status == 201
    ) as p1_resp_info:
        page.get_by_role("button", name=SAVE_RE).click()
    p1 = p1_resp_info.value.json()
    p1_id = p1["id"]

    page.wait_for_url(re.compile(rf"/products/{p1_id}(?:[/?#]|$)"))
    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()

    # Image rendering check — locate the product image, fetch its src
    # via the public /uploads route (no auth required per
    # `api_spec.md` §10.2), assert the bytes round-trip.
    img_src = page.locator("img").filter(has_not_text="").first.get_attribute("src")
    assert img_src and "/uploads/" in img_src, (
        f"product detail must render an <img src=...uploads/...>, got {img_src!r}"
    )
    img_url = img_src if img_src.startswith("http") else f"{app_base_url}{img_src}"
    img_resp = httpx.get(img_url, timeout=10.0)
    assert img_resp.status_code == 200, (
        f"GET {img_url!r} via nginx /uploads failed: {img_resp.status_code}"
    )
    assert img_resp.content == JPEG_BYTES, (
        "uploaded JPEG bytes must round-trip identically through nginx /uploads"
    )

    # ------------------------------------------------------------------
    # Step 2b. Seed P2 + P3 via the API for speed.
    # ------------------------------------------------------------------
    p2 = make_product(
        token=alice_token,
        name="E2E Brown Rice",
        nutrition_facts=[
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
    )
    p3 = make_product(
        token=alice_token,
        name="E2E Olive Oil",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "volume",
                "amount": 884,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Fat"],
                "quantity_type": "volume",
                "amount": 100,
            },
        ],
    )

    # My Products tab should list all three products. Re-open the page
    # so the React Query cache picks up the seeded rows.
    page.get_by_role("link", name="My Products").click()
    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()
    expect(page.get_by_text("E2E Brown Rice")).to_be_visible()
    expect(page.get_by_text("E2E Olive Oil")).to_be_visible()

    # ------------------------------------------------------------------
    # Step 3. Alice creates recipe R1 = 200g P1 + 150g P2 via the UI.
    # On the detail page, assert the products + the per-serving totals.
    # ------------------------------------------------------------------
    page.get_by_role("link", name=re.compile(r"recipes", re.IGNORECASE)).first.click()
    page.get_by_role("link", name=NEW_RE).or_(
        page.get_by_role("button", name=NEW_RE)
    ).first.click()
    page.wait_for_url(re.compile(r"/recipes/new(?:[/?#]|$)"))

    page.get_by_label(NAME_RE).fill("Alice's Bowl")
    _add_recipe_product(
        page,
        product_name="E2E Chicken Breast",
        quantity_type="weight",
        amount=200,
    )
    _add_recipe_product(
        page,
        product_name="E2E Brown Rice",
        quantity_type="weight",
        amount=150,
    )

    with page.expect_response(
        lambda r: r.url.endswith("/api/recipes")
        and r.request.method == "POST"
        and r.status == 201
    ) as r1_resp_info:
        page.get_by_role("button", name=SAVE_RE).click()
    r1 = r1_resp_info.value.json()
    r1_id = r1["id"]
    page.wait_for_url(re.compile(rf"/recipes/{r1_id}(?:[/?#]|$)"))

    expect(page.get_by_text("Alice's Bowl")).to_be_visible()
    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()
    expect(page.get_by_text("E2E Brown Rice")).to_be_visible()

    # Per-serving totals (api_spec §13: amount × (a/100)):
    #   Energy = 165·2 + 130·1.5 = 330 + 195 = 525 kcal
    #   Protein = 31·2 + 0       = 62 g
    #   Net Carbs = 0 + 28·1.5   = 42 g
    _assert_total_row(page, fact_name="Energy", expected_amount=525.0, expected_unit="kcal")
    _assert_total_row(page, fact_name="Protein", expected_amount=62.0, expected_unit="g")
    _assert_total_row(page, fact_name="Net Carbs", expected_amount=42.0, expected_unit="g")

    # DB cross-check on R1 ownership + product rows.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT created_by_user_id FROM recipes WHERE id = %s", (r1_id,)
        )
        owner_row = cur.fetchone()
    assert owner_row is not None and owner_row[0] == alice["id"], (
        f"R1 must be owned by alice (id={alice['id']}), got {owner_row!r}"
    )

    # ------------------------------------------------------------------
    # Step 4. Alice logs out; Bob registers via the UI.
    # ------------------------------------------------------------------
    _logout_via_ui(page)
    assert page.evaluate("() => window.localStorage.getItem('auth_token')") is None

    _register_via_ui(
        page,
        app_base_url,
        username="bob",
        password="hunter2pwd",
        full_name="Bob Jones",
    )
    bob_token = page.evaluate("() => window.localStorage.getItem('auth_token')")
    assert bob_token and bob_token != alice_token, (
        "bob's token must be present and distinct from alice's"
    )
    me_b = httpx.get(
        f"{api_base_url}/auth/me",
        headers={"Authorization": f"Bearer {bob_token}"},
        timeout=10.0,
    )
    assert me_b.status_code == 200
    bob = me_b.json()
    assert bob["username"] == "bob" and bob["id"] != alice["id"]

    # ------------------------------------------------------------------
    # Step 5. Bob searches for one of Alice's products and stars it.
    # Asserts: Search tab is reachable, results render, star action
    # round-trips through `PUT /api/products/{id}/star` (204), and
    # "My Starred Products" reflects it.
    # ------------------------------------------------------------------
    page.get_by_role("link", name="My Products").click()

    # Click the Search tab. Implementations may render it as a tab
    # button, link, or a select option — match by accessible name.
    page.get_by_role("tab", name=re.compile(r"search", re.IGNORECASE)).or_(
        page.get_by_role("button", name=re.compile(r"^search$", re.IGNORECASE))
    ).or_(
        page.get_by_role("link", name=re.compile(r"^search$", re.IGNORECASE))
    ).first.click()

    search_box = page.get_by_role("searchbox").or_(
        page.get_by_role("textbox", name=re.compile(r"search", re.IGNORECASE))
    ).first
    with page.expect_response(
        lambda r: "/api/products" in r.url
        and "scope=search" in r.url
        and r.status == 200
    ):
        search_box.fill("E2E Chicken")

    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()
    page.get_by_text("E2E Chicken Breast").first.click()
    page.wait_for_url(re.compile(rf"/products/{p1_id}(?:[/?#]|$)"))

    # Star the product. Lenient name match — implementation may render
    # the toggle as Star / Favourite / a glyph button; the most common
    # accessible name is "Star".
    with page.expect_response(
        lambda r: re.search(rf"/api/products/{p1_id}/star$", r.url) is not None
        and r.request.method == "PUT"
        and r.status == 204
    ):
        page.get_by_role("button", name=STAR_RE).first.click()

    # Switch to "My Starred Products"; P1 must be visible.
    page.get_by_role("link", name="My Products").click()
    page.get_by_role("tab", name=re.compile(r"starred", re.IGNORECASE)).or_(
        page.get_by_role("button", name=re.compile(r"starred", re.IGNORECASE))
    ).or_(
        page.get_by_role("link", name=re.compile(r"starred", re.IGNORECASE))
    ).first.click()
    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()

    # ------------------------------------------------------------------
    # Step 6. Bob copies recipe R1 → R2 via the UI. Assertions:
    # - Non-owner sees Copy, not Edit (api_spec §15).
    # - POST /api/recipes/{R1.id}/copy returns 201.
    # - R2's detail mirrors R1's products + totals.
    # ------------------------------------------------------------------
    page.get_by_role("link", name=re.compile(r"recipes", re.IGNORECASE)).first.click()
    page.get_by_role("tab", name=re.compile(r"search", re.IGNORECASE)).or_(
        page.get_by_role("button", name=re.compile(r"^search$", re.IGNORECASE))
    ).or_(
        page.get_by_role("link", name=re.compile(r"^search$", re.IGNORECASE))
    ).first.click()

    rsearch = page.get_by_role("searchbox").or_(
        page.get_by_role("textbox", name=re.compile(r"search", re.IGNORECASE))
    ).first
    with page.expect_response(
        lambda r: "/api/recipes" in r.url
        and "scope=search" in r.url
        and r.status == 200
    ):
        rsearch.fill("Alice's Bowl")

    page.get_by_text("Alice's Bowl").first.click()
    page.wait_for_url(re.compile(rf"/recipes/{r1_id}(?:[/?#]|$)"))

    # Edit must be absent (non-owner per api_spec §15); Copy present.
    expect(page.get_by_role("button", name=EDIT_RE)).to_have_count(0)
    expect(page.get_by_role("link", name=EDIT_RE)).to_have_count(0)
    copy_button = page.get_by_role("button", name=COPY_RE).or_(
        page.get_by_role("link", name=COPY_RE)
    ).first
    expect(copy_button).to_be_visible()

    with page.expect_response(
        lambda r: re.search(rf"/api/recipes/{r1_id}/copy$", r.url) is not None
        and r.request.method == "POST"
        and r.status == 201
    ) as r2_resp_info:
        copy_button.click()
    r2 = r2_resp_info.value.json()
    r2_id = r2["id"]
    assert r2_id != r1_id

    page.wait_for_url(re.compile(rf"/recipes/{r2_id}(?:[/?#]|$)"))
    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()
    expect(page.get_by_text("E2E Brown Rice")).to_be_visible()
    # R2 starts as a copy of R1 — same per-serving totals.
    _assert_total_row(page, fact_name="Energy", expected_amount=525.0, expected_unit="kcal")
    _assert_total_row(page, fact_name="Protein", expected_amount=62.0, expected_unit="g")

    # DB cross-check: R2 owned by bob, distinct row from R1.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT created_by_user_id FROM recipes WHERE id = %s", (r2_id,)
        )
        r2_owner = cur.fetchone()
    assert r2_owner is not None and r2_owner[0] == bob["id"], (
        f"R2 must be owned by bob (id={bob['id']}), got {r2_owner!r}"
    )

    # ------------------------------------------------------------------
    # Step 7a. Bob creates P4 ("E2E Quinoa") via API — the form path
    # is already covered by the P1 step above.
    # ------------------------------------------------------------------
    p4 = make_product(
        token=bob_token,
        name="E2E Quinoa",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 120,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 4,
            },
        ],
    )

    # ------------------------------------------------------------------
    # Step 7b. Bob edits R2 — remove the P2 row, add P4 at 150g (same
    # amount P2 had so the swap is symmetric). Final R2 = 200g P1 +
    # 150g P4.
    # ------------------------------------------------------------------
    edit_action = (
        page.get_by_role("button", name=EDIT_RE)
        .or_(page.get_by_role("link", name=EDIT_RE))
        .first
    )
    expect(edit_action).to_be_visible()
    edit_action.click()
    page.wait_for_url(re.compile(rf"/recipes/{r2_id}/edit(?:[/?#]|$)"))

    # Locate the row containing "E2E Brown Rice" and click its Remove
    # control. Implementation may attach the remove button per-row;
    # we scope by the row containing the product name.
    rice_row = page.locator(
        ":is(li, tr, div):has-text('E2E Brown Rice')"
    ).filter(has=page.get_by_role("button", name=REMOVE_RE)).first
    rice_remove = rice_row.get_by_role("button", name=REMOVE_RE).first
    rice_remove.click()
    # The product name should disappear from the form area after removal.
    expect(page.get_by_text("E2E Brown Rice")).to_have_count(0)

    _add_recipe_product(
        page, product_name="E2E Quinoa", quantity_type="weight", amount=150
    )

    with page.expect_response(
        lambda r: re.search(rf"/api/recipes/{r2_id}$", r.url) is not None
        and r.request.method == "PUT"
        and r.status == 200
    ):
        page.get_by_role("button", name=SAVE_RE).click()

    page.wait_for_url(re.compile(rf"/recipes/{r2_id}(?:[/?#]|$)"))
    expect(page.get_by_text("E2E Chicken Breast")).to_be_visible()
    expect(page.get_by_text("E2E Quinoa")).to_be_visible()
    expect(page.get_by_text("E2E Brown Rice")).to_have_count(0)

    # New per-serving totals after the swap:
    #   Energy = 165·2 + 120·1.5 = 330 + 180 = 510 kcal
    #   Protein = 31·2 + 4·1.5   = 62 + 6   = 68 g
    _assert_total_row(page, fact_name="Energy", expected_amount=510.0, expected_unit="kcal")
    _assert_total_row(page, fact_name="Protein", expected_amount=68.0, expected_unit="g")

    # ------------------------------------------------------------------
    # Step 8. Bob stars Alice's R1 so the shopping list can include it.
    # `api_spec.md` §9.1 requires recipes in `POST /shopping-list` to
    # be owned-or-starred by the caller; without this step the journey
    # would fall back to "R2 only".
    # ------------------------------------------------------------------
    page.goto(f"{app_base_url}/recipes/{r1_id}")
    with page.expect_response(
        lambda r: re.search(rf"/api/recipes/{r1_id}/star$", r.url) is not None
        and r.request.method == "PUT"
        and r.status == 204
    ):
        page.get_by_role("button", name=STAR_RE).first.click()

    # ------------------------------------------------------------------
    # Step 9. Bob opens Shopping List, selects R2 with 3 servings and
    # R1 with 1 serving, computes. Captures the API response and asserts
    # totals + sort order.
    # ------------------------------------------------------------------
    page.get_by_role("link", name=re.compile(r"shopping", re.IGNORECASE)).first.click()
    page.wait_for_url(re.compile(r"/shopping-list(?:[/?#]|$)"))

    _select_recipe_in_picker(page, recipe_name="Alice's Bowl", servings=1)
    _select_recipe_in_picker(
        page,
        # R2's name was inherited from R1 by the copy. `api_spec.md`
        # §7.5 doesn't mandate a renamed copy, so the picker shows the
        # name verbatim. Match leniently in case the implementation
        # appends a "(copy)" suffix.
        recipe_name="Alice's Bowl",
        servings=3,
    )

    # If the implementation appends "(copy)" to R2's name we'd end up
    # adding R1 twice instead of R1 + R2. Detect that case via the API
    # response: there must be exactly two distinct recipe selections,
    # which will surface as 3 distinct (product, qty_type) rows. If the
    # selection ended up as R1 + R1 the response would have only 2 rows
    # (no Quinoa). The assertion on `len(api_items) == 3` below catches
    # that path.

    with page.expect_response(
        lambda r: r.url.endswith("/api/shopping-list")
        and r.request.method == "POST"
        and r.status == 200
    ) as sl_resp_info:
        page.get_by_role("button", name=COMPUTE_RE).first.click()
    sl_resp: Response = sl_resp_info.value
    api_items: list[dict[str, Any]] = sl_resp.json()["items"]

    # Expected (sorted by product_name ASC, quantity_type ASC):
    expected_rows = [
        ("E2E Brown Rice", "weight", "g", 150.0),
        ("E2E Chicken Breast", "weight", "g", 800.0),
        ("E2E Quinoa", "weight", "g", 450.0),
    ]
    assert len(api_items) == 3, (
        f"shopping-list must aggregate to exactly 3 rows for this fixture, "
        f"got {len(api_items)}: {api_items!r}"
    )
    api_keys = [(row["product_name"], row["quantity_type"]) for row in api_items]
    expected_keys = [(name, qty) for name, qty, _u, _t in expected_rows]
    assert api_keys == expected_keys, (
        f"shopping-list sort-order regression: "
        f"got {api_keys!r}, expected {expected_keys!r}"
    )
    for (name, qty, unit, total), row in zip(expected_rows, api_items, strict=True):
        assert row["unit"] == unit, f"{name} {qty}: unit mismatch in {row!r}"
        assert float(row["total_amount"]) == pytest.approx(total), (
            f"{name} {qty}: total_amount mismatch in {row!r}"
        )

    # ------------------------------------------------------------------
    # Step 10. UI assertions on the displayed shopping-list table.
    # ------------------------------------------------------------------
    for product_name, quantity_type, unit, total in expected_rows:
        row = page.get_by_role(
            "row", name=re.compile(re.escape(product_name))
        ).first
        expect(row).to_be_visible()
        text = row.inner_text()
        stripped = _strip_name(text, product_name)
        assert _parse_leading_number(stripped) == pytest.approx(total), (
            f"row {product_name!r} expected amount ≈ {total}, got text={text!r}"
        )
        assert quantity_type.lower() in text.lower(), (
            f"row {product_name!r} must show quantity_type "
            f"{quantity_type!r}, got {text!r}"
        )
        assert _row_shows_unit(text, unit), (
            f"row {product_name!r} must show unit {unit!r}, got {text!r}"
        )

    # Final DB cross-check: P3 remains owned by Alice (proves we didn't
    # accidentally write to it from Bob's session — Alice never used P3
    # in any recipe), and the four products / two recipes we created
    # exist exactly as expected.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT name, created_by_user_id FROM products "
            "WHERE name LIKE 'E2E %' ORDER BY name"
        )
        product_rows = cur.fetchall()
    assert product_rows == [
        ("E2E Brown Rice", alice["id"]),
        ("E2E Chicken Breast", alice["id"]),
        ("E2E Olive Oil", alice["id"]),
        ("E2E Quinoa", bob["id"]),
    ], f"final products state mismatch: {product_rows!r}"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, created_by_user_id FROM recipes ORDER BY id"
        )
        recipe_rows = cur.fetchall()
    assert recipe_rows == [
        (r1_id, alice["id"]),
        (r2_id, bob["id"]),
    ], f"final recipes state mismatch: {recipe_rows!r}"

    # Reference unused locals so the linter sees them as part of the
    # journey wiring (each one represents a step's outcome we keep
    # available for debugging if assertions fail mid-journey).
    del p2, p3, p4
