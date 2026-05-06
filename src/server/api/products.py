"""Product endpoints: POST/GET/PUT/DELETE /products and /products/{id}/copy.

See `api_spec.md` §6.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.dependencies import current_user
from api.schemas.products import Product, ProductCreate
from services import products as products_service

router = APIRouter()


@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
    response_model=Product,
)
async def create_product(
    body: ProductCreate,
    response: Response,
    user: dict = Depends(current_user),
) -> Product:
    product = await products_service.create(user_id=user["id"], body=body)
    response.headers["Location"] = f"/products/{product['id']}"
    return Product(**product)


@router.get("/products/{product_id}", response_model=Product)
async def get_product(
    product_id: int,
    _user: dict = Depends(current_user),
) -> Product:
    product = await products_service.get(product_id)
    return Product(**product)


@router.put("/products/{product_id}", response_model=Product)
async def replace_product(
    product_id: int,
    body: ProductCreate,
    user: dict = Depends(current_user),
) -> Product:
    product = await products_service.replace(
        product_id=product_id, user_id=user["id"], body=body
    )
    return Product(**product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    user: dict = Depends(current_user),
) -> Response:
    await products_service.delete(product_id=product_id, user_id=user["id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/products/{product_id}/copy",
    status_code=status.HTTP_201_CREATED,
    response_model=Product,
)
async def copy_product(
    product_id: int,
    response: Response,
    user: dict = Depends(current_user),
) -> Product:
    product = await products_service.copy(
        source_id=product_id, user_id=user["id"]
    )
    response.headers["Location"] = f"/products/{product['id']}"
    return Product(**product)
