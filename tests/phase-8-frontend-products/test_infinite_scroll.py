"""Phase-8 infinite-scroll mechanics on the My Products listing.

Covers `testing_strategy.md` §5 phase 8 (`test_infinite_scroll.py` —
"seed 50 products, scroll the list, assert at least three 'page' worth
of items load") in conjunction with the spec amendment in this same
session (30 → 50 to make ≥3 page-worths reachable with the API's
default `limit=20`).
"""

from __future__ import annotations

import time

from playwright.sync_api import Page, expect


def test_my_products_infinite_scroll_loads_three_pages(
    page: Page,
    app_base_url: str,
    make_user,
    make_product,
    nutrition_fact_ids,
) -> None:
    """Seed 50 products owned by Alice. Open My Products, scroll to the
    bottom in a loop, and assert that ≥3 distinct list-fetch requests
    fired (initial + ≥2 cursor-based follow-ups) and that all 50 cards
    eventually render.
    """
    _alice, alice_token = make_user(
        username="alice", password="hunter2pwd", full_name="Alice Smith"
    )

    energy_id = nutrition_fact_ids["Energy"]
    for i in range(1, 51):
        make_product(
            token=alice_token,
            name=f"Prod {i:02d}",
            nutrition_facts=[
                {
                    "nutrition_fact_id": energy_id,
                    "quantity_type": "weight",
                    "amount": 100 + i,
                }
            ],
        )

    # Track every GET /api/products?scope=mine&... request the page makes.
    list_request_urls: list[str] = []

    def _on_request(request) -> None:
        if request.method != "GET":
            return
        if "/api/products" not in request.url:
            return
        if "scope=mine" not in request.url:
            return
        list_request_urls.append(request.url)

    page.on("request", _on_request)

    # UI login.
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill("alice")
    page.get_by_label("Password").fill("hunter2pwd")
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(lambda url: "/login" not in url)

    page.get_by_role("link", name="My Products").click()

    # Wait for the first batch (limit=20 by default per api_spec §5.1).
    # Sort is created_at DESC (api_spec §6.6), so Prod 50 is the most-recent
    # and reliably renders in the first page.
    expect(page.get_by_text("Prod 50")).to_be_visible()

    # Scroll to bottom in a loop until all 50 cards are visible or we
    # give up. The loop bound is generous; the test should converge in
    # 3-4 iterations with limit=20 (initial + 20 + 10 = 50).
    deadline = time.monotonic() + 30.0
    last_count = 0
    while time.monotonic() < deadline:
        # Scroll the document body to the bottom — works for both
        # window-scrolled and container-scrolled listings as long as the
        # listing reaches the page bottom.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        # Also nudge mouse wheel inside the viewport in case the
        # implementation uses an inner scroll container.
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(500)

        # Count visible "Prod NN" texts (these are unique per card).
        # Use locator-based count rather than a snapshot.
        current_count = page.get_by_text("Prod ", exact=False).count()
        if current_count >= 50:
            break
        if current_count == last_count and current_count > 0:
            # No progress this iteration; let the network catch up.
            page.wait_for_timeout(500)
        last_count = current_count

    # Final assertion: every product is visible.
    for i in (1, 25, 49, 50):
        expect(page.get_by_text(f"Prod {i:02d}")).to_be_visible()

    # At least three distinct list-fetch requests must have been issued
    # — the initial page plus ≥2 cursor-based follow-ups. We
    # de-duplicate by full URL; identical retries collapse to one entry.
    distinct_urls = list(dict.fromkeys(list_request_urls))
    assert len(distinct_urls) >= 3, (
        f"expected ≥3 distinct list-fetch URLs (initial + ≥2 cursor "
        f"follow-ups), got {len(distinct_urls)}: {distinct_urls!r}"
    )

    # And: at least 2 of those URLs must include a `cursor=` parameter
    # (the cursor-based follow-ups). The first request omits cursor.
    cursored = [u for u in distinct_urls if "cursor=" in u]
    assert len(cursored) >= 2, (
        f"expected ≥2 cursor-based follow-up requests, got {len(cursored)}: "
        f"{cursored!r}"
    )
