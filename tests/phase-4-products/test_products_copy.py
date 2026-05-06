"""Product copy integration tests.

Spec: `.specs/ai_gen/api_spec.md` §6.5 — `POST /products/{id}/copy`.
Anyone authenticated can copy any product (own or other's). The copy is
owned by the caller, references the same `image_filename` (no file
duplication), preserves all nutrition facts, and is **not**
auto-starred.
"""

from __future__ import annotations

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    ERROR_NOT_FOUND,
    ERROR_UNAUTHORIZED,
    assert_problem_json,
)


def _facts_set(facts: list[dict]) -> set[tuple[int, str, float]]:
    return {
        (f["nutrition_fact_id"], f["quantity_type"], float(f["amount"]))
        for f in facts
    }


def _make_source_product(
    api_base_url: str, token: str, nutrition_fact_ids: dict[str, int]
) -> dict:
    body = {
        "name": "Original Product",
        "image_filename": "shared-uuid.jpg",
        "nutrition_facts": [
            {
                "nutrition_fact_id": nutrition_fact_ids["Energy"],
                "quantity_type": "weight",
                "amount": 165,
            },
            {
                "nutrition_fact_id": nutrition_fact_ids["Protein"],
                "quantity_type": "weight",
                "amount": 31,
            },
        ],
    }
    response = api_helpers.products_create(api_base_url, token=token, body=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_copy_other_users_product(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    user_a, token_a = make_user(username="alice_copy_src", password="hunter2pwd")
    user_b, token_b = make_user(username="bob_copy_caller", password="hunter2pwd")

    source = _make_source_product(api_base_url, token_a, nutrition_fact_ids)

    response = api_helpers.products_copy(
        api_base_url, token=token_b, product_id=source["id"]
    )

    assert response.status_code == 201, (
        f"Expected 201 on copy, got {response.status_code}. Body: {response.text!r}"
    )
    copy = response.json()

    assert isinstance(copy.get("id"), int) and copy["id"] != source["id"], (
        f"Copy must have a fresh id (not equal to source.id={source['id']}); "
        f"got {copy.get('id')!r}"
    )
    assert copy.get("name") == source["name"], (
        f"Copy name must match source: expected {source['name']!r}, "
        f"got {copy.get('name')!r}"
    )
    assert copy.get("image_filename") == source["image_filename"], (
        f"Copy image_filename must match source (no file duplication); "
        f"expected {source['image_filename']!r}, got {copy.get('image_filename')!r}"
    )
    assert copy.get("created_by", {}).get("id") == user_b["id"], (
        f"Copy.created_by must be the caller; expected user_b id={user_b['id']}, "
        f"got {copy.get('created_by')!r}"
    )
    assert copy.get("import_source") is None, (
        f"Copy.import_source must be null, got {copy.get('import_source')!r}"
    )
    assert copy.get("starred_by_me") is False, (
        f"Copy must not be auto-starred, got starred_by_me={copy.get('starred_by_me')!r}"
    )
    assert _facts_set(copy["nutrition_facts"]) == _facts_set(source["nutrition_facts"]), (
        f"Copy facts must match source: source={source['nutrition_facts']!r}, "
        f"copy={copy['nutrition_facts']!r}"
    )

    # Location header should point to the new product.
    location = response.headers.get("location")
    assert location == f"/products/{copy['id']}", (
        f"Expected Location: /products/{copy['id']!r}, got {location!r}"
    )

    # Source unchanged: same owner, same id, same facts.
    after_source = api_helpers.products_get(
        api_base_url, token=token_a, product_id=source["id"]
    )
    assert after_source.status_code == 200
    after_body = after_source.json()
    assert after_body["created_by"]["id"] == user_a["id"], (
        f"Source ownership must be unchanged after copy; "
        f"got {after_body['created_by']!r}"
    )
    assert _facts_set(after_body["nutrition_facts"]) == _facts_set(source["nutrition_facts"])


def test_copy_own_product_creates_duplicate(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """api_spec §6.5: 'Any user can copy any product' — including their own."""
    user_a, token_a = make_user(username="alice_self_copy", password="hunter2pwd")

    source = _make_source_product(api_base_url, token_a, nutrition_fact_ids)
    response = api_helpers.products_copy(
        api_base_url, token=token_a, product_id=source["id"]
    )

    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != source["id"], (
        f"Self-copy must produce a new id; got {copy['id']} == source {source['id']}"
    )
    assert copy["created_by"]["id"] == user_a["id"]
    assert _facts_set(copy["nutrition_facts"]) == _facts_set(source["nutrition_facts"])


def test_copy_unknown_product_returns_404(
    api_base_url: str, make_user
) -> None:
    _user, token = make_user(username="bob_copy_404", password="hunter2pwd")

    response = api_helpers.products_copy(
        api_base_url, token=token, product_id=999_999
    )

    assert_problem_json(response, status=404, type_uri=ERROR_NOT_FOUND)


def test_copy_without_auth_returns_401(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    _user, token = make_user(username="alice_copy_anon_src", password="hunter2pwd")
    source = _make_source_product(api_base_url, token, nutrition_fact_ids)

    response = api_helpers.products_copy(
        api_base_url, token=None, product_id=source["id"]
    )

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)
