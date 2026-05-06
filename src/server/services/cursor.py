"""Opaque cursor encoding for paginated listing endpoints.

Per `api_spec.md` §5.1 / §5.3 cursors are opaque base64url tokens. The
internal envelope is a small JSON object `{"k": "...", "v": [...]}` where
`k` identifies the sort key (so the server can detect mismatch when the
caller passes a search-mode cursor to a chronological list, or vice
versa) and `v` carries the boundary values.

Any decoding or shape failure raises `InvalidCursorError`, which the API
layer surfaces as `400 /errors/invalid-cursor`.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from typing import Any

from api.errors import InvalidCursorError

KIND_CREATED_AT_ID = "created_at_id"
KIND_SIM_ID = "sim_id"


def _to_iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def encode_chronological(*, when: datetime, item_id: int) -> str:
    return _encode(KIND_CREATED_AT_ID, [_to_iso_z(when), item_id])


def encode_search(*, similarity: float, item_id: int) -> str:
    return _encode(KIND_SIM_ID, [similarity, item_id])


def decode_chronological(token: str) -> tuple[datetime, int]:
    values = _decode(token, expected_kind=KIND_CREATED_AT_ID)
    if len(values) != 2:
        raise InvalidCursorError("Cursor `v` must be `[timestamp, id]`.")
    iso, item_id = values
    if not isinstance(iso, str) or not isinstance(item_id, int):
        raise InvalidCursorError("Cursor `v` types: expected (str, int).")
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCursorError("Cursor timestamp is not ISO-8601.") from exc
    return when, item_id


def decode_search(token: str) -> tuple[float, int]:
    values = _decode(token, expected_kind=KIND_SIM_ID)
    if len(values) != 2:
        raise InvalidCursorError("Cursor `v` must be `[similarity, id]`.")
    sim, item_id = values
    if not isinstance(sim, (int, float)) or isinstance(sim, bool):
        raise InvalidCursorError("Cursor similarity must be a number.")
    if not isinstance(item_id, int) or isinstance(item_id, bool):
        raise InvalidCursorError("Cursor id must be an integer.")
    return float(sim), item_id


def _encode(kind: str, values: list[Any]) -> str:
    payload = {"k": kind, "v": values}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(token: str, *, expected_kind: str) -> list[Any]:
    """Decode `token` and return the `v` array; raise on any failure.

    Failure modes (all → `InvalidCursorError`):
    - `token` is not a base64url string;
    - decoded bytes are not JSON;
    - JSON is not an object with `k` (str) and `v` (list);
    - `k` does not equal `expected_kind`.
    """
    raw_b64 = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
    except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
        raise InvalidCursorError("Cursor is not valid base64url.") from exc

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("Cursor payload is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise InvalidCursorError("Cursor payload must be a JSON object.")
    kind = payload.get("k")
    values = payload.get("v")
    if not isinstance(kind, str) or not isinstance(values, list):
        raise InvalidCursorError("Cursor payload missing `k` or `v`.")
    if kind != expected_kind:
        raise InvalidCursorError(
            f"Cursor kind {kind!r} does not match expected {expected_kind!r}."
        )
    return values
