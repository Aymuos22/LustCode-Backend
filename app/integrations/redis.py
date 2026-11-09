from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import AppError

RATE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
"""

QUOTA_SCRIPT = """
local submissions = tonumber(redis.call('GET', KEYS[1]) or '0')
local executions = tonumber(redis.call('GET', KEYS[2]) or '0')
if submissions >= tonumber(ARGV[1]) or executions + tonumber(ARGV[3]) > tonumber(ARGV[2]) then
  return 0
end
redis.call('INCR', KEYS[1])
redis.call('INCRBY', KEYS[2], ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return 1
"""


class Limits:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.settings = settings

    async def rate(self, identity: str, *, auth: bool = False) -> None:
        limit = (
            self.settings.auth_requests_per_minute
            if auth
            else self.settings.rate_requests_per_minute
        )
        window = int(datetime.now(UTC).timestamp()) // 60
        try:
            count = await cast(
                Awaitable[int], self.redis.eval(RATE_SCRIPT, 1, f"rate:{identity}:{window}", 60)
            )
        except RedisError as exc:
            raise AppError("infrastructure_unavailable", "Rate limiter unavailable", 503) from exc
        if int(count) > limit:
            raise AppError("rate_limited", "Too many requests; retry after 60 seconds", 429)

    async def execution(self, user_id: str, tests: int) -> None:
        day = datetime.now(UTC).date().isoformat()
        try:
            allowed = await cast(
                Awaitable[int],
                self.redis.eval(
                    QUOTA_SCRIPT,
                    2,
                    f"quota:{{{user_id}}}:{day}:submissions",
                    f"quota:{{{user_id}}}:{day}:executions",
                    self.settings.daily_submissions,
                    self.settings.daily_test_executions,
                    tests,
                    172800,
                ),
            )
        except RedisError as exc:
            raise AppError(
                "infrastructure_unavailable", "Execution quota service unavailable", 503
            ) from exc
        if not allowed:
            raise AppError(
                "quota_exceeded", "Daily execution quota exceeded (resets at UTC midnight)", 429
            )
