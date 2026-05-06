"""User row accessors. SQLAlchemy Core only."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncConnection

_metadata = MetaData()

users_table = Table(
    "users",
    _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("username", String, nullable=False),
    Column("full_name", String, nullable=True),
    Column("pwd_hash", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_RETURN_COLS = (
    users_table.c.id,
    users_table.c.username,
    users_table.c.full_name,
    users_table.c.created_at,
)


async def create_user(
    conn: AsyncConnection,
    *,
    username: str,
    full_name: str | None,
    pwd_hash: str,
) -> dict:
    """Insert a user. Raises `IntegrityError` on duplicate username."""
    stmt = (
        insert(users_table)
        .values(username=username, full_name=full_name, pwd_hash=pwd_hash)
        .returning(*_RETURN_COLS)
    )
    row = (await conn.execute(stmt)).mappings().one()
    return dict(row)


async def get_user_by_username(conn: AsyncConnection, username: str) -> dict | None:
    stmt = select(
        users_table.c.id,
        users_table.c.username,
        users_table.c.full_name,
        users_table.c.pwd_hash,
        users_table.c.created_at,
    ).where(users_table.c.username == username)
    row = (await conn.execute(stmt)).mappings().first()
    return dict(row) if row else None


async def get_user_by_id(conn: AsyncConnection, user_id: int) -> dict | None:
    stmt = select(*_RETURN_COLS).where(users_table.c.id == user_id)
    row = (await conn.execute(stmt)).mappings().first()
    return dict(row) if row else None
