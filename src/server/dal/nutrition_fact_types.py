"""Nutrition-fact-types accessors. Read-only seeded reference data."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncConnection

_metadata = MetaData()

nutrition_fact_types_table = Table(
    "nutrition_fact_types",
    _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", String, nullable=False),
    Column("unit", String, nullable=False),
)


async def list_all(conn: AsyncConnection) -> list[dict]:
    stmt = select(
        nutrition_fact_types_table.c.id,
        nutrition_fact_types_table.c.name,
        nutrition_fact_types_table.c.unit,
    ).order_by(nutrition_fact_types_table.c.id)
    rows = (await conn.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def find_unknown_ids(conn: AsyncConnection, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    stmt = select(nutrition_fact_types_table.c.id).where(
        nutrition_fact_types_table.c.id.in_(ids)
    )
    found = {r[0] for r in (await conn.execute(stmt)).all()}
    return ids - found
