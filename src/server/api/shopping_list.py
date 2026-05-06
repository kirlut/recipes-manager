"""Shopping-list endpoint: POST /shopping-list.

See `api_spec.md` §9.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import current_user
from api.schemas.shopping_list import (
    ShoppingListRequest,
    ShoppingListResponse,
)
from services import shopping_list as shopping_list_service

router = APIRouter()


@router.post("/shopping-list", response_model=ShoppingListResponse)
async def compute_shopping_list(
    body: ShoppingListRequest,
    user: dict = Depends(current_user),
) -> ShoppingListResponse:
    return await shopping_list_service.compute(
        user_id=user["id"], body=body
    )
