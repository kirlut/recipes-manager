"""Nutrition-fact-types service. Thin pass-through over the DAL."""

from __future__ import annotations

from dal import nutrition_fact_types as nft_dal
from dal.connections import read_only


async def list_all() -> list[dict]:
    async with read_only() as conn:
        return await nft_dal.list_all(conn)
