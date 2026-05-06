"""Product orchestration: validation + DAL coordination."""

from __future__ import annotations

from typing import Any

from api.errors import (
    DuplicateNutritionFactError,
    ForbiddenNotOwnerError,
    NoNutritionFactsError,
    NotFoundError,
    ServiceValidationError,
)
from api.schemas.products import ProductCreate
from dal import nutrition_fact_types as nft_dal
from dal import products as products_dal
from dal.connections import read_only, transaction


def _facts_to_dicts(body: ProductCreate) -> list[dict[str, Any]]:
    return [
        {
            "nutrition_fact_id": f.nutrition_fact_id,
            "quantity_type": f.quantity_type,
            "amount": float(f.amount),
        }
        for f in body.nutrition_facts
    ]


async def _validate_facts(
    conn,
    body: ProductCreate,
) -> list[dict[str, Any]]:
    """Run the three semantic checks (empty / dupes / unknown FK) and
    return the facts as plain dicts ready for insertion.
    """
    facts = _facts_to_dicts(body)
    if not facts:
        raise NoNutritionFactsError(
            "Product must have at least one nutrition fact."
        )

    seen: set[tuple[int, str]] = set()
    for f in facts:
        key = (f["nutrition_fact_id"], f["quantity_type"])
        if key in seen:
            raise DuplicateNutritionFactError(
                "Same (nutrition_fact_id, quantity_type) listed more than once.",
            )
        seen.add(key)

    requested_ids = {f["nutrition_fact_id"] for f in facts}
    unknown_ids = await nft_dal.find_unknown_ids(conn, requested_ids)
    if unknown_ids:
        violations = [
            {
                "field": f"nutrition_facts.{i}.nutrition_fact_id",
                "message": f"unknown nutrition_fact_id: {f['nutrition_fact_id']}",
            }
            for i, f in enumerate(facts)
            if f["nutrition_fact_id"] in unknown_ids
        ]
        raise ServiceValidationError(
            "One or more nutrition_fact_id values do not exist.",
            violations=violations,
        )
    return facts


def _wrap_for_response(row: dict) -> dict:
    """Fill in `starred_by_me` (always False until phase 6)."""
    return {**row, "starred_by_me": False}


async def create(*, user_id: int, body: ProductCreate) -> dict:
    async with transaction() as conn:
        facts = await _validate_facts(conn, body)
        product = await products_dal.insert_product(
            conn,
            name=body.name,
            image_filename=body.image_filename,
            created_by_user_id=user_id,
        )
        await products_dal.insert_product_facts(
            conn, product_id=product["id"], facts=facts
        )
        full = await products_dal.get_product_with_facts(conn, product["id"])
    assert full is not None
    return _wrap_for_response(full)


async def get(product_id: int) -> dict:
    async with read_only() as conn:
        full = await products_dal.get_product_with_facts(conn, product_id)
    if full is None:
        raise NotFoundError(f"Product {product_id} not found.")
    return _wrap_for_response(full)


async def replace(
    *, product_id: int, user_id: int, body: ProductCreate
) -> dict:
    async with transaction() as conn:
        owner_id = await _require_owner(conn, product_id, user_id)
        del owner_id  # silence unused warning; the call raises if not owner

        facts = await _validate_facts(conn, body)

        await products_dal.update_product_fields(
            conn,
            product_id=product_id,
            name=body.name,
            image_filename=body.image_filename,
        )
        await products_dal.delete_product_facts(conn, product_id)
        await products_dal.insert_product_facts(
            conn, product_id=product_id, facts=facts
        )
        full = await products_dal.get_product_with_facts(conn, product_id)
    assert full is not None
    return _wrap_for_response(full)


async def delete(*, product_id: int, user_id: int) -> None:
    async with transaction() as conn:
        await _require_owner(conn, product_id, user_id)
        await products_dal.delete_product(conn, product_id)


async def copy(*, source_id: int, user_id: int) -> dict:
    async with transaction() as conn:
        source = await products_dal.get_product_with_facts(conn, source_id)
        if source is None:
            raise NotFoundError(f"Product {source_id} not found.")

        new = await products_dal.insert_product(
            conn,
            name=source["name"],
            image_filename=source["image_filename"],
            created_by_user_id=user_id,
        )
        cloned_facts = [
            {
                "nutrition_fact_id": f["nutrition_fact_id"],
                "quantity_type": f["quantity_type"],
                "amount": float(f["amount"]),
            }
            for f in source["nutrition_facts"]
        ]
        await products_dal.insert_product_facts(
            conn, product_id=new["id"], facts=cloned_facts
        )
        full = await products_dal.get_product_with_facts(conn, new["id"])
    assert full is not None
    return _wrap_for_response(full)


async def _require_owner(conn, product_id: int, user_id: int) -> int:
    """Raise NotFound (no row) or ForbiddenNotOwner (row exists, owner mismatch).

    Returns the verified owner id.
    """
    if not await products_dal.product_exists(conn, product_id):
        raise NotFoundError(f"Product {product_id} not found.")
    owner_id = await products_dal.get_product_owner(conn, product_id)
    if owner_id != user_id:
        raise ForbiddenNotOwnerError(
            f"Caller is not the owner of product {product_id}."
        )
    return owner_id
