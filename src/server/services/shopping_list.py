"""Shopping-list orchestration: validate accessibility, aggregate, sort.

See `api_spec.md` §9.1 (request/response shape, sort order, unit
derivation), §13 (per-product aggregation formula).
"""

from __future__ import annotations

from api.errors import ServiceValidationError
from api.schemas.shopping_list import (
    ShoppingListRequest,
    ShoppingListResponse,
    ShoppingListResponseItem,
)
from dal import shopping_list as shopping_list_dal
from dal.connections import read_only


def _unit_for(quantity_type: str) -> str:
    return "g" if quantity_type == "weight" else "ml"


async def compute(
    *, user_id: int, body: ShoppingListRequest
) -> ShoppingListResponse:
    # 1. Duplicate recipe_id is a semantic 422.
    seen: dict[int, int] = {}
    duplicates: list[tuple[int, int]] = []
    for i, item in enumerate(body.items):
        if item.recipe_id in seen:
            duplicates.append((i, item.recipe_id))
        else:
            seen[item.recipe_id] = i
    if duplicates:
        raise ServiceValidationError(
            "Duplicate recipe_id in items.",
            violations=[
                {
                    "field": f"items.{i}.recipe_id",
                    "message": f"duplicate recipe_id {rid}",
                }
                for i, rid in duplicates
            ],
        )

    requested_ids = {item.recipe_id for item in body.items}

    async with read_only() as conn:
        # 2. Accessibility check (covers unknown ids and not-owned/not-starred).
        access = await shopping_list_dal.fetch_recipe_accessibility(
            conn, recipe_ids=requested_ids, user_id=user_id
        )
        violations = [
            {
                "field": f"items.{i}.recipe_id",
                "message": (
                    f"recipe_id {item.recipe_id} is not accessible: "
                    f"caller must own or have starred the recipe."
                ),
            }
            for i, item in enumerate(body.items)
            if not access.get(item.recipe_id, False)
        ]
        if violations:
            raise ServiceValidationError(
                "One or more recipes are not accessible.",
                violations=violations,
            )

        # 3. Fetch all recipe_products in one query.
        rows = await shopping_list_dal.fetch_recipe_products_for_recipes(
            conn, recipe_ids=requested_ids
        )

    # 4. Aggregate by (product_id, quantity_type), scaled by per-recipe servings.
    servings_by_recipe = {
        item.recipe_id: float(item.servings) for item in body.items
    }
    totals: dict[tuple[int, str], dict] = {}
    for r in rows:
        key = (r["product_id"], r["quantity_type"])
        contribution = float(r["amount"]) * servings_by_recipe[r["recipe_id"]]
        entry = totals.get(key)
        if entry is None:
            totals[key] = {
                "product_id": r["product_id"],
                "product_name": r["product_name"],
                "product_image_filename": r["product_image_filename"],
                "quantity_type": r["quantity_type"],
                "unit": _unit_for(r["quantity_type"]),
                "total_amount": contribution,
            }
        else:
            entry["total_amount"] += contribution

    # 5. Sort by (product_name ASC, quantity_type ASC). "volume" < "weight".
    items_out = sorted(
        totals.values(),
        key=lambda e: (e["product_name"], e["quantity_type"]),
    )
    return ShoppingListResponse(
        items=[ShoppingListResponseItem(**item) for item in items_out]
    )
