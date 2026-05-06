"""Phase-8 product creation flow via the UI.

Covers `testing_strategy.md` §5 phase 8 (`test_create_product.py` —
"go to 'My Products', click create, fill form, upload an image
(Playwright provides `page.set_input_files`), submit, see the new
product in 'My Products'").

Asserts both the visible UI state and the underlying database state
to confirm the request actually reached the backend.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from tests.helpers.images import JPEG_BYTES


def test_create_product_via_ui_with_image_appears_in_my_products(
    page: Page,
    app_base_url: str,
    make_user,
    nutrition_fact_ids,
    pg_conn,
) -> None:
    """Sign in, fill the New Product form, upload a tiny JPEG, add one
    nutrition fact, submit, and confirm the product appears in My
    Products. Cross-check via Postgres that one product row + one
    product_nutrition_facts row was written.
    """
    user, _token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )

    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill("alice")
    page.get_by_label("Password").fill("hunter2pwd")
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)

    # Navigate to My Products and start a new product.
    page.get_by_role("link", name="My Products").click()
    page.get_by_role("link", name="New Product").click()

    page.get_by_label("Name").fill("Chicken Breast")

    # Upload an in-memory JPEG via Playwright's FilePayload shape.
    # The form must contain an <input type="file">.
    page.locator('input[type="file"]').set_input_files(
        files=[
            {
                "name": "chicken.jpg",
                "mimeType": "image/jpeg",
                "buffer": JPEG_BYTES,
            }
        ]
    )

    # Add one Energy / weight / 165 nutrition fact.
    # Implementation surfaces two collapsible sub-forms (weight, volume) per
    # implementation_plan §Phase 8. The "Add weight fact" affordance opens
    # the weight sub-form's first row.
    page.get_by_role("button", name="Add weight fact").click()
    page.get_by_label("Nutrition fact").select_option(label="Energy")
    page.get_by_label("Amount").fill("165")

    # Submit and wait for the create call to complete.
    with page.expect_response(
        lambda r: r.url.endswith("/api/products")
        and r.request.method == "POST"
        and r.status == 201
    ):
        page.get_by_role("button", name="Save").click()

    # Back on My Products, the new card should appear.
    page.wait_for_url(lambda url: "/products" in url and "/new" not in url)
    expect(page.get_by_text("Chicken Breast")).to_be_visible()

    # DB cross-check: one product row owned by Alice + one weight fact.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, image_filename, created_by_user_id "
            "FROM products WHERE created_by_user_id = %s",
            (user["id"],),
        )
        rows = cur.fetchall()
    assert len(rows) == 1, f"expected exactly 1 product row, got {len(rows)}: {rows!r}"
    product_id, name, image_filename, owner_id = rows[0]
    assert name == "Chicken Breast"
    assert owner_id == user["id"]
    assert image_filename and image_filename.endswith(".jpg"), (
        f"image_filename should be a UUID4-named .jpg, got {image_filename!r}"
    )

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT nutrition_fact_id, quantity_type, amount "
            "FROM product_nutrition_facts WHERE product_id = %s",
            (product_id,),
        )
        facts = cur.fetchall()
    assert len(facts) == 1, f"expected exactly 1 fact, got {facts!r}"
    fact_id, qty_type, amount = facts[0]
    assert fact_id == nutrition_fact_ids["Energy"]
    assert qty_type == "weight"
    assert amount == 165
