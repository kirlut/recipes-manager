"""Auth endpoints: register, login, me. See `api_spec.md` §2.2."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError

from api.dependencies import current_user
from api.errors import ConflictUsernameError, UnauthorizedError
from api.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from api.schemas.users import User
from dal import users as users_dal
from dal.connections import read_only, transaction
from services.auth import hash_password, issue_token, verify_password

router = APIRouter()


@router.post("/auth/register", status_code=status.HTTP_201_CREATED, response_model=User)
async def register(req: RegisterRequest) -> User:
    pwd_hash = hash_password(req.password)
    try:
        async with transaction() as conn:
            row = await users_dal.create_user(
                conn,
                username=req.username,
                full_name=req.full_name,
                pwd_hash=pwd_hash,
            )
    except IntegrityError:
        raise ConflictUsernameError(
            f"Username {req.username!r} is already taken.",
            extensions={"username": req.username},
        ) from None
    return User(**row)


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    async with read_only() as conn:
        user = await users_dal.get_user_by_username(conn, req.username)
    if user is None or not verify_password(req.password, user["pwd_hash"]):
        raise UnauthorizedError("Invalid username or password.")

    token, expires_at = issue_token(user_id=user["id"], username=user["username"])
    return LoginResponse(
        token=token,
        expires_at=expires_at,
        user=User(
            id=user["id"],
            username=user["username"],
            full_name=user["full_name"],
            created_at=user["created_at"],
        ),
    )


@router.get("/auth/me", response_model=User)
async def me(user: dict = Depends(current_user)) -> User:
    return User(
        id=user["id"],
        username=user["username"],
        full_name=user["full_name"],
        created_at=user["created_at"],
    )
