"""Auth primitives: bcrypt password hashing and HS256 JWT issue/decode."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt as pyjwt

from settings import settings

JWT_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_cost)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def issue_token(*, user_id: int, username: str) -> tuple[str, datetime]:
    """Encode a 24h HS256 JWT and return `(token, expires_at_utc)`."""
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(hours=settings.jwt_ttl_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_token(token: str) -> dict:
    """Decode a JWT or raise `pyjwt.PyJWTError`."""
    return pyjwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
