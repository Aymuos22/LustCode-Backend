from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db import create_engine
from app.integrations.judge0 import Judge0


@dataclass(frozen=True)
class RuntimeResources:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    http: httpx.AsyncClient
    provider: Judge0


@asynccontextmanager
async def runtime_resources(settings: Settings) -> AsyncIterator[RuntimeResources]:
    # Register each cleanup immediately: partial initialization and cleanup failures
    # must still close the other resources. No remote calls are made during startup.
    async with AsyncExitStack() as stack:
        engine = create_engine(settings)
        stack.push_async_callback(engine.dispose)
        redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
        )
        stack.push_async_callback(redis.aclose)
        http = await stack.enter_async_context(
            httpx.AsyncClient(
                timeout=httpx.Timeout(settings.judge0_timeout_seconds),
                limits=httpx.Limits(
                    max_connections=settings.judge0_max_connections,
                    max_keepalive_connections=settings.judge0_max_keepalive_connections,
                ),
                follow_redirects=False,
                trust_env=False,
            )
        )
        yield RuntimeResources(
            engine,
            async_sessionmaker(engine, expire_on_commit=False),
            redis,
            http,
            Judge0(http, settings, redis),
        )
