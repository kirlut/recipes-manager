"""Product request / response models. See `api_spec.md` §3.4, §3.5, §6."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas.users import UserRef, ZDatetime


class ProductNutritionFactCreate(BaseModel):
    nutrition_fact_id: int
    quantity_type: Literal["weight", "volume"]
    amount: float = Field(ge=0)


class ProductCreate(BaseModel):
    name: str = Field(max_length=200)
    image_filename: str | None = None
    nutrition_facts: list[ProductNutritionFactCreate] = Field(default_factory=list)

    @field_validator("name", mode="after")
    @classmethod
    def _strip_and_require_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty after trimming")
        return stripped


class ProductNutritionFact(BaseModel):
    nutrition_fact_id: int
    nutrition_fact_name: str
    unit: str
    quantity_type: Literal["weight", "volume"]
    amount: float


class Product(BaseModel):
    id: int
    name: str
    image_filename: str | None
    created_by: UserRef
    import_source: str | None
    created_at: ZDatetime
    starred_by_me: bool
    nutrition_facts: list[ProductNutritionFact]
