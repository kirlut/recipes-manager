"""Recipe + recipe_products accessors. SQLAlchemy Core only."""

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
from dal.products import product_nutrition_facts_table, products_table
from dal.stars import recipe_stars_table
from dal.users import users_table

_metadata = MetaData()

# DB type already created by schema.sql; tell SQLAlchemy not to emit DDL.
_quantity_type = PgEnum(
    "weight", "volume", name="quantity_type", create_type=False
)

recipes_table = Table(
    "recipes",
    _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("image_filename", String, nullable=True),
    Column("created_by_user_id", BigInteger, nullable=True),
    Column("import_source", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

recipe_products_table = Table(
    "recipe_products",
    _metadata,
    Column("recipe_id", BigInteger, primary_key=True),
    Column("product_id", BigInteger, primary_key=True),
    Column("quantity_type", _quantity_type, nullable=False),
    Column("amount", Float, nullable=False),
)


async def insert_recipe(
    conn: AsyncConnection,
    *,
    name: str,
    description: str | None,
    image_filename: str | None,
    created_by_user_id: int,
) -> dict:
    """Insert a user-owned recipe row. `import_source` is forced to NULL
    so the `recipes_origin_xor` CHECK constraint is satisfied."""
    stmt = (
        insert(recipes_table)
        .values(
            name=name,
            description=description,
            image_filename=image_filename,
            created_by_user_id=created_by_user_id,
            import_source=None,
        )
        .returning(
            recipes_table.c.id,
            recipes_table.c.name,
            recipes_table.c.description,
            recipes_table.c.image_filename,
            recipes_table.c.created_by_user_id,
            recipes_table.c.import_source,
            recipes_table.c.created_at,
        )
    )
    row = (await conn.execute(stmt)).mappings().one()
    return dict(row)


async def insert_recipe_products(
    conn: AsyncConnection,
    *,
    recipe_id: int,
    products: list[dict[str, Any]],
) -> None:
    if not products:
        return
    rows = [
        {
            "recipe_id": recipe_id,
            "product_id": p["product_id"],
            "quantity_type": p["quantity_type"],
            "amount": p["amount"],
        }
        for p in products
    ]
    await conn.execute(insert(recipe_products_table), rows)


async def update_recipe_fields(
    conn: AsyncConnection,
    *,
    recipe_id: int,
    name: str,
    description: str | None,
    image_filename: str | None,
) -> None:
    stmt = (
        update(recipes_table)
        .where(recipes_table.c.id == recipe_id)
        .values(name=name, description=description, image_filename=image_filename)
    )
    await conn.execute(stmt)


async def delete_recipe_products(conn: AsyncConnection, recipe_id: int) -> None:
    stmt = delete(recipe_products_table).where(
        recipe_products_table.c.recipe_id == recipe_id
    )
    await conn.execute(stmt)


async def delete_recipe(conn: AsyncConnection, recipe_id: int) -> int:
    stmt = delete(recipes_table).where(recipes_table.c.id == recipe_id)
    result = await conn.execute(stmt)
    return result.rowcount or 0


async def recipe_exists(conn: AsyncConnection, recipe_id: int) -> bool:
    stmt = select(recipes_table.c.id).where(recipes_table.c.id == recipe_id)
    return (await conn.execute(stmt)).first() is not None


async def get_recipe_owner(conn: AsyncConnection, recipe_id: int) -> int | None:
    """Return `created_by_user_id` for a recipe, or `None` if the recipe
    does not exist. Imported recipes have NULL owner; callers distinguish
    "no row" from "no owner" via `recipe_exists`.
    """
    stmt = select(recipes_table.c.created_by_user_id).where(
        recipes_table.c.id == recipe_id
    )
    row = (await conn.execute(stmt)).first()
    if row is None:
        return None
    return row[0]


async def get_recipe_with_products(
    conn: AsyncConnection, recipe_id: int
) -> dict | None:
    """Fetch a recipe joined to its creator and embedded recipe-products.

    Returns a dict shaped to feed straight into the `Recipe` schema
    (less `nutrition_totals_per_serving` + `starred_by_me`, which are
    layered on by the service):
        {
          "id", "name", "description", "image_filename",
          "created_by": {"id","username","full_name"} | None,
          "import_source", "created_at",
          "products": [
              {"product_id","product_name","product_image_filename",
               "quantity_type","amount"}, ...
          ],
        }
    or `None` if no such recipe exists.
    """
    r = recipes_table
    u = users_table
    join = r.outerjoin(u, r.c.created_by_user_id == u.c.id)
    stmt = (
        select(
            r.c.id,
            r.c.name,
            r.c.description,
            r.c.image_filename,
            r.c.import_source,
            r.c.created_at,
            u.c.id.label("user_id"),
            u.c.username,
            u.c.full_name,
        )
        .select_from(join)
        .where(r.c.id == recipe_id)
    )
    row = (await conn.execute(stmt)).mappings().first()
    if row is None:
        return None

    products = await _list_products(conn, recipe_id)

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
        "description": row["description"],
        "image_filename": row["image_filename"],
        "created_by": created_by,
        "import_source": row["import_source"],
        "created_at": row["created_at"],
        "products": products,
    }


async def _list_products(conn: AsyncConnection, recipe_id: int) -> list[dict]:
    rp = recipe_products_table
    p = products_table
    join = rp.join(p, rp.c.product_id == p.c.id)
    stmt = (
        select(
            rp.c.product_id,
            p.c.name.label("product_name"),
            p.c.image_filename.label("product_image_filename"),
            rp.c.quantity_type,
            rp.c.amount,
        )
        .select_from(join)
        .where(rp.c.recipe_id == recipe_id)
        .order_by(rp.c.product_id)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def existing_product_ids(
    conn: AsyncConnection, ids: set[int]
) -> set[int]:
    """Return the subset of `ids` that exist in the `products` table."""
    if not ids:
        return set()
    stmt = select(products_table.c.id).where(products_table.c.id.in_(ids))
    return {r[0] for r in (await conn.execute(stmt)).all()}


async def is_starred_by(
    conn: AsyncConnection, *, user_id: int, recipe_id: int
) -> bool:
    """Per-caller star check used to populate `starred_by_me` on detail
    responses (`api_spec.md` §3.7)."""
    s = recipe_stars_table
    stmt = select(s.c.user_id).where(
        s.c.user_id == user_id, s.c.recipe_id == recipe_id
    )
    return (await conn.execute(stmt)).first() is not None


def _list_item_columns(caller_user_id: int):
    """Columns shared by the three list query builders.

    Yields rows shaped for `RecipeListItem` (no embedded products /
    totals; per `api_spec.md` §7.6) plus the per-caller `starred_by_me`
    flag computed by an EXISTS subquery against `recipe_stars`.

    Same correlation guard as in `dal/products.py`: when the outer
    query is `scope=starred`, `recipe_stars` is already in the FROM
    clause and SQLAlchemy would otherwise auto-correlate the inner
    reference, leaving the subquery without a FROM.
    """
    r = recipes_table
    u = users_table
    s = recipe_stars_table
    starred_by_me = (
        select(s.c.user_id)
        .select_from(s)
        .where(s.c.user_id == caller_user_id, s.c.recipe_id == r.c.id)
        .correlate(r)
        .exists()
    )
    return [
        r.c.id,
        r.c.name,
        r.c.image_filename,
        r.c.import_source,
        r.c.created_at,
        u.c.id.label("user_id"),
        u.c.username,
        u.c.full_name,
        starred_by_me.label("starred_by_me"),
    ]


def _row_to_list_item(row: Any) -> dict:
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
    r = recipes_table
    u = users_table
    join = r.outerjoin(u, r.c.created_by_user_id == u.c.id)
    where = [r.c.created_by_user_id == user_id]
    if cursor is not None:
        c_at, c_id = cursor
        where.append(
            or_(
                r.c.created_at < c_at,
                and_(r.c.created_at == c_at, r.c.id < c_id),
            )
        )
    stmt = (
        select(*_list_item_columns(user_id))
        .select_from(join)
        .where(*where)
        .order_by(r.c.created_at.desc(), r.c.id.desc())
        .limit(limit + 1)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return [_row_to_list_item(row) for row in rows]


async def list_starred(
    conn: AsyncConnection,
    *,
    user_id: int,
    cursor: tuple[datetime, int] | None,
    limit: int,
) -> list[dict]:
    r = recipes_table
    u = users_table
    s = recipe_stars_table
    join = (
        s.join(r, s.c.recipe_id == r.c.id)
        .outerjoin(u, r.c.created_by_user_id == u.c.id)
    )
    where = [s.c.user_id == user_id]
    if cursor is not None:
        c_at, c_id = cursor
        where.append(
            or_(
                s.c.created_at < c_at,
                and_(s.c.created_at == c_at, s.c.recipe_id < c_id),
            )
        )
    stmt = (
        select(
            *_list_item_columns(user_id),
            s.c.created_at.label("star_created_at"),
        )
        .select_from(join)
        .where(*where)
        .order_by(s.c.created_at.desc(), s.c.recipe_id.desc())
        .limit(limit + 1)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    items: list[dict] = []
    for row in rows:
        item = _row_to_list_item(row)
        item["starred_by_me"] = True
        item["_star_created_at"] = row["star_created_at"]
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
    r = recipes_table
    u = users_table
    similarity = func.similarity(r.c.name, q)
    join = r.outerjoin(u, r.c.created_by_user_id == u.c.id)
    where = [similarity >= threshold]
    if cursor is not None:
        c_sim, c_id = cursor
        where.append(
            or_(
                similarity < c_sim,
                and_(similarity == c_sim, r.c.id > c_id),
            )
        )
    stmt = (
        select(*_list_item_columns(user_id), similarity.label("similarity"))
        .select_from(join)
        .where(*where)
        .order_by(similarity.desc(), r.c.id.asc())
        .limit(limit + 1)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    items: list[dict] = []
    for row in rows:
        item = _row_to_list_item(row)
        item["_similarity"] = float(row["similarity"])
        items.append(item)
    return items


async def fetch_facts_for_pairs(
    conn: AsyncConnection,
    pairs: list[tuple[int, str]],
) -> list[dict]:
    """Fetch all `product_nutrition_facts` rows matching any of the given
    `(product_id, quantity_type)` pairs, joined to `nutrition_fact_types`
    for `name` and `unit`.

    Returns rows shaped as:
        {"product_id", "quantity_type", "nutrition_fact_id",
         "nutrition_fact_name", "unit", "amount"}

    Used both for quantity-type-mismatch validation and totals
    computation (one DB round-trip serves both purposes).
    """
    if not pairs:
        return []
    pnf = product_nutrition_facts_table
    nft = nutrition_fact_types_table
    join = pnf.join(nft, pnf.c.nutrition_fact_id == nft.c.id)
    pair_filter = or_(
        *(
            and_(pnf.c.product_id == pid, pnf.c.quantity_type == qt)
            for pid, qt in pairs
        )
    )
    stmt = (
        select(
            pnf.c.product_id,
            pnf.c.quantity_type,
            pnf.c.nutrition_fact_id,
            nft.c.name.label("nutrition_fact_name"),
            nft.c.unit,
            pnf.c.amount,
            nft.c.id.label("nft_order_id"),
        )
        .select_from(join)
        .where(pair_filter)
        .order_by(nft.c.id, pnf.c.product_id)
    )
    rows = (await conn.execute(stmt)).mappings().all()
    return [
        {
            "product_id": r["product_id"],
            "quantity_type": r["quantity_type"],
            "nutrition_fact_id": r["nutrition_fact_id"],
            "nutrition_fact_name": r["nutrition_fact_name"],
            "unit": r["unit"],
            "amount": r["amount"],
        }
        for r in rows
    ]
