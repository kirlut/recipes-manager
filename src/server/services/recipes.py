"""Recipe orchestration: validation + totals + DAL coordination."""

from __future__ import annotations

from typing import Any, Literal

from api.errors import (
    DuplicateRecipeProductError,
    ForbiddenNotOwnerError,
    InvalidCursorError,
    NotFoundError,
    QuantityTypeMismatchError,
    ServiceValidationError,
)
from api.schemas.recipes import RecipeCreate
from dal import recipes as recipes_dal
from dal.connections import read_only, transaction
from services import cursor as cursor_svc
from settings import settings

Scope = Literal["mine", "starred", "search"]


def _products_to_dicts(body: RecipeCreate) -> list[dict[str, Any]]:
    return [
        {
            "product_id": p.product_id,
            "quantity_type": p.quantity_type,
            "amount": float(p.amount),
        }
        for p in body.products
    ]


async def _validate_products(
    conn,
    body: RecipeCreate,
) -> list[dict[str, Any]]:
    """Run the three semantic checks and return recipe-products as dicts.

    Order (matches `services/products.py`):
        1. Duplicate `product_id`            → 422 /errors/duplicate-recipe-product
        2. Unknown `product_id`              → 422 /errors/validation (+violations)
        3. Quantity-type mismatch            → 422 /errors/quantity-type-mismatch
    """
    products = _products_to_dicts(body)
    if not products:
        return products

    # 1. Duplicate product_id.
    seen: set[int] = set()
    for p in products:
        pid = p["product_id"]
        if pid in seen:
            raise DuplicateRecipeProductError(
                f"product_id {pid} listed more than once.",
            )
        seen.add(pid)

    # 2. Unknown product_id (FK existence check).
    requested_ids = {p["product_id"] for p in products}
    existing_ids = await recipes_dal.existing_product_ids(conn, requested_ids)
    unknown_ids = requested_ids - existing_ids
    if unknown_ids:
        violations = [
            {
                "field": f"products.{i}.product_id",
                "message": f"unknown product_id: {p['product_id']}",
            }
            for i, p in enumerate(products)
            if p["product_id"] in unknown_ids
        ]
        raise ServiceValidationError(
            "One or more product_id values do not exist.",
            violations=violations,
        )

    # 3. Quantity-type mismatch: every (product_id, quantity_type) pair
    # in the request must correspond to at least one product_nutrition_facts
    # row for that pair.
    requested_pairs = [
        (p["product_id"], p["quantity_type"]) for p in products
    ]
    fact_rows = await recipes_dal.fetch_facts_for_pairs(conn, requested_pairs)
    existing_pairs = {(r["product_id"], r["quantity_type"]) for r in fact_rows}
    for p in products:
        pair = (p["product_id"], p["quantity_type"])
        if pair not in existing_pairs:
            raise QuantityTypeMismatchError(
                f"Product {p['product_id']} has no nutrition facts for "
                f"quantity_type={p['quantity_type']}.",
                extensions={
                    "product_id": p["product_id"],
                    "requested_quantity_type": p["quantity_type"],
                },
            )

    return products


def _compute_totals(
    recipe_products: list[dict[str, Any]],
    fact_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate `nutrition_totals_per_serving` per `api_spec.md` §13.

    For each nutrition_fact_type t:
        total_t = sum_{i} pnf(p_i, t, q_i).amount × (a_i / 100)

    Zero totals are omitted. Output ordered by nutrition_fact_id ascending
    (which aligns with the seeded order Energy, Protein, Net Carbs, Fat,
    Fibers).
    """
    if not recipe_products or not fact_rows:
        return []

    # Index fact rows by (product_id, quantity_type) → list of facts.
    facts_by_pair: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in fact_rows:
        key = (row["product_id"], row["quantity_type"])
        facts_by_pair.setdefault(key, []).append(row)

    # Aggregate by nutrition_fact_id.
    totals: dict[int, dict[str, Any]] = {}
    for rp in recipe_products:
        pair = (rp["product_id"], rp["quantity_type"])
        scale = float(rp["amount"]) / 100.0
        for fact in facts_by_pair.get(pair, ()):
            fid = fact["nutrition_fact_id"]
            entry = totals.get(fid)
            if entry is None:
                totals[fid] = {
                    "nutrition_fact_id": fid,
                    "nutrition_fact_name": fact["nutrition_fact_name"],
                    "unit": fact["unit"],
                    "amount": float(fact["amount"]) * scale,
                }
            else:
                entry["amount"] += float(fact["amount"]) * scale

    return [
        totals[fid]
        for fid in sorted(totals)
        if totals[fid]["amount"] != 0
    ]


async def _assemble_response(conn, recipe_id: int, *, caller_user_id: int) -> dict:
    """Build the full Recipe response shape from the DB state."""
    recipe = await recipes_dal.get_recipe_with_products(conn, recipe_id)
    assert recipe is not None
    pairs = [
        (rp["product_id"], rp["quantity_type"]) for rp in recipe["products"]
    ]
    fact_rows = await recipes_dal.fetch_facts_for_pairs(conn, pairs)
    totals = _compute_totals(recipe["products"], fact_rows)
    starred = await recipes_dal.is_starred_by(
        conn, user_id=caller_user_id, recipe_id=recipe_id
    )
    return {
        **recipe,
        "starred_by_me": starred,
        "nutrition_totals_per_serving": totals,
    }


async def _require_owner(conn, recipe_id: int, user_id: int) -> int:
    """Raise NotFound (no row) or ForbiddenNotOwner (row exists, owner mismatch).

    Returns the verified owner id.
    """
    if not await recipes_dal.recipe_exists(conn, recipe_id):
        raise NotFoundError(f"Recipe {recipe_id} not found.")
    owner_id = await recipes_dal.get_recipe_owner(conn, recipe_id)
    if owner_id != user_id:
        raise ForbiddenNotOwnerError(
            f"Caller is not the owner of recipe {recipe_id}."
        )
    return owner_id


async def create(*, user_id: int, body: RecipeCreate) -> dict:
    async with transaction() as conn:
        products = await _validate_products(conn, body)
        recipe = await recipes_dal.insert_recipe(
            conn,
            name=body.name,
            description=body.description,
            image_filename=body.image_filename,
            created_by_user_id=user_id,
        )
        await recipes_dal.insert_recipe_products(
            conn, recipe_id=recipe["id"], products=products
        )
        return await _assemble_response(conn, recipe["id"], caller_user_id=user_id)


async def get(*, recipe_id: int, user_id: int) -> dict:
    async with read_only() as conn:
        if not await recipes_dal.recipe_exists(conn, recipe_id):
            raise NotFoundError(f"Recipe {recipe_id} not found.")
        return await _assemble_response(conn, recipe_id, caller_user_id=user_id)


async def replace(
    *, recipe_id: int, user_id: int, body: RecipeCreate
) -> dict:
    async with transaction() as conn:
        await _require_owner(conn, recipe_id, user_id)

        products = await _validate_products(conn, body)

        await recipes_dal.update_recipe_fields(
            conn,
            recipe_id=recipe_id,
            name=body.name,
            description=body.description,
            image_filename=body.image_filename,
        )
        await recipes_dal.delete_recipe_products(conn, recipe_id)
        await recipes_dal.insert_recipe_products(
            conn, recipe_id=recipe_id, products=products
        )
        return await _assemble_response(conn, recipe_id, caller_user_id=user_id)


async def delete(*, recipe_id: int, user_id: int) -> None:
    async with transaction() as conn:
        await _require_owner(conn, recipe_id, user_id)
        await recipes_dal.delete_recipe(conn, recipe_id)


async def copy(*, source_id: int, user_id: int) -> dict:
    async with transaction() as conn:
        source = await recipes_dal.get_recipe_with_products(conn, source_id)
        if source is None:
            raise NotFoundError(f"Recipe {source_id} not found.")

        new = await recipes_dal.insert_recipe(
            conn,
            name=source["name"],
            description=source["description"],
            image_filename=source["image_filename"],
            created_by_user_id=user_id,
        )
        cloned_products = [
            {
                "product_id": p["product_id"],
                "quantity_type": p["quantity_type"],
                "amount": float(p["amount"]),
            }
            for p in source["products"]
        ]
        await recipes_dal.insert_recipe_products(
            conn, recipe_id=new["id"], products=cloned_products
        )
        return await _assemble_response(conn, new["id"], caller_user_id=user_id)


async def list_recipes(
    *,
    user_id: int,
    scope: Scope,
    q: str | None,
    cursor_token: str | None,
    limit: int,
) -> dict:
    """Return `{items, next_cursor}` for the requested scope."""
    async with read_only() as conn:
        if scope == "search":
            assert q is not None and q != ""
            cursor: tuple[float, int] | None = (
                cursor_svc.decode_search(cursor_token)
                if cursor_token is not None
                else None
            )
            rows = await recipes_dal.list_search(
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

        chrono_cursor: tuple[Any, int] | None = (
            cursor_svc.decode_chronological(cursor_token)
            if cursor_token is not None
            else None
        )
        if scope == "mine":
            rows = await recipes_dal.list_mine(
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
            rows = await recipes_dal.list_starred(
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

        raise InvalidCursorError(f"unknown scope: {scope!r}")
