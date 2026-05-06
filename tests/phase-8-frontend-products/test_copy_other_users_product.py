"""Phase-8 copy-another-users-product flow via the UI.

Covers `testing_strategy.md` §5 phase 8
(`test_copy_other_users_product.py` — "User B opens A's product, 'Edit'
is disabled / not shown, 'Copy' button is shown; clicking 'Copy'
creates a new product in B's 'My Products' with the same image and
facts").
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


def _login_via_ui(page: Page, app_base_url: str, *, username: str, password: str) -> None:
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)


def test_non_owner_sees_copy_not_edit(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    make_image_filename,
    nutrition_fact_ids,
) -> None:
    """When a non-owner views a product detail page, the Edit affordance
    must be absent and a Copy button must be visible. Per `api_spec.md`
    §6.3 only the owner can PUT/DELETE; the UI must not even tempt the
    user with an Edit button.
    """
    _alice, alice_token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )
    _bob, _bob_token = make_user(
        username="bob", password="hunter2pwd", full_name="Bob Jones"
    )

    image_filename = make_image_filename(token=alice_token, kind="jpeg")
    alice_product = make_product(
        token=alice_token,
        name="Alice's Quinoa",
        image_filename=image_filename,
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 120,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 4.4,
            },
        ],
    )

    _login_via_ui(page, app_base_url, username="bob", password="hunter2pwd")
    page.goto(f"{app_base_url}/products/{alice_product['id']}")

    # Detail loaded.
    expect(page.get_by_text("Alice's Quinoa")).to_be_visible()

    # Edit must NOT be visible to a non-owner.
    expect(page.get_by_role("link", name="Edit")).to_have_count(0)
    expect(page.get_by_role("button", name="Edit")).to_have_count(0)

    # Copy must BE visible.
    expect(page.get_by_role("button", name="Copy")).to_be_visible()


def test_copy_creates_new_product_in_b_my_products(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    make_image_filename,
    nutrition_fact_ids,
    pg_conn,
) -> None:
    """Clicking Copy on another user's product creates a new product
    owned by the caller, with the same image_filename and facts.
    """
    alice, alice_token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )
    bob, _bob_token = make_user(
        username="bob", password="hunter2pwd", full_name="Bob Jones"
    )

    image_filename = make_image_filename(token=alice_token, kind="jpeg")
    alice_product = make_product(
        token=alice_token,
        name="Alice's Quinoa",
        image_filename=image_filename,
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 120,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 4.4,
            },
        ],
    )

    _login_via_ui(page, app_base_url, username="bob", password="hunter2pwd")
    page.goto(f"{app_base_url}/products/{alice_product['id']}")

    with page.expect_response(
        lambda r: r.url.endswith(f"/api/products/{alice_product['id']}/copy")
        and r.request.method == "POST"
        and r.status == 201
    ):
        page.get_by_role("button", name="Copy").click()

    # Bob's My Products should now contain a product with the same name.
    page.get_by_role("link", name="My Products").click()
    expect(page.get_by_text("Alice's Quinoa")).to_be_visible()

    # DB cross-check: two products with the same name; one owned by
    # Alice, one by Bob; same image_filename on both (per api_spec
    # §6.5 the copy reuses the filename without duplicating the file).
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, created_by_user_id, image_filename "
            "FROM products WHERE name = %s ORDER BY id",
            ("Alice's Quinoa",),
        )
        rows = cur.fetchall()
    assert len(rows) == 2, f"expected 2 products after copy, got {rows!r}"
    owners = {row[1] for row in rows}
    assert owners == {alice["id"], bob["id"]}, (
        f"unexpected owners after copy: {owners!r}"
    )
    image_filenames = {row[2] for row in rows}
    assert image_filenames == {image_filename}, (
        f"copy should reuse the source image_filename, got {image_filenames!r}"
    )

    # The two products must have the same fact set (composite PK
    # (product_id, nutrition_fact_id, quantity_type)).
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT product_id, nutrition_fact_id, quantity_type, amount "
            "FROM product_nutrition_facts "
            "WHERE product_id = ANY(%s) "
            "ORDER BY product_id, nutrition_fact_id",
            ([row[0] for row in rows],),
        )
        facts = cur.fetchall()
    facts_by_product: dict[int, set[tuple[int, str, float]]] = {}
    for product_id, fact_id, qty, amount in facts:
        facts_by_product.setdefault(product_id, set()).add(
            (fact_id, qty, float(amount))
        )
    assert len(facts_by_product) == 2
    fact_sets = list(facts_by_product.values())
    assert fact_sets[0] == fact_sets[1], (
        f"copy must clone facts exactly: {facts_by_product!r}"
    )
