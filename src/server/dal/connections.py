"""Async DB connection helpers built on the shared engine.

`transaction()` wraps work that mutates DB state: opens a connection inside
`engine.begin()`, commits on clean exit, rolls back on exception.

`read_only()` is for SELECT-only paths: opens a plain connection and never
commits.

Both yield a SQLAlchemy `AsyncConnection`; callers use SQLAlchemy Core
constructs against it (no ORM).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection

from dal.db import get_engine


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncConnection]:
    async with get_engine().begin() as conn:
        yield conn


@asynccontextmanager
async def read_only() -> AsyncIterator[AsyncConnection]:
    async with get_engine().connect() as conn:
        yield conn
