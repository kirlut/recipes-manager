"""Auth request / response models. See `api_spec.md` §2.2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.schemas.users import User, ZDatetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: ZDatetime
    user: User
