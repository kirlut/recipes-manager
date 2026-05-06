"""Product orchestration: validation + DAL coordination."""

from __future__ import annotations

from typing import Any, Literal

from api.errors import (
    DuplicateNutritionFactError,
    ForbiddenNotOwnerError,
    InvalidCursorError,
    NoNutritionFactsError,
    NotFoundError,
    ServiceValidationError,
)
from api.schemas.products import ProductCreate
from dal import nutrition_fact_types as nft_dal
from dal import products as products_dal
from dal.connections import read_only, transaction
from services import cursor as cursor_svc
from settings import settings

Scope = Literal["mine", "starred", "search"]


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


async def _wrap_for_response(conn, row: dict, *, caller_user_id: int) -> dict:
    """Attach `starred_by_me` for the caller (per `api_spec.md` §3.5)."""
    starred = await products_dal.is_starred_by(
        conn, user_id=caller_user_id, product_id=row["id"]
    )
    return {**row, "starred_by_me": starred}


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
        return await _wrap_for_response(conn, full, caller_user_id=user_id)


async def get(*, product_id: int, user_id: int) -> dict:
    async with read_only() as conn:
        full = await products_dal.get_product_with_facts(conn, product_id)
        if full is None:
            raise NotFoundError(f"Product {product_id} not found.")
        return await _wrap_for_response(conn, full, caller_user_id=user_id)


async def replace(
    *, product_id: int, user_id: int, body: ProductCreate
) -> dict:
    async with transaction() as conn:
        await _require_owner(conn, product_id, user_id)
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
        return await _wrap_for_response(conn, full, caller_user_id=user_id)


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
        return await _wrap_for_response(conn, full, caller_user_id=user_id)


async def list_products(
    *,
    user_id: int,
    scope: Scope,
    q: str | None,
    cursor_token: str | None,
    limit: int,
) -> dict:
    """Return `{items, next?}` for the requested scope.

    The `self`/`next` URL fields are constructed by the API layer where
    the request URL is known. This service returns the raw items + an
    optional `next_cursor` token for the API layer to format.
    """
    async with read_only() as conn:
        if scope == "search":
            assert q is not None and q != ""
            cursor: tuple[float, int] | None = (
                cursor_svc.decode_search(cursor_token)
                if cursor_token is not None
                else None
            )
            rows = await products_dal.list_search(
                conn,
                user_id=user_id,
                q=q,
                threshold=settings.search_similarity_threshold,
                cursor=cursor,
                limit=limit,
            )
            has_more = len(rows) > limit
            kept = rows[:limit]
            next_token: str | None = None
            if has_more:
                last = kept[-1]
                next_token = cursor_svc.encode_search(
                    similarity=last["_similarity"], item_id=last["id"]
                )
            for item in kept:
                item.pop("_similarity", None)
            return {"items": kept, "next_cursor": next_token}

        # Chronological: mine | starred.
        chrono_cursor: tuple[Any, int] | None = (
            cursor_svc.decode_chronological(cursor_token)
            if cursor_token is not None
            else None
        )
        if scope == "mine":
            rows = await products_dal.list_mine(
                conn, user_id=user_id, cursor=chrono_cursor, limit=limit
            )
            has_more = len(rows) > limit
            kept = rows[:limit]
            next_token = None
            if has_more:
                last = kept[-1]
                next_token = cursor_svc.encode_chronological(
                    when=last["created_at"], item_id=last["id"]
                )
            return {"items": kept, "next_cursor": next_token}

        if scope == "starred":
            rows = await products_dal.list_starred(
                conn, user_id=user_id, cursor=chrono_cursor, limit=limit
            )
            has_more = len(rows) > limit
            kept = rows[:limit]
            next_token = None
            if has_more:
                last = kept[-1]
                next_token = cursor_svc.encode_chronological(
                    when=last["_star_created_at"], item_id=last["id"]
                )
            for item in kept:
                item.pop("_star_created_at", None)
            return {"items": kept, "next_cursor": next_token}

        # Should be unreachable thanks to Pydantic Literal validation.
        raise InvalidCursorError(f"unknown scope: {scope!r}")


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
