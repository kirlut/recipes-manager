"""Nutrition-fact-types response models. See `api_spec.md` §3.3, §11."""

from __future__ import annotations

from pydantic import BaseModel


class NutritionFactType(BaseModel):
    id: int
    name: str
    unit: str


class NutritionFactTypeList(BaseModel):
    items: list[NutritionFactType]
