"""Phase-8 mobile-viewport layout adaptation.

CLAUDE.md mandates "Layout must adapt to both regular and mobile
screens (DaisyUI handles most of this; verify with phase-8 tests at
small viewports)". `implementation_plan.md` §Phase 8 specifies a
"top app bar with current section and a hamburger menu on small
screens; full sidebar on `md+`".

This file is the 7th phase-8 test (added in the same session that
authored the suite — see `testing_strategy.md` §5 phase 8 amendment).
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_mobile_viewport_shows_hamburger_menu(
    mobile_page: Page,
    app_base_url: str,
    make_user,
) -> None:
    """At a 360x640 viewport, the desktop sidebar must be hidden and a
    hamburger button must be visible. Clicking the hamburger reveals
    the navigation drawer with the My Products link.
    """
    make_user(username="alice", password="hunter2pwd", full_name="Alice Smith")

    mobile_page.goto(f"{app_base_url}/login")
    mobile_page.get_by_label("Username").fill("alice")
    mobile_page.get_by_label("Password").fill("hunter2pwd")
    mobile_page.get_by_role("button", name="Log in").click()
    mobile_page.wait_for_url(lambda url: "/login" not in url)

    # The full sidebar should NOT be visible at 360x640.
    # Implementation may render the sidebar element in the DOM but hide
    # it via Tailwind's `hidden md:block` (or DaisyUI drawer collapse);
    # both cases satisfy `to_be_hidden`.
    sidebar = mobile_page.get_by_role("navigation", name="Primary")
    if sidebar.count() > 0:
        expect(sidebar.first).to_be_hidden()

    # The hamburger menu trigger MUST be visible. The implementation may
    # name it "Open menu", "Menu", or use an icon-only button with an
    # `aria-label`; we match leniently on accessible name.
    hamburger = mobile_page.get_by_role(
        "button", name=re.compile(r"menu", re.IGNORECASE)
    ).first
    expect(hamburger).to_be_visible()

    # Open the menu and assert the My Products link is now accessible.
    hamburger.click()
    expect(mobile_page.get_by_role("link", name="My Products")).to_be_visible()
