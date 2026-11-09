from unittest.mock import AsyncMock

from sqlalchemy.exc import OperationalError

from app.db import session_dependency


async def test_liveness_and_openapi(client) -> None:
    assert (await client.get("/api/v1/health/live")).json() == {"data": {"status": "ok"}}
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/submissions" in response.json()["paths"]
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_auth_required_and_validation_redacted(client) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid",
            "username": "xx",
            "password": "secret",
        },
    )
    assert response.status_code == 422
    assert "secret" not in response.text and '"input"' not in response.text
    assert (await client.get("/api/v1/questions/not-uuid")).status_code == 422
    assert (await client.get("/api/v1/questions?page_size=101")).status_code == 422
    assert (await client.get("/api/v1/questions?page=99999999999999999999999")).status_code == 422


async def test_body_limit_including_chunked(client, settings) -> None:
    response = await client.post(
        "/api/v1/auth/register", content=b"x" * (settings.request_max_bytes + 1)
    )
    assert response.status_code == 413

    async def chunks():
        yield b"x" * settings.request_max_bytes
        yield b"y"

    assert (await client.post("/api/v1/auth/register", content=chunks())).status_code == 413


async def test_cors_allows_only_configured_origins(client) -> None:
    for origin, allowed in [("http://localhost:3000", True), ("https://evil.example", False)]:
        response = await client.options(
            "/api/v1/runs",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert (response.status_code == 200) == allowed


async def test_database_failure_is_sanitized(client) -> None:
    app = client._transport.app
    session = AsyncMock()
    session.scalar.side_effect = OperationalError(
        "SELECT secret", {}, Exception("private-password")
    )

    async def broken_session():
        yield session

    app.dependency_overrides[session_dependency] = broken_session
    response = await client.get("/api/v1/questions")
    assert response.status_code == 503
    assert "private-password" not in response.text and "SELECT" not in response.text


async def test_auth_rate_limit(client, settings) -> None:
    settings.auth_requests_per_minute = 1
    await client.post("/api/v1/auth/login", json={})
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
