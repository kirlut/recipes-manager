"""Phase-8 register / login / logout flow via the UI.

Covers `testing_strategy.md` §5 phase 8 (`test_register_login.py` —
"register via UI, log out, log in, verify auth state visible") plus
`implementation_plan.md` §Phase 8 scope:

- Routes `/login`, `/register`, `/products` (My / Starred / Search tabs).
- Auth flow stores the JWT in `localStorage` under key `auth_token`
  (CLAUDE.md "Frontend").
- A visible Logout affordance must exist (per the spec amendment in
  this same session).

These tests interact through the browser only; backend cross-checks
use `pg_conn` to confirm DB-level effects without trusting the UI.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

# Lenient match for the Logout affordance — implementation may render
# it as "Logout", "Log out", "LOG OUT", etc. Mirrors the regex defined
# in conftest.py (kept inline here to avoid relative-import pitfalls;
# pytest test files aren't part of a Python package).
LOGOUT_NAME_RE = re.compile(r"log\s*out", re.IGNORECASE)


def _do_login_via_ui(page: Page, app_base_url: str, *, username: str, password: str) -> None:
    """Drive the login form. Used both by tests that test login and by
    tests that just need to be authenticated to test something else.
    """
    page.goto(f"{app_base_url}/login")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()


def test_register_via_ui_creates_user_and_logs_in(
    page: Page,
    app_base_url: str,
    pg_conn,
) -> None:
    """A brand-new user can register through the UI and lands in an
    authenticated state. Per `api_spec.md` §2.2 register returns 201
    without a token; the implementation may auto-login after register
    or send the user to `/login` — both are acceptable, this test
    follows the "register then log in" path explicitly.
    """
    page.goto(f"{app_base_url}/register")
    page.get_by_label("Username").fill("alice")
    page.get_by_label("Password").fill("hunter2pwd")
    # `full_name` is optional per api_spec §2.2; provide it to verify
    # the field is wired through.
    page.get_by_label("Full name").fill("Alice Smith")
    page.get_by_role("button", name="Register").click()

    # The implementation may either auto-login + redirect, or send the
    # user to `/login`. We accept either: if we're not authed yet, log
    # in explicitly and assert auth state afterwards.
    if "/login" in page.url or "/register" in page.url:
        _do_login_via_ui(
            page, app_base_url, username="alice", password="hunter2pwd"
        )

    page.wait_for_url(lambda url: "/login" not in url and "/register" not in url)
    # The user's identity should be visible somewhere in the chrome —
    # the implementation plan describes a top app bar / sidebar with
    # the current user info. We assert by username text.
    expect(page.get_by_text("alice")).to_be_visible()

    # DB cross-check: the row exists with the username we registered.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, full_name FROM users WHERE username = %s",
            ("alice",),
        )
        row = cur.fetchone()
    assert row is not None, "users row not created by /register"
    assert row[1] == "alice"
    assert row[2] == "Alice Smith"


def test_login_with_existing_user_shows_authed_state(
    page: Page,
    app_base_url: str,
    make_user,
) -> None:
    """A user seeded via the API can log in through the UI."""
    make_user(username="bob", password="hunter2pwd", full_name="Bob Jones")
    _do_login_via_ui(page, app_base_url, username="bob", password="hunter2pwd")

    page.wait_for_url(lambda url: "/login" not in url)
    # Per implementation_plan §Phase 8, `/products` (with My / Starred /
    # Search tabs) is the post-login default destination. Either an
    # immediate redirect to `/products` or visible "My Products" nav
    # entry counts as authed.
    expect(page.get_by_role("link", name="My Products")).to_be_visible()


def test_logout_clears_token_and_redirects_to_login(
    page: Page,
    app_base_url: str,
    make_user,
) -> None:
    """The Logout affordance clears the JWT from localStorage and
    bounces the user to `/login`. Per CLAUDE.md the token key is
    `auth_token`.
    """
    make_user(username="carol", password="hunter2pwd", full_name="Carol Diaz")
    _do_login_via_ui(page, app_base_url, username="carol", password="hunter2pwd")
    page.wait_for_url(lambda url: "/login" not in url)

    # Sanity: the token was stored.
    token_before = page.evaluate("() => window.localStorage.getItem('auth_token')")
    assert token_before, (
        "auth_token must be present in localStorage after a successful login"
    )

    # The implementation may render Logout as a top-level button OR
    # inside a user menu. Look for the role-named control first; if
    # invisible (likely hidden inside a menu), open the user menu and
    # try again.
    logout = page.get_by_role("button", name=LOGOUT_NAME_RE)
    if logout.count() == 0 or not logout.first.is_visible():
        # Fall back to any clickable element (link / menuitem) named "Logout".
        logout = page.get_by_role("menuitem", name=LOGOUT_NAME_RE)
        if logout.count() == 0 or not logout.first.is_visible():
            # Open a probable user menu: a button containing the username.
            page.get_by_role("button", name="carol").click()
            logout = page.get_by_role("menuitem", name=LOGOUT_NAME_RE)
    logout.first.click()

    page.wait_for_url(lambda url: url.rstrip("/").endswith("/login"))
    token_after = page.evaluate("() => window.localStorage.getItem('auth_token')")
    assert token_after is None, (
        f"auth_token must be cleared on logout, got {token_after!r}"
    )
