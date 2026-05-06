"""Star/unstar accessors for `product_stars` and `recipe_stars`.

Both tables are junction tables with composite PK `(user_id, *_id)` plus
a `created_at` timestamp used as the sort key for `scope=starred`
listings. Inserts use `ON CONFLICT DO NOTHING` so the API layer can
guarantee idempotent star semantics without a pre-check.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    Table,
    delete,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

_metadata = MetaData()

product_stars_table = Table(
    "product_stars",
    _metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column("product_id", BigInteger, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

recipe_stars_table = Table(
    "recipe_stars",
    _metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column("recipe_id", BigInteger, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


async def add_product_star(
    conn: AsyncConnection, *, user_id: int, product_id: int
) -> None:
    stmt = pg_insert(product_stars_table).values(
        user_id=user_id, product_id=product_id
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["user_id", "product_id"]
    )
    await conn.execute(stmt)


async def remove_product_star(
    conn: AsyncConnection, *, user_id: int, product_id: int
) -> None:
    stmt = delete(product_stars_table).where(
        product_stars_table.c.user_id == user_id,
        product_stars_table.c.product_id == product_id,
    )
    await conn.execute(stmt)


async def add_recipe_star(
    conn: AsyncConnection, *, user_id: int, recipe_id: int
) -> None:
    stmt = pg_insert(recipe_stars_table).values(
        user_id=user_id, recipe_id=recipe_id
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["user_id", "recipe_id"]
    )
    await conn.execute(stmt)


async def remove_recipe_star(
    conn: AsyncConnection, *, user_id: int, recipe_id: int
) -> None:
    stmt = delete(recipe_stars_table).where(
        recipe_stars_table.c.user_id == user_id,
        recipe_stars_table.c.recipe_id == recipe_id,
    )
    await conn.execute(stmt)
