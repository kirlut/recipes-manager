"""Shopping-list DB accessors. SQLAlchemy Core only.

See `api_spec.md` §9.1 (request/response shape) and §13 (aggregation
formula). The endpoint reads-only; both helpers run inside a single
`read_only()` connection in the service layer.
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from dal.products import products_table
from dal.recipes import recipe_products_table, recipes_table
from dal.stars import recipe_stars_table


async def fetch_recipe_accessibility(
    conn: AsyncConnection,
    *,
    recipe_ids: set[int],
    user_id: int,
) -> dict[int, bool]:
    """Return `{recipe_id: accessible}` for every recipe id in `recipe_ids`.

    A recipe is accessible iff it exists AND
    (`created_by_user_id == user_id` OR the caller has starred it).
    Recipes that don't exist are absent from the result; the service
    layer treats absence as "not accessible".
    """
    if not recipe_ids:
        return {}

    r = recipes_table
    s = recipe_stars_table
    join = r.outerjoin(
        s, and_(s.c.recipe_id == r.c.id, s.c.user_id == user_id)
    )
    stmt = (
        select(
            r.c.id,
            r.c.created_by_user_id,
            s.c.user_id.label("star_user_id"),
        )
        .select_from(join)
        .where(r.c.id.in_(recipe_ids))
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return {
        row["id"]: (
            row["created_by_user_id"] == user_id
            or row["star_user_id"] is not None
        )
        for row in rows
    }


async def fetch_recipe_products_for_recipes(
    conn: AsyncConnection,
    *,
    recipe_ids: set[int],
) -> list[dict]:
    """Fetch `recipe_products` joined to `products` for the given recipes.

    Returns rows shaped as:
        {"recipe_id", "product_id", "product_name",
         "product_image_filename", "quantity_type", "amount"}

    Returns an empty list when `recipe_ids` is empty or no recipe has
    any products.
    """
    if not recipe_ids:
        return []
    rp = recipe_products_table
    p = products_table
    join = rp.join(p, rp.c.product_id == p.c.id)
    stmt = (
        select(
            rp.c.recipe_id,
            rp.c.product_id,
            p.c.name.label("product_name"),
            p.c.image_filename.label("product_image_filename"),
            rp.c.quantity_type,
            rp.c.amount,
        )
        .select_from(join)
        .where(rp.c.recipe_id.in_(recipe_ids))
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


__all__ = [
    "fetch_recipe_accessibility",
    "fetch_recipe_products_for_recipes",
]
