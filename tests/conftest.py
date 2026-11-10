import os
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.integrations.judge0 import ExecutionResult
from app.main import create_app
from app.models import Base, Language, RewardProduct, Verdict
from app.schemas import LanguageView
from app.services.orders import INITIAL_PRODUCTS


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://test:test@localhost/lustcode_test",
        jwt_secret="test-secret-at-least-thirty-two-characters-long",
        rate_requests_per_minute=1000,
        auth_requests_per_minute=100,
        judge0_poll_seconds=0.1,
    )


@pytest.fixture
async def redis() -> AsyncIterator[FakeRedis]:
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


class FakeProvider:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.polled: list[str] = []
        self.results: list[ExecutionResult] = []
        self.error: Exception | None = None

    async def languages(self) -> list[LanguageView]:
        return [
            LanguageView(id=71, name="Python (3.8.1)", language=Language.PYTHON),
            LanguageView(id=62, name="Java (OpenJDK 13.0.1)", language=Language.JAVA),
            LanguageView(id=54, name="C++ (GCC 9.2.0)", language=Language.CPP),
        ]

    async def create(
        self,
        source: str,
        language_id: int,
        stdin: str,
        expected: str | None,
        cpu: float,
        memory: int,
        compiler_options: str | None = None,
    ) -> str:
        if self.error:
            raise self.error
        self.created.append(
            dict(source=source, stdin=stdin, expected=expected, cpu=cpu, memory=memory)
        )
        return str(uuid4())

    async def poll(self, token: str) -> ExecutionResult:
        self.polled.append(token)
        if self.error:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return ExecutionResult(
            status=Verdict.ACCEPTED, stdout="output", execution_time=0.01, memory_kb=1000
        )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    admin = create_async_engine(url)
    schema = "test_" + uuid4().hex
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with AsyncSession(engine) as session:
            session.add_all([RewardProduct(**values) for values in INITIAL_PRODUCTS])
            await session.commit()
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def client(settings: Settings, redis: FakeRedis) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.redis = redis
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as value:
            yield value


@pytest.fixture
async def api(
    settings: Settings, redis: FakeRedis, sessions, provider
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        app.state.redis = redis
        app.state.sessions = sessions
        app.state.provider = provider
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as value:
            yield value
