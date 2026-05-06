"""Phase-8 edit-own-product flow via the UI.

Covers `testing_strategy.md` §5 phase 8 (`test_edit_own_product.py` —
"owner can edit; confirm new value appears").
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_owner_edits_product_name_and_change_persists(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids,
    pg_conn,
) -> None:
    """Owner opens their product, clicks Edit, changes the name, saves.
    The new name should be visible on the detail page and in the My
    Products list. Cross-check via Postgres that the row was updated.
    """
    _alice, alice_token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )
    product = make_product(
        token=alice_token,
        name="Original Name",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    )

    # UI login.
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill("alice")
    page.get_by_label("Password").fill("hunter2pwd")
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)

    # Navigate directly to the detail page; this is the same URL the
    # listing-card click would resolve to.
    page.goto(f"{app_base_url}/products/{product['id']}")
    expect(page.get_by_text("Original Name")).to_be_visible()

    # Click Edit, change the name, save.
    page.get_by_role("link", name="Edit").click()
    name_input = page.get_by_label("Name")
    name_input.fill("")
    name_input.fill("Renamed Product")

    with page.expect_response(
        lambda r: r.url.endswith(f"/api/products/{product['id']}")
        and r.request.method == "PUT"
        and r.status == 200
    ):
        page.get_by_role("button", name="Save").click()

    # The detail page (or listing) should reflect the new name.
    expect(page.get_by_text("Renamed Product")).to_be_visible()
    expect(page.get_by_text("Original Name")).to_have_count(0)

    # Cross-check the DB.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT name FROM products WHERE id = %s", (product["id"],)
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "Renamed Product", (
        f"DB still has the old name: {row[0]!r}"
    )

    # Listing should also reflect the change.
    page.get_by_role("link", name="My Products").click()
    expect(page.get_by_text("Renamed Product")).to_be_visible()
