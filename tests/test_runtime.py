import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient as HttpClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.main import create_app
from app.runtime import runtime_resources


@pytest.fixture
def factories(settings, monkeypatch):
    engine = MagicMock()
    engine.dispose = AsyncMock()
    redis = MagicMock()
    redis.aclose = AsyncMock()
    redis.ping = AsyncMock(side_effect=RedisConnectionError("unavailable"))
    requests = []

    def forbidden_request(request):
        requests.append(request)
        raise AssertionError("Startup must not call Judge0")

    http = HttpClient(transport=httpx.MockTransport(forbidden_request))
    http_factory = MagicMock(return_value=http)
    redis_factory = MagicMock(return_value=redis)
    monkeypatch.setattr("app.runtime.create_engine", lambda config: engine)
    monkeypatch.setattr("app.runtime.Redis.from_url", redis_factory)
    monkeypatch.setattr("app.runtime.httpx.AsyncClient", http_factory)
    return engine, redis, http, http_factory, redis_factory, requests


async def test_shared_runtime_is_lazy_bounded_and_closes_resources(settings, factories) -> None:
    engine, redis, http, http_factory, redis_factory, requests = factories
    async with runtime_resources(settings) as resources:
        assert resources.engine is engine and resources.redis is redis
        assert resources.provider.client is resources.http is http
        assert not http.is_closed
        kwargs = http_factory.call_args.kwargs
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert kwargs["limits"].max_connections == settings.judge0_max_connections
        assert kwargs["timeout"].connect == settings.judge0_timeout_seconds
        assert redis_factory.call_args.args[0] == settings.redis_url.get_secret_value()
        assert redis_factory.call_args.kwargs["socket_connect_timeout"] == 2
    assert http.is_closed and not requests
    redis.ping.assert_not_awaited()
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_partial_initialization_failure_closes_prior_resources(settings, factories) -> None:
    engine, redis, http, factory, _, _ = factories
    factory.side_effect = RuntimeError("initialization failed")
    with pytest.raises(RuntimeError):
        async with runtime_resources(settings):
            pytest.fail("Must fail before entering runtime")
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    await http.aclose()


async def test_one_cleanup_failure_does_not_skip_other_closes(settings, factories) -> None:
    engine, redis, http, _, _, _ = factories
    redis.aclose.side_effect = RuntimeError("close failed")
    with pytest.raises(RuntimeError, match="close failed"):
        async with runtime_resources(settings):
            pass
    assert http.is_closed
    engine.dispose.assert_awaited_once()


async def test_cancelled_work_still_closes_runtime(settings, factories) -> None:
    engine, redis, http, _, _, _ = factories
    with pytest.raises(asyncio.CancelledError):
        async with runtime_resources(settings):
            raise asyncio.CancelledError()
    assert http.is_closed
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_app_starts_with_unavailable_optional_integrations(settings, factories) -> None:
    engine, redis, http, _, _, requests = factories
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.http_client is http and app.state.provider.client is http
        async with HttpClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/health/live")
            assert response.status_code == 200
    assert http.is_closed and not requests
    redis.ping.assert_not_awaited()
    engine.dispose.assert_awaited_once()


async def test_failure_after_resource_creation_still_cleans_up(
    settings, factories, monkeypatch
) -> None:
    engine, redis, http, _, _, _ = factories
    monkeypatch.setattr(
        "app.main.run_in_threadpool", AsyncMock(side_effect=RuntimeError("hash initialization"))
    )
    app = create_app(settings)
    with pytest.raises(RuntimeError):
        async with app.router.lifespan_context(app):
            pytest.fail("Startup should fail")
    assert http.is_closed
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
