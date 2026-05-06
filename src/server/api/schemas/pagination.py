"""List-item models for paginated `/products` and `/recipes` responses.

The full `Product` and `Recipe` schemas (in `api.schemas.products` /
`api.schemas.recipes`) embed `nutrition_facts`, `products`, and
`nutrition_totals_per_serving`. Per `api_spec.md` §6.6 / §7.6 those are
omitted from list responses; this module declares the lighter shape.

The pagination envelope itself is built as a plain dict in the API layer
so the `next` key can be omitted entirely on the last page (per §5.2),
rather than serialized as `null`.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.users import UserRef, ZDatetime


class ProductListItem(BaseModel):
    id: int
    name: str
    image_filename: str | None
    created_by: UserRef | None
    import_source: str | None
    created_at: ZDatetime
    starred_by_me: bool


class RecipeListItem(BaseModel):
    id: int
    name: str
    image_filename: str | None
    created_by: UserRef | None
    import_source: str | None
    created_at: ZDatetime
    starred_by_me: bool
