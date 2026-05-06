"""Image upload integration tests.

Spec: `.specs/ai_gen/api_spec.md` §10 (single multipart `file` part,
header-byte sniffing for JPEG/PNG, 5 MB limit), §4.1 (error registry).

The phase-4 stack is backend-only — there is no nginx — so the tests
verify the API contract (status code, response shape, filename pattern)
rather than the served `/uploads/<filename>` URL. End-to-end serving via
nginx is exercised in the frontend phases.
"""

from __future__ import annotations

import re

from tests.helpers import api as api_helpers
from tests.helpers.asserts import (
    JSON_MEDIA_TYPE,
    UUID4_RE,
    ERROR_PAYLOAD_TOO_LARGE,
    ERROR_UNAUTHORIZED,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    ERROR_VALIDATION,
    assert_problem_json,
)
from tests.helpers.images import JPEG_BYTES, PNG_BYTES

UUID4_JPG_RE = re.compile(UUID4_RE.pattern[:-1] + r"\.jpg$", re.IGNORECASE)
UUID4_PNG_RE = re.compile(UUID4_RE.pattern[:-1] + r"\.png$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_upload_jpeg_returns_201_with_uuid_jpg_filename(
    api_base_url: str, make_user
) -> None:
    _user, token = make_user(username="up_jpeg", password="hunter2pwd")

    response = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="photo.jpg",
        content=JPEG_BYTES,
        content_type="image/jpeg",
    )

    assert response.status_code == 201, (
        f"Expected 201 for valid JPEG, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    assert JSON_MEDIA_TYPE in response.headers.get("content-type", "")
    body = response.json()
    filename = body.get("filename")
    assert isinstance(filename, str) and UUID4_JPG_RE.match(filename), (
        f"Expected `<uuid4>.jpg` filename, got {filename!r}"
    )


def test_upload_png_returns_201_with_uuid_png_filename(
    api_base_url: str, make_user
) -> None:
    _user, token = make_user(username="up_png", password="hunter2pwd")

    response = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="photo.png",
        content=PNG_BYTES,
        content_type="image/png",
    )

    assert response.status_code == 201, (
        f"Expected 201 for valid PNG, got {response.status_code}. "
        f"Body: {response.text!r}"
    )
    body = response.json()
    filename = body.get("filename")
    assert isinstance(filename, str) and UUID4_PNG_RE.match(filename), (
        f"Expected `<uuid4>.png` filename, got {filename!r}"
    )


def test_upload_filenames_are_unique_per_request(
    api_base_url: str, make_user
) -> None:
    """UUID4 filenames must not collide between successive uploads."""
    _user, token = make_user(username="up_unique", password="hunter2pwd")

    first = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="photo.jpg",
        content=JPEG_BYTES,
        content_type="image/jpeg",
    )
    second = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="photo.jpg",
        content=JPEG_BYTES,
        content_type="image/jpeg",
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["filename"] != second.json()["filename"], (
        f"Two uploads must produce distinct filenames; got {first.json()['filename']!r} twice"
    )


# ---------------------------------------------------------------------------
# Validation: wrong format / wrong size / missing part / no auth
# ---------------------------------------------------------------------------


def test_upload_text_returns_415(api_base_url: str, make_user) -> None:
    """A 1-byte text payload fails the magic-byte sniff per implementation
    plan; api_spec §10.1 → 415 unsupported-media-type."""
    _user, token = make_user(username="up_text", password="hunter2pwd")

    response = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="not-an-image.txt",
        content=b"x",
        content_type="text/plain",
    )

    assert_problem_json(response, status=415, type_uri=ERROR_UNSUPPORTED_MEDIA_TYPE)


def test_upload_lying_content_type_still_rejected_by_sniff(
    api_base_url: str, make_user
) -> None:
    """The backend trusts the sniffed magic bytes, not the multipart
    `Content-Type` (api_spec §10.1)."""
    _user, token = make_user(username="up_lying_ct", password="hunter2pwd")

    response = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="evil.jpg",
        content=b"<html>not a jpeg</html>",
        content_type="image/jpeg",  # client lies; backend still sniffs.
    )

    assert_problem_json(response, status=415, type_uri=ERROR_UNSUPPORTED_MEDIA_TYPE)


def test_upload_too_large_returns_413(api_base_url: str, make_user) -> None:
    """api_spec §10.1: max size is 5 MB → 413 Payload Too Large."""
    _user, token = make_user(username="up_big", password="hunter2pwd")

    six_mb = JPEG_BYTES + b"\x00" * (6 * 1024 * 1024)
    response = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="huge.jpg",
        content=six_mb,
        content_type="image/jpeg",
    )

    assert_problem_json(response, status=413, type_uri=ERROR_PAYLOAD_TOO_LARGE)


def test_upload_missing_file_part_returns_400(
    api_base_url: str, make_user
) -> None:
    """api_spec §10.1: the only required form field is `file`."""
    _user, token = make_user(username="up_no_part", password="hunter2pwd")

    response = api_helpers.uploads_image_no_part(api_base_url, token=token)

    assert_problem_json(response, status=400, type_uri=ERROR_VALIDATION)


def test_upload_without_auth_returns_401(api_base_url: str) -> None:
    response = api_helpers.uploads_image(
        api_base_url,
        token=None,
        filename="photo.jpg",
        content=JPEG_BYTES,
        content_type="image/jpeg",
    )

    assert_problem_json(response, status=401, type_uri=ERROR_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# End-to-end with product creation
# ---------------------------------------------------------------------------


def test_upload_then_create_product_with_returned_filename(
    api_base_url: str, make_user, nutrition_fact_ids: dict[str, int]
) -> None:
    """Full contract loop: upload → create product referencing the
    returned filename → fetch product and confirm the filename was
    persisted. The on-disk file is **not** asserted (api_spec §6.1: the
    backend doesn't verify file existence; testing_strategy.md §4 rule 8
    forbids host-filesystem inspection)."""
    _user, token = make_user(username="up_end_to_end", password="hunter2pwd")

    upload = api_helpers.uploads_image(
        api_base_url,
        token=token,
        filename="cover.png",
        content=PNG_BYTES,
        content_type="image/png",
    )
    assert upload.status_code == 201, upload.text
    filename = upload.json()["filename"]

    create = api_helpers.products_create(
        api_base_url,
        token=token,
        body={
            "name": "Product With Image",
            "image_filename": filename,
            "nutrition_facts": [
                {
                    "nutrition_fact_id": nutrition_fact_ids["Energy"],
                    "quantity_type": "weight",
                    "amount": 200,
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    product_id = create.json()["id"]

    fetched = api_helpers.products_get(
        api_base_url, token=token, product_id=product_id
    )
    assert fetched.status_code == 200
    assert fetched.json()["image_filename"] == filename, (
        f"Persisted image_filename should equal upload-response filename "
        f"({filename!r}); got {fetched.json().get('image_filename')!r}"
    )
