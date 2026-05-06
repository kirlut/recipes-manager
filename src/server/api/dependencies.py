"""Reusable FastAPI dependencies (auth, etc.)."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt as pyjwt

from api.errors import UnauthorizedError
from dal import users as users_dal
from dal.connections import read_only
from services.auth import decode_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Resolve the caller from `Authorization: Bearer <jwt>`.

    Any failure (missing header, wrong scheme, bad signature, expired
    token, missing/invalid `sub`, user not in DB) → 401 Unauthorized
    with Problem+JSON `type=/errors/unauthorized`.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing or malformed Authorization header.")

    try:
        payload = decode_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise UnauthorizedError("Invalid or expired token.") from None

    sub = payload.get("sub")
    if sub is None:
        raise UnauthorizedError("Invalid or expired token.")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise UnauthorizedError("Invalid or expired token.") from None

    async with read_only() as conn:
        user = await users_dal.get_user_by_id(conn, user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token.")
    return user
