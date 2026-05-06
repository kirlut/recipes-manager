"""Recipe endpoints: POST/GET/PUT/DELETE /recipes and /recipes/{id}/copy.

See `api_spec.md` §7.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Response, status

from api.dependencies import current_user
from api.errors import RequestValidationFailedError
from api.schemas.pagination import RecipeListItem
from api.schemas.recipes import Recipe, RecipeCreate
from services import recipes as recipes_service
from services import stars as stars_service

router = APIRouter()


@router.post(
    "/recipes",
    status_code=status.HTTP_201_CREATED,
    response_model=Recipe,
)
async def create_recipe(
    body: RecipeCreate,
    response: Response,
    user: dict = Depends(current_user),
) -> Recipe:
    recipe = await recipes_service.create(user_id=user["id"], body=body)
    response.headers["Location"] = f"/recipes/{recipe['id']}"
    return Recipe(**recipe)


@router.get("/recipes")
async def list_recipes(
    scope: Literal["mine", "starred", "search"] = Query(...),
    q: str | None = Query(None, max_length=200),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
) -> dict:
    if scope == "search" and (q is None or q == ""):
        raise RequestValidationFailedError(
            "`q` is required and non-empty when scope=search.",
            violations=[{"field": "q", "message": "required when scope=search"}],
        )
    page = await recipes_service.list_recipes(
        user_id=user["id"],
        scope=scope,
        q=q,
        cursor_token=cursor,
        limit=limit,
    )
    items = [RecipeListItem(**item).model_dump(mode="json") for item in page["items"]]
    self_url = _build_url("/api/recipes", scope=scope, q=q, cursor=cursor, limit=limit)
    body: dict = {"items": items, "self": self_url}
    if page["next_cursor"] is not None:
        body["next"] = _build_url(
            "/api/recipes",
            scope=scope,
            q=q,
            cursor=page["next_cursor"],
            limit=limit,
        )
    return body


@router.get("/recipes/{recipe_id}", response_model=Recipe)
async def get_recipe(
    recipe_id: int,
    user: dict = Depends(current_user),
) -> Recipe:
    recipe = await recipes_service.get(recipe_id=recipe_id, user_id=user["id"])
    return Recipe(**recipe)


@router.put("/recipes/{recipe_id}", response_model=Recipe)
async def replace_recipe(
    recipe_id: int,
    body: RecipeCreate,
    user: dict = Depends(current_user),
) -> Recipe:
    recipe = await recipes_service.replace(
        recipe_id=recipe_id, user_id=user["id"], body=body
    )
    return Recipe(**recipe)


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: int,
    user: dict = Depends(current_user),
) -> Response:
    await recipes_service.delete(recipe_id=recipe_id, user_id=user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/recipes/{recipe_id}/copy",
    status_code=status.HTTP_201_CREATED,
    response_model=Recipe,
)
async def copy_recipe(
    recipe_id: int,
    response: Response,
    user: dict = Depends(current_user),
) -> Recipe:
    recipe = await recipes_service.copy(
        source_id=recipe_id, user_id=user["id"]
    )
    response.headers["Location"] = f"/recipes/{recipe['id']}"
    return Recipe(**recipe)


@router.put(
    "/recipes/{recipe_id}/star",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def star_recipe(
    recipe_id: int,
    user: dict = Depends(current_user),
) -> Response:
    await stars_service.star_recipe(user_id=user["id"], recipe_id=recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/recipes/{recipe_id}/star",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unstar_recipe(
    recipe_id: int,
    user: dict = Depends(current_user),
) -> Response:
    await stars_service.unstar_recipe(user_id=user["id"], recipe_id=recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _build_url(
    path: str,
    *,
    scope: str,
    q: str | None,
    cursor: str | None,
    limit: int,
) -> str:
    params: list[tuple[str, str]] = [("scope", scope)]
    if q is not None and q != "":
        params.append(("q", q))
    if cursor is not None and cursor != "":
        params.append(("cursor", cursor))
    params.append(("limit", str(limit)))
    return f"{path}?{urlencode(params)}"
