"""Product authorization integration tests.

Spec: `.specs/ai_gen/api_spec.md` §1.5 (auth required), §6 (read open to
any authenticated user; PUT/DELETE owner-only), §15 (authorization
summary). The 403 case uses `/errors/forbidden-not-owner` per §4.1.
"""

from __future__ import annotations

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_FORBIDDEN_NOT_OWNER,
    ERROR_UNAUTHORIZED,
    assert_problem_json,
)


def _make_product(api_base_url: str, token: str, nutrition_fact_ids: dict[str, int]) -> dict:
    body = {
        "name": "Owner's Product",
        "image_filename": "owner-uuid.jpg",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Unauthenticated requests
# ---------------------------------------------------------------------------


def test_create_without_token_returns_401(
    api_base_url: str, nutrition_fact_ids: dict[str, int]
) -> None:
    body = {
        "name": "Anon Attempt",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 100,
            }
        ],
    }
    response = api_helpers.products_create(api_base_url, token=None, body=body)

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_get_without_token_returns_401(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="authz_get_owner", password="hunter2pwd")
    product = _make_product(api_base_url, token, nutrition_fact_ids)

    response = api_helpers.products_get(
        api_base_url, token=None, product_id=product["id"]
    )

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_update_without_token_returns_401(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="authz_put_owner", password="hunter2pwd")
    product = _make_product(api_base_url, token, nutrition_fact_ids)

    body = {
        "name": "Anon Edit",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 50,
            }
        ],
    }
    response = api_helpers.products_update(
        api_base_url, token=None, product_id=product["id"], body=body
    )

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


def test_delete_without_token_returns_401(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="authz_del_owner", password="hunter2pwd")
    product = _make_product(api_base_url, token, nutrition_fact_ids)

    response = api_helpers.products_delete(
        api_base_url, token=None, product_id=product["id"]
    )

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Cross-user access: read open, mutate forbidden
# ---------------------------------------------------------------------------


def test_other_user_can_read_product(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """api_spec §15: GET is open to any authenticated user."""
    user_a, token_a = make_user(username="alice_authz", password="hunter2pwd")
    _user_b, token_b = make_user(username="bob_authz", password="hunter2pwd")

    product = _make_product(api_base_url, token_a, nutrition_fact_ids)

    response = api_helpers.products_get(
        api_base_url, token=token_b, product_id=product["id"]
    )

    assert response.status_code == 200, (
        f"Expected 200 on cross-user GET, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    body = response.json()
    assert body.get("created_by", {}).get("id") == user_a["id"], (
        f"Cross-user GET should still surface the original owner; "
        f"body.created_by={body.get('created_by')!r}"
    )
    assert body.get("starred_by_me") is False, (
        f"User B has not starred Alice's product, expected starred_by_me=False, "
        f"got {body.get('starred_by_me')!r}"
    )


def test_other_user_put_returns_403_and_data_unchanged(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    user_a, token_a = make_user(username="alice_put_owner", password="hunter2pwd")
    _user_b, token_b = make_user(username="bob_put_attacker", password="hunter2pwd")

    product = _make_product(api_base_url, token_a, nutrition_fact_ids)
    original_name = product["name"]
    original_image = product["image_filename"]

    update_body = {
        "name": "Bob Hijack",
        "image_filename": "bob-pwn.png",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 1,
            }
        ],
    }
    response = api_helpers.products_update(
        api_base_url, token=token_b, product_id=product["id"], body=update_body
    )

    assert_problem_json(
        response, status=403, type_uri=ERROR_FORBIDDEN_NOT_OWNER
    )

    # Re-read as the owner — data must be exactly as Alice left it.
    after = api_helpers.products_get(
        api_base_url, token=token_a, product_id=product["id"]
    )
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["name"] == original_name, (
        f"403 PUT must not have mutated name; was {original_name!r}, "
        f"got {after_body['name']!r}"
    )
    assert after_body["image_filename"] == original_image, (
        f"403 PUT must not have mutated image; was {original_image!r}, "
        f"got {after_body['image_filename']!r}"
    )
    assert after_body["created_by"]["id"] == user_a["id"]


def test_other_user_delete_returns_403_and_product_remains(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user_a, token_a = make_user(username="alice_del_owner", password="hunter2pwd")
    _user_b, token_b = make_user(username="bob_del_attacker", password="hunter2pwd")

    product = _make_product(api_base_url, token_a, nutrition_fact_ids)

    response = api_helpers.products_delete(
        api_base_url, token=token_b, product_id=product["id"]
    )

    assert_problem_json(
        response, status=403, type_uri=ERROR_FORBIDDEN_NOT_OWNER
    )

    after = api_helpers.products_get(
        api_base_url, token=token_a, product_id=product["id"]
    )
    assert after.status_code == 200, (
        f"Product must still exist after a forbidden DELETE attempt; "
        f"GET returned {after.status_code} {after.text!r}"
    )
