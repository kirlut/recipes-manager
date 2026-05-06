"""Product + product_nutrition_facts accessors. SQLAlchemy Core only."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.ext.asyncio import AsyncConnection

from dal.nutrition_fact_types import nutrition_fact_types_table
from dal.users import users_table

_metadata = MetaData()

# DB type already created by schema.sql; tell SQLAlchemy not to emit DDL.
_quantity_type = PgEnum(
    "weight", "volume", name="quantity_type", create_type=False
)

products_table = Table(
    "products",
    _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", String, nullable=False),
    Column("image_filename", String, nullable=True),
    Column("created_by_user_id", BigInteger, nullable=True),
    Column("import_source", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

product_nutrition_facts_table = Table(
    "product_nutrition_facts",
    _metadata,
    Column("product_id", BigInteger, primary_key=True),
    Column("nutrition_fact_id", BigInteger, primary_key=True),
    Column("quantity_type", _quantity_type, primary_key=True),
    Column("amount", Float, nullable=False),
)


async def insert_product(
    conn: AsyncConnection,
    *,
    name: str,
    image_filename: str | None,
    created_by_user_id: int,
) -> dict:
    """Insert a user-owned product row. `import_source` is forced to NULL
    so the `products_origin_xor` CHECK constraint is satisfied."""
    stmt = (
        insert(products_table)
        .values(
            name=name,
            image_filename=image_filename,
            created_by_user_id=created_by_user_id,
            import_source=None,
        )
        .returning(
            products_table.c.id,
            products_table.c.name,
            products_table.c.image_filename,
            products_table.c.created_by_user_id,
            products_table.c.import_source,
            products_table.c.created_at,
        )
    )
    row = (await conn.execute(stmt)).mappings().one()
    return dict(row)


async def insert_product_facts(
    conn: AsyncConnection,
    *,
    product_id: int,
    facts: list[dict[str, Any]],
) -> None:
    if not facts:
        return
    rows = [
        {
            "product_id": product_id,
            "nutrition_fact_id": f["nutrition_fact_id"],
            "quantity_type": f["quantity_type"],
            "amount": f["amount"],
        }
        for f in facts
    ]
    await conn.execute(insert(product_nutrition_facts_table), rows)


async def update_product_fields(
    conn: AsyncConnection,
    *,
    product_id: int,
    name: str,
    image_filename: str | None,
) -> None:
    stmt = (
        update(products_table)
        .where(products_table.c.id == product_id)
        .values(name=name, image_filename=image_filename)
    )
    await conn.execute(stmt)


async def delete_product_facts(conn: AsyncConnection, product_id: int) -> None:
    stmt = delete(product_nutrition_facts_table).where(
        product_nutrition_facts_table.c.product_id == product_id
    )
    await conn.execute(stmt)


async def delete_product(conn: AsyncConnection, product_id: int) -> int:
    """Delete the row by id. Returns row count (0 or 1)."""
    stmt = delete(products_table).where(products_table.c.id == product_id)
    result = await conn.execute(stmt)
    return result.rowcount or 0


async def get_product_owner(conn: AsyncConnection, product_id: int) -> int | None:
    """Return the `created_by_user_id` for a product, or `None` if the
    product does not exist. For imported products the owner is `NULL` so
    callers must distinguish "no row" from "no owner" via the row-existence
    check below.
    """
    stmt = select(
        products_table.c.id, products_table.c.created_by_user_id
    ).where(products_table.c.id == product_id)
    row = (await conn.execute(stmt)).first()
    if row is None:
        return None
    # row exists but may have NULL owner (imported); return owner as-is.
    return row[1]


async def product_exists(conn: AsyncConnection, product_id: int) -> bool:
    stmt = select(products_table.c.id).where(products_table.c.id == product_id)
    return (await conn.execute(stmt)).first() is not None


async def get_product_with_facts(
    conn: AsyncConnection, product_id: int
) -> dict | None:
    """Fetch a product joined to its creator and embedded nutrition facts.

    Returns a dict shaped to feed straight into `Product` schema:
        {
          "id": ..., "name": ..., "image_filename": ...,
          "created_by": {"id", "username", "full_name"} | None,
          "import_source": ...,
          "created_at": datetime,
          "nutrition_facts": [
              {"nutrition_fact_id", "nutrition_fact_name", "unit",
               "quantity_type", "amount"}, ...
          ],
        }
    or `None` if no such product exists.
    """
    p = products_table
    u = users_table
    join = p.outerjoin(u, p.c.created_by_user_id == u.c.id)
    stmt = (
        select(
            p.c.id,
            p.c.name,
            p.c.image_filename,
            p.c.import_source,
            p.c.created_at,
            u.c.id.label("user_id"),
            u.c.username,
            u.c.full_name,
        )
        .select_from(join)
        .where(p.c.id == product_id)
    )
    row = (await conn.execute(stmt)).mappings().first()
    if row is None:
        return None

    facts = await _list_facts(conn, product_id)

    created_by: dict | None
    if row["user_id"] is not None:
        created_by = {
            "id": row["user_id"],
            "username": row["username"],
            "full_name": row["full_name"],
        }
    else:
        created_by = None

    return {
        "id": row["id"],
        "name": row["name"],
        "image_filename": row["image_filename"],
        "created_by": created_by,
        "import_source": row["import_source"],
        "created_at": row["created_at"],
        "nutrition_facts": facts,
    }


async def _list_facts(conn: AsyncConnection, product_id: int) -> list[dict]:
    pnf = product_nutrition_facts_table
    nft = nutrition_fact_types_table
    join = pnf.join(nft, pnf.c.nutrition_fact_id == nft.c.id)
    stmt = (
        select(
            pnf.c.nutrition_fact_id,
            nft.c.name.label("nutrition_fact_name"),
            nft.c.unit,
            pnf.c.quantity_type,
            pnf.c.amount,
        )
        .select_from(join)
        .where(pnf.c.product_id == product_id)
        .order_by(pnf.c.nutrition_fact_id, pnf.c.quantity_type)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def list_facts(conn: AsyncConnection, product_id: int) -> list[dict]:
    """Public wrapper around _list_facts for the copy path."""
    return await _list_facts(conn, product_id)
