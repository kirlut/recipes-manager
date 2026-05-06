"""Product + product_nutrition_facts accessors. SQLAlchemy Core only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    and_,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.ext.asyncio import AsyncConnection

from dal.nutrition_fact_types import nutrition_fact_types_table
from dal.stars import product_stars_table
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


async def is_starred_by(
    conn: AsyncConnection, *, user_id: int, product_id: int
) -> bool:
    """Per-caller star check used to populate `starred_by_me` on detail
    responses (`api_spec.md` §3.5)."""
    s = product_stars_table
    stmt = select(s.c.user_id).where(
        s.c.user_id == user_id, s.c.product_id == product_id
    )
    return (await conn.execute(stmt)).first() is not None


def _list_item_columns(caller_user_id: int):
    """Columns shared by all three list query builders.

    Yields rows shaped for `ProductListItem` (no embedded nutrition
    facts; per `api_spec.md` §6.6) plus the per-caller `starred_by_me`
    flag computed by an EXISTS subquery against `product_stars`.

    The EXISTS subquery is explicitly correlated with `products` only —
    when the outer query is `scope=starred` it also has `product_stars`
    in its FROM clause, and without an explicit `correlate()` SQLAlchemy
    would auto-correlate the inner `product_stars` reference too,
    leaving the subquery with no FROM clauses (`InvalidRequestError`).
    """
    p = products_table
    u = users_table
    s = product_stars_table
    starred_by_me = (
        select(s.c.user_id)
        .select_from(s)
        .where(s.c.user_id == caller_user_id, s.c.product_id == p.c.id)
        .correlate(p)
        .exists()
    )
    return [
        p.c.id,
        p.c.name,
        p.c.image_filename,
        p.c.import_source,
        p.c.created_at,
        u.c.id.label("user_id"),
        u.c.username,
        u.c.full_name,
        starred_by_me.label("starred_by_me"),
    ]


def _row_to_list_item(row: Any) -> dict:
    """Shape a list-query row into the `ProductListItem` dict."""
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
        "starred_by_me": bool(row["starred_by_me"]),
    }


async def list_mine(
    conn: AsyncConnection,
    *,
    user_id: int,
    cursor: tuple[datetime, int] | None,
    limit: int,
) -> list[dict]:
    """Products owned by `user_id`, newest-first.

    Sort: `(created_at DESC, id DESC)` per `api_spec.md` §5.3 / §6.6.

    Fetches `limit + 1` rows so the caller can detect whether a `next`
    page exists.
    """
    p = products_table
    u = users_table
    join = p.outerjoin(u, p.c.created_by_user_id == u.c.id)
    where = [p.c.created_by_user_id == user_id]
    if cursor is not None:
        c_at, c_id = cursor
        where.append(
            or_(
                p.c.created_at < c_at,
                and_(p.c.created_at == c_at, p.c.id < c_id),
            )
        )
    stmt = (
        select(*_list_item_columns(user_id))
        .select_from(join)
        .where(*where)
        .order_by(p.c.created_at.desc(), p.c.id.desc())
        .limit(limit + 1)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return [_row_to_list_item(r) for r in rows]


async def list_starred(
    conn: AsyncConnection,
    *,
    user_id: int,
    cursor: tuple[datetime, int] | None,
    limit: int,
) -> list[dict]:
    """Products starred by `user_id`, most-recently-starred first.

    Sort: `(product_stars.created_at DESC, product_stars.product_id DESC)`
    per `db_schema.md` §5.3.
    """
    p = products_table
    u = users_table
    s = product_stars_table
    join = (
        s.join(p, s.c.product_id == p.c.id)
        .outerjoin(u, p.c.created_by_user_id == u.c.id)
    )
    where = [s.c.user_id == user_id]
    if cursor is not None:
        c_at, c_id = cursor
        where.append(
            or_(
                s.c.created_at < c_at,
                and_(s.c.created_at == c_at, s.c.product_id < c_id),
            )
        )
    stmt = (
        select(*_list_item_columns(user_id), s.c.created_at.label("star_created_at"))
        .select_from(join)
        .where(*where)
        .order_by(s.c.created_at.desc(), s.c.product_id.desc())
        .limit(limit + 1)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    items: list[dict] = []
    for r in rows:
        item = _row_to_list_item(r)
        # By definition every row in this query is starred by the caller.
        item["starred_by_me"] = True
        item["_star_created_at"] = r["star_created_at"]
        items.append(item)
    return items


async def list_search(
    conn: AsyncConnection,
    *,
    user_id: int,
    q: str,
    threshold: float,
    cursor: tuple[float, int] | None,
    limit: int,
) -> list[dict]:
    """Products matching `q` by trigram similarity above `threshold`.

    Sort: `(similarity DESC, id ASC)` per `api_spec.md` §5.3 / §6.6.
    Subsequent pages must satisfy `(similarity, id) "after"
    (cursor_sim, cursor_id)` with the asymmetric ordering — strictly
    less similarity, OR equal similarity with strictly greater id.
    """
    p = products_table
    u = users_table
    similarity = func.similarity(p.c.name, q)
    join = p.outerjoin(u, p.c.created_by_user_id == u.c.id)
    where = [similarity >= threshold]
    if cursor is not None:
        c_sim, c_id = cursor
        where.append(
            or_(
                similarity < c_sim,
                and_(similarity == c_sim, p.c.id > c_id),
            )
        )
    stmt = (
        select(*_list_item_columns(user_id), similarity.label("similarity"))
        .select_from(join)
        .where(*where)
        .order_by(similarity.desc(), p.c.id.asc())
        .limit(limit + 1)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    items: list[dict] = []
    for r in rows:
        item = _row_to_list_item(r)
        item["_similarity"] = float(r["similarity"])
        items.append(item)
    return items
