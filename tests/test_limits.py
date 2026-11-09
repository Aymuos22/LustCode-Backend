import asyncio

import pytest
from redis.exceptions import ConnectionError

from app.core.errors import AppError
from app.integrations.redis import Limits


async def test_atomic_quota_under_concurrency(redis, settings) -> None:
    settings.daily_submissions = 3
    settings.daily_test_executions = 6
    limits = Limits(redis, settings)
    results = await asyncio.gather(
        *(limits.execution("same-user", 2) for _ in range(20)), return_exceptions=True
    )
    assert sum(result is None for result in results) == 3
    assert all(result is None or isinstance(result, AppError) for result in results)
    await limits.execution("different-user", 2)


async def test_quota_rejects_expensive_request_without_consuming_budget(redis, settings) -> None:
    settings.daily_test_executions = 2
    limits = Limits(redis, settings)
    with pytest.raises(AppError):
        await limits.execution("user", 3)
    await limits.execution("user", 2)
    with pytest.raises(AppError):
        await limits.execution("user", 1)


async def test_rate_limit_has_expiry(redis, settings) -> None:
    settings.auth_requests_per_minute = 1
    limits = Limits(redis, settings)
    await limits.rate("login", auth=True)
    with pytest.raises(AppError) as error:
        await limits.rate("login", auth=True)
    assert error.value.status == 429
    keys = await redis.keys("rate:*")
    assert await redis.ttl(keys[0]) > 0


async def test_limits_fail_closed(redis, settings, monkeypatch) -> None:
    async def fail(*args, **kwargs):
        raise ConnectionError("private-infrastructure-address")

    monkeypatch.setattr(redis, "eval", fail)
    for action in (Limits(redis, settings).rate("ip"), Limits(redis, settings).execution("u", 1)):
        with pytest.raises(AppError) as error:
            await action
        assert error.value.status == 503
        assert "private-infrastructure" not in error.value.message
