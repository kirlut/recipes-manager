"""POST /uploads/images. See `api_spec.md` §10."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status

from api.dependencies import current_user
from api.errors import PayloadTooLargeError
from api.schemas.uploads import UploadResponse
from dal.images import write_image
from services.images import detect_extension
from settings import settings

router = APIRouter()

_SNIFF_BYTES = 32
_CHUNK_SIZE = 64 * 1024


@router.post(
    "/uploads/images",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
)
async def upload_image(
    # Auth dependency is listed first so a missing/invalid token surfaces as
    # 401 before the multipart parser runs.
    user: dict = Depends(current_user),
    file: UploadFile = File(...),
) -> UploadResponse:
    sniff = await file.read(_SNIFF_BYTES)
    ext = detect_extension(sniff)

    chunks: list[bytes] = [sniff]
    total = len(sniff)
    max_bytes = settings.image_max_bytes
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"Uploaded image exceeds {max_bytes} bytes."
            )
        chunks.append(chunk)

    payload = b"".join(chunks)
    filename = write_image(settings.image_dir, payload, ext)
    return UploadResponse(filename=filename)
