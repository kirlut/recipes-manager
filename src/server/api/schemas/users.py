"""User-facing pydantic models. See `api_spec.md` §3.1, §3.2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, PlainSerializer


def _to_iso_z(value: datetime) -> str:
    """Serialize a datetime as ISO-8601 UTC with `Z` suffix per spec §1.3."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


ZDatetime = Annotated[datetime, PlainSerializer(_to_iso_z, return_type=str)]


class UserRef(BaseModel):
    """Compact creator reference embedded in product/recipe responses."""

    id: int
    username: str
    full_name: str | None


class User(UserRef):
    """Full user representation returned by /auth endpoints."""

    created_at: ZDatetime
