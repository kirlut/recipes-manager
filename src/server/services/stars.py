"""Star/unstar orchestration. Idempotent per `api_spec.md` §8."""

from __future__ import annotations

from api.errors import NotFoundError
from dal import products as products_dal
from dal import recipes as recipes_dal
from dal import stars as stars_dal
from dal.connections import transaction


async def star_product(*, user_id: int, product_id: int) -> None:
    async with transaction() as conn:
        if not await products_dal.product_exists(conn, product_id):
            raise NotFoundError(f"Product {product_id} not found.")
        await stars_dal.add_product_star(
            conn, user_id=user_id, product_id=product_id
        )


async def unstar_product(*, user_id: int, product_id: int) -> None:
    async with transaction() as conn:
        if not await products_dal.product_exists(conn, product_id):
            raise NotFoundError(f"Product {product_id} not found.")
        await stars_dal.remove_product_star(
            conn, user_id=user_id, product_id=product_id
        )


async def star_recipe(*, user_id: int, recipe_id: int) -> None:
    async with transaction() as conn:
        if not await recipes_dal.recipe_exists(conn, recipe_id):
            raise NotFoundError(f"Recipe {recipe_id} not found.")
        await stars_dal.add_recipe_star(
            conn, user_id=user_id, recipe_id=recipe_id
        )


async def unstar_recipe(*, user_id: int, recipe_id: int) -> None:
    async with transaction() as conn:
        if not await recipes_dal.recipe_exists(conn, recipe_id):
            raise NotFoundError(f"Recipe {recipe_id} not found.")
        await stars_dal.remove_recipe_star(
            conn, user_id=user_id, recipe_id=recipe_id
        )
