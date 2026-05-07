"""Phase-9 copy-another-users-recipe flow via the UI.

Covers `testing_strategy.md` §5 phase 9 (`test_copy_recipe.py` —
"copy another user's recipe, edit the copy").

Mirrors `tests/phase-8-frontend-products/test_copy_other_users_product.py`
for the recipes endpoint. A non-owner viewing another user's recipe
must see Copy and not Edit (`api_spec.md` §7.3 — only the owner can
PUT/DELETE; UI must not present Edit). After copying, the new recipe
is owned by the caller (`api_spec.md` §7.5) and they can edit it.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login_via_ui(
    page: Page, app_base_url: str, *, username: str, password: str
) -> None:
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)


def test_non_owner_sees_copy_not_edit_then_copy_and_edit_succeed(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    make_recipe,
    nutrition_fact_ids,
    pg_conn,
) -> None:
    """End-to-end: alice creates a recipe, bob copies it via the UI,
    then renames the copy via the Edit page. Both create/edit calls
    are observed at the network layer; the resulting DB state is
    cross-checked.

    All test-strategy guarantees this single function must enforce:
    - Non-owner sees Copy (visible) and Edit (absent) on the detail
      page.
    - POST /recipes/{id}/copy returns 201 and the new recipe lands in
      bob's "My Recipes".
    - PUT /recipes/{copyId} returns 200 and the new name renders.
    - Database has two recipes (alice + bob), one of each, with the
      bob-owned name updated to the renamed value and alice's name
      unchanged.
    """
    alice, alice_token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )
    bob, _bob_token = make_user(
        username="bob", password="hunter2pwd", full_name="Bob Jones"
    )

    # Alice seeds a product + recipe via the API (we test the *copy*
    # flow, not creation — that's `test_create_recipe.py`).
    chicken = make_product(
        token=alice_token,
        name="Phase9 Chicken Breast",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 165,
            }
        ],
    )
    alice_recipe = make_recipe(
        token=alice_token,
        name="Alice's Bowl",
        products=[
            {
                "product_id": chicken["id"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    )

    # Bob logs in, navigates straight to alice's recipe detail.
    _login_via_ui(page, app_base_url, username="bob", password="hunter2pwd")
    page.goto(f"{app_base_url}/recipes/{alice_recipe['id']}")

    expect(page.get_by_text("Alice's Bowl")).to_be_visible()

    # Edit must NOT be available to a non-owner — neither as a link
    # nor as a button — per `api_spec.md` §7.3.
    expect(page.get_by_role("link", name=re.compile(r"^edit$", re.IGNORECASE))).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile(r"^edit$", re.IGNORECASE))).to_have_count(0)

    # Copy MUST be available.
    copy_button = page.get_by_role(
        "button", name=re.compile(r"^copy$", re.IGNORECASE)
    )
    expect(copy_button).to_be_visible()

    # Click Copy and capture the response so we can pull the new id.
    with page.expect_response(
        lambda r: r.url.endswith(f"/api/recipes/{alice_recipe['id']}/copy")
        and r.request.method == "POST"
        and r.status == 201
    ) as copy_response_info:
        copy_button.click()
    copy_body = copy_response_info.value.json()
    copy_id = copy_body["id"]
    assert copy_id != alice_recipe["id"], (
        f"copy must produce a NEW id; got {copy_id} == source id"
    )

    # Bob's My Recipes should now contain the copied recipe (same name).
    page.get_by_role("link", name=re.compile(r"recipes", re.IGNORECASE)).first.click()
    expect(page.get_by_text("Alice's Bowl")).to_be_visible()

    # Open Bob's copy and click Edit.
    page.goto(f"{app_base_url}/recipes/{copy_id}")
    expect(page.get_by_text("Alice's Bowl")).to_be_visible()

    # Edit affordance is now present (bob owns the copy). Match either
    # a link to /edit or a button.
    edit_target = page.get_by_role(
        "link", name=re.compile(r"^edit$", re.IGNORECASE)
    ).or_(
        page.get_by_role("button", name=re.compile(r"^edit$", re.IGNORECASE))
    ).first
    edit_target.click()
    page.wait_for_url(re.compile(rf"/recipes/{copy_id}/edit(?:[/?#]|$)"))

    # Rename and submit.
    name_input = page.get_by_label(re.compile(r"^name$", re.IGNORECASE))
    name_input.fill("Bob's Renamed Bowl")
    with page.expect_response(
        lambda r: r.url.endswith(f"/api/recipes/{copy_id}")
        and r.request.method == "PUT"
        and r.status == 200
    ):
        page.get_by_role("button", name=re.compile(r"^save$", re.IGNORECASE)).click()

    # Detail page reflects the new name.
    page.wait_for_url(re.compile(rf"/recipes/{copy_id}(?:[/?#]|$)"))
    expect(page.get_by_text("Bob's Renamed Bowl")).to_be_visible()

    # DB cross-check: two recipes, one per owner; alice's name is
    # unchanged; bob's row carries the new name; both have a
    # recipe_products row referencing chicken.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, created_by_user_id FROM recipes "
            "WHERE id = ANY(%s) ORDER BY id",
            ([alice_recipe["id"], copy_id],),
        )
        rows = cur.fetchall()
    assert len(rows) == 2, f"expected 2 recipes after copy, got {rows!r}"
    by_id = {row[0]: (row[1], row[2]) for row in rows}
    alice_name, alice_owner = by_id[alice_recipe["id"]]
    bob_name, bob_owner = by_id[copy_id]
    assert alice_name == "Alice's Bowl", (
        f"source recipe name should be unchanged after copy/edit; "
        f"got {alice_name!r}"
    )
    assert alice_owner == alice["id"], (
        f"source owner unchanged; got {alice_owner!r}"
    )
    assert bob_name == "Bob's Renamed Bowl", (
        f"copy should reflect the new name; got {bob_name!r}"
    )
    assert bob_owner == bob["id"], (
        f"copy should be owned by bob; got {bob_owner!r}"
    )

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT recipe_id, product_id, quantity_type, amount "
            "FROM recipe_products WHERE recipe_id = ANY(%s) "
            "ORDER BY recipe_id, product_id",
            ([alice_recipe["id"], copy_id],),
        )
        rp_rows = cur.fetchall()
    rp_by_recipe: dict[int, list] = {}
    for rid, pid, qty, amount in rp_rows:
        rp_by_recipe.setdefault(rid, []).append((pid, qty, float(amount)))

    assert rp_by_recipe.get(alice_recipe["id"]) == [
        (chicken["id"], "weight", 100.0)
    ], (
        f"alice's recipe_products row mismatch: "
        f"{rp_by_recipe.get(alice_recipe['id'])!r}"
    )
    assert rp_by_recipe.get(copy_id) == [
        (chicken["id"], "weight", 100.0)
    ], (
        f"bob's copy must carry the same recipe_products row as the "
        f"source per `api_spec.md` §7.5; got "
        f"{rp_by_recipe.get(copy_id)!r}"
    )
