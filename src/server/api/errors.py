"""Problem+JSON (RFC 9457) error contract.

Every non-2xx response served by the backend must use the shape defined
here. The error `type` URI registry lives in `.specs/ai_gen/api_spec.md`
§4.1; the URIs here mirror that registry exactly.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("recipes-manager.errors")

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

_BASE_URI = "https://recipes-manager.local/errors"

ERROR_VALIDATION = f"{_BASE_URI}/validation"
ERROR_INVALID_CURSOR = f"{_BASE_URI}/invalid-cursor"
ERROR_UNAUTHORIZED = f"{_BASE_URI}/unauthorized"
ERROR_FORBIDDEN_NOT_OWNER = f"{_BASE_URI}/forbidden-not-owner"
ERROR_NOT_FOUND = f"{_BASE_URI}/not-found"
ERROR_CONFLICT_USERNAME = f"{_BASE_URI}/conflict-username"
ERROR_CONFLICT = f"{_BASE_URI}/conflict"
ERROR_PAYLOAD_TOO_LARGE = f"{_BASE_URI}/payload-too-large"
ERROR_UNSUPPORTED_MEDIA_TYPE = f"{_BASE_URI}/unsupported-media-type"
ERROR_INTERNAL = f"{_BASE_URI}/internal"

# HTTP status -> default registry URI for generic StarletteHTTPException
# fall-throughs (e.g. FastAPI's own 404 on unknown routes).
_STATUS_DEFAULT_URI: dict[int, str] = {
    400: ERROR_VALIDATION,
    401: ERROR_UNAUTHORIZED,
    403: ERROR_FORBIDDEN_NOT_OWNER,
    404: ERROR_NOT_FOUND,
    409: ERROR_CONFLICT,
    413: ERROR_PAYLOAD_TOO_LARGE,
    415: ERROR_UNSUPPORTED_MEDIA_TYPE,
}

_STATUS_DEFAULT_TITLE: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    415: "Unsupported media type",
    500: "Internal server error",
}


class AppError(Exception):
    """Base for application-defined errors that map to Problem+JSON."""

    type_uri: str = ERROR_INTERNAL
    status: int = 500
    title: str = "Internal server error"

    def __init__(
        self,
        detail: str = "",
        *,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extensions = extensions

    def to_problem(self, request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": self.type_uri,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "instance": request.url.path,
        }
        if self.extensions:
            body["extensions"] = self.extensions
        return body


class UnauthorizedError(AppError):
    type_uri = ERROR_UNAUTHORIZED
    status = 401
    title = "Unauthorized"


class ConflictUsernameError(AppError):
    type_uri = ERROR_CONFLICT_USERNAME
    status = 409
    title = "Username already taken"


def _problem_response(body: dict[str, Any], status: int) -> JSONResponse:
    return JSONResponse(content=body, status_code=status, media_type=PROBLEM_JSON_MEDIA_TYPE)


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _problem_response(exc.to_problem(request), exc.status)


async def _request_validation_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Convert pydantic / FastAPI request-body validation errors to 400 Problem+JSON.

    Spec § 4 example uses `field` paths like `nutrition_facts.0.amount` —
    drop the leading `body` segment that FastAPI prepends.
    """
    assert isinstance(exc, RequestValidationError)
    violations = []
    for err in exc.errors():
        loc = err.get("loc", ())
        # Strip leading "body" / "query" / "path" segment for cleaner field paths.
        if loc and loc[0] in ("body", "query", "path"):
            loc = loc[1:]
        field = ".".join(str(part) for part in loc)
        violations.append({"field": field, "message": err.get("msg", "")})

    body = {
        "type": ERROR_VALIDATION,
        "title": "Validation failed",
        "status": 400,
        "detail": "Request body is invalid.",
        "instance": request.url.path,
        "extensions": {"violations": violations},
    }
    return _problem_response(body, 400)


async def _http_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Generic Problem+JSON wrapper for unhandled `HTTPException`s.

    Mostly catches FastAPI's own 404s on unknown routes.
    """
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    type_uri = _STATUS_DEFAULT_URI.get(status, ERROR_INTERNAL)
    title = _STATUS_DEFAULT_TITLE.get(status, "Error")
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else title
    body = {
        "type": type_uri,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    return _problem_response(body, status)


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("unhandled exception", extra={"path": request.url.path})
    body = {
        "type": ERROR_INTERNAL,
        "title": "Internal server error",
        "status": 500,
        "detail": "An unexpected error occurred.",
        "instance": request.url.path,
    }
    return _problem_response(body, 500)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
