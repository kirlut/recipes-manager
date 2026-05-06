import httpx


def test_health_endpoint_returns_ok(base_url: str) -> None:
    response = httpx.get(f"{base_url}/api/health", timeout=10.0)

    assert response.status_code == 200, (
        f"Expected 200 from /api/health, got {response.status_code}. "
        f"Body: {response.text!r}"
    )

    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type, (
        f"Expected application/json from /api/health, got {content_type!r}"
    )

    payload = response.json()
    assert payload == {"status": "ok"}, (
        f"Expected {{'status': 'ok'}} from /api/health, got {payload!r}"
    )
