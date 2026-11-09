import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy.exc import OperationalError


def ready_dependencies(app):
    session = MagicMock()
    session.execute = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    app.state.sessions = MagicMock(return_value=context)
    app.state.redis.ping = AsyncMock(return_value=True)
    return session, context


async def test_readiness_success_does_not_probe_judge0(client) -> None:
    app = client._transport.app
    session, context = ready_dependencies(app)
    app.state.provider.languages = AsyncMock(
        side_effect=AssertionError("Not a readiness dependency")
    )
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200 and response.json() == {"data": {"status": "ready"}}
    session.execute.assert_awaited_once()
    context.__aexit__.assert_awaited_once()
    app.state.provider.languages.assert_not_awaited()


@pytest.mark.parametrize("failed", ["database", "redis", "both"])
async def test_required_dependency_failures_report_503(client, failed) -> None:
    app = client._transport.app
    session, context = ready_dependencies(app)
    if failed in ("database", "both"):
        session.execute.side_effect = OperationalError("SELECT", {}, Exception("private-password"))
    if failed in ("redis", "both"):
        app.state.redis.ping.side_effect = ConnectionError("private-redis-address")
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503 and response.json()["error"]["code"] == "not_ready"
    assert "private-" not in response.text
    assert (await client.get("/api/v1/health/live")).status_code == 200
    context.__aexit__.assert_awaited_once()
    app.state.redis.ping.assert_awaited_once()


async def test_readiness_has_a_total_deadline_and_closes_session(client, settings) -> None:
    app = client._transport.app
    session, context = ready_dependencies(app)
    settings.readiness_timeout_seconds = 0.1

    async def stall(*args):
        await asyncio.sleep(5)

    session.execute.side_effect = stall
    app.state.redis.ping.side_effect = stall
    started = time.monotonic()
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert time.monotonic() - started < 1
    context.__aexit__.assert_awaited_once()


async def test_redis_outage_keeps_liveness_up_and_protected_requests_fail_closed(
    client, monkeypatch
) -> None:
    app = client._transport.app

    async def fail(*args):
        raise ConnectionError("secret")

    monkeypatch.setattr(app.state.redis, "eval", fail)
    assert (await client.get("/api/v1/health/live")).status_code == 200
    response = await client.get("/api/v1/questions")
    assert response.status_code == 503 and "secret" not in response.text
