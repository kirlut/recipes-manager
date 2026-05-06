import uuid

import httpx


def test_unknown_api_path_is_proxied_to_backend(base_url: str) -> None:
    """`/api/<unknown>` must reach the backend (which produces 404).

    Body shape (Problem+JSON) is not asserted here — the Problem+JSON
    exception middleware lands in phase 3. Phase 1 only needs to prove
    that nginx forwards `/api/*` to the backend at all.
    """
    unknown_path = f"/api/__phase1_unknown_{uuid.uuid4().hex}__"

    response = httpx.get(f"{base_url}{unknown_path}", timeout=10.0)

    assert response.status_code == 404, (
        f"Expected 404 from {unknown_path}, got {response.status_code}. "
        f"Body: {response.text!r}"
    )


def test_uploads_missing_file_served_by_nginx(base_url: str) -> None:
    """`/uploads/<missing>.jpg` must 404 directly from nginx.

    nginx's stock 404 page is HTML; FastAPI's would be JSON. Asserting
    `Content-Type: text/html` confirms the request did not reach the
    backend (which has no `/uploads` route).
    """
    missing_filename = f"missing-{uuid.uuid4().hex}.jpg"

    response = httpx.get(
        f"{base_url}/uploads/{missing_filename}", timeout=10.0
    )

    assert response.status_code == 404, (
        f"Expected 404 from /uploads/{missing_filename}, "
        f"got {response.status_code}. Body: {response.text!r}"
    )

    content_type = response.headers.get("content-type", "")
    assert content_type.lower().startswith("text/html"), (
        "Expected /uploads/<missing> to be served by nginx (text/html 404), "
        f"got Content-Type={content_type!r}. Body: {response.text!r}"
    )
