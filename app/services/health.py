import asyncio
from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError


async def check_readiness(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    budget_seconds: float,
) -> None:
    async def database_ready() -> bool:
        try:
            async with asyncio.timeout(budget_seconds), sessions() as session:
                await session.execute(text("SELECT 1"))
            return True
        except (SQLAlchemyError, OSError, TimeoutError):
            return False

    async def redis_ready() -> bool:
        try:
            async with asyncio.timeout(budget_seconds):
                return bool(await cast(Awaitable[bool], redis.ping()))
        except (RedisError, OSError, TimeoutError):
            return False

    if not all(await asyncio.gather(database_ready(), redis_ready())):
        raise AppError("not_ready", "Required infrastructure is unavailable", 503)
