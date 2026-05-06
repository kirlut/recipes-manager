"""Recipe request / response models. See `api_spec.md` §3.6, §3.7, §7."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas.users import UserRef, ZDatetime


class RecipeProductCreate(BaseModel):
    product_id: int
    quantity_type: Literal["weight", "volume"]
    amount: float = Field(gt=0)


class RecipeCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    image_filename: str | None = None
    products: list[RecipeProductCreate] = Field(default_factory=list)

    @field_validator("name", mode="after")
    @classmethod
    def _strip_and_require_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty after trimming")
        return stripped


class RecipeProduct(BaseModel):
    product_id: int
    product_name: str
    product_image_filename: str | None
    quantity_type: Literal["weight", "volume"]
    amount: float


class NutritionTotal(BaseModel):
    nutrition_fact_id: int
    nutrition_fact_name: str
    unit: str
    amount: float


class Recipe(BaseModel):
    id: int
    name: str
    description: str | None
    image_filename: str | None
    created_by: UserRef
    import_source: str | None
    created_at: ZDatetime
    starred_by_me: bool
    products: list[RecipeProduct]
    nutrition_totals_per_serving: list[NutritionTotal]
