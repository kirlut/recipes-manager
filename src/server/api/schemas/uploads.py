"""Image upload response model. See `api_spec.md` §10.1."""

from __future__ import annotations

from pydantic import BaseModel


class UploadResponse(BaseModel):
    filename: str
