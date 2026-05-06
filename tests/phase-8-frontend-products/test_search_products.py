"""Phase-8 product search + starring flow via the UI.

Covers `testing_strategy.md` §5 phase 8 (`test_search_products.py` —
"User A creates a product; User B logs in; in 'Search', types the
name; result list shows it; B clicks star; 'My Starred Products'
contains it").
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_user_b_searches_user_a_product_and_stars_it(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids,
) -> None:
    """User A creates a uniquely-named product. User B logs in,
    searches by name (the API's 0.3 similarity threshold is comfortably
    cleared by an exact substring), stars the product, and finds it in
    the Starred tab.
    """
    _alice, alice_token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )
    _bob, _bob_token = make_user(
        username="bob", password="hunter2pwd", full_name="Bob Jones"
    )

    # Seed a uniquely-named product owned by Alice via the API to keep
    # the test focused on B's search/star flow rather than re-testing
    # creation.
    alice_product = make_product(
        token=alice_token,
        name="Unique Quinoa",
        nutrition_facts=[
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 120,
            }
        ],
    )

    # Bob logs in via the UI.
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill("bob")
    page.get_by_label("Password").fill("hunter2pwd")
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)

    page.get_by_role("link", name="My Products").click()

    # Switch to the Search sub-tab and type the query. The
    # implementation debounces input by 300ms (implementation_plan
    # §Phase 8); waiting on the network response is the most reliable
    # synchronization.
    page.get_by_role("tab", name="Search").click()
    search_input = page.get_by_role("searchbox")
    with page.expect_response(
        lambda r: "/api/products" in r.url
        and "scope=search" in r.url
        and "q=" in r.url
        and r.status == 200
    ):
        search_input.fill("Quinoa")

    # The product card should be visible in results.
    expect(page.get_by_text("Unique Quinoa")).to_be_visible()

    # Click the star control on the matching card. The implementation
    # is expected to render the star with an accessible name like
    # "Star" / "Add to starred"; we match leniently.
    star_button = page.get_by_role(
        "button", name=re.compile(r"star", re.IGNORECASE)
    ).first
    with page.expect_response(
        lambda r: r.url.endswith(f"/api/products/{alice_product['id']}/star")
        and r.request.method == "PUT"
        and r.status == 204
    ):
        star_button.click()

    # Switch to the Starred sub-tab; the product should appear there.
    page.get_by_role("tab", name="Starred").click()
    expect(page.get_by_text("Unique Quinoa")).to_be_visible()
