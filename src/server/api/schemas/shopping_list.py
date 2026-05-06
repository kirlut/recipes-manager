"""Shopping-list request / response models. See `api_spec.md` §9.1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ShoppingListRequestItem(BaseModel):
    recipe_id: int
    servings: float = Field(gt=0)


class ShoppingListRequest(BaseModel):
    items: list[ShoppingListRequestItem] = Field(min_length=1)


class ShoppingListResponseItem(BaseModel):
    product_id: int
    product_name: str
    product_image_filename: str | None
    quantity_type: Literal["weight", "volume"]
    unit: str
    total_amount: float


class ShoppingListResponse(BaseModel):
    items: list[ShoppingListResponseItem]
