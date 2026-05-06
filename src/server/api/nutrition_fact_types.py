"""GET /nutrition-fact-types — read-only seeded list. See api_spec.md §11."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import current_user
from api.schemas.nutrition_fact_types import NutritionFactType, NutritionFactTypeList
from services import nutrition_fact_types as nft_service

router = APIRouter()


@router.get("/nutrition-fact-types", response_model=NutritionFactTypeList)
async def list_nutrition_fact_types(
    _user: dict = Depends(current_user),
) -> NutritionFactTypeList:
    rows = await nft_service.list_all()
    return NutritionFactTypeList(
        items=[NutritionFactType(**row) for row in rows]
    )
