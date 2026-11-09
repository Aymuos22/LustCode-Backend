import ssl
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database_config import database_target


def create_engine(settings: Settings, *, migration: bool = False) -> AsyncEngine:
    url = settings.database_url
    if migration and settings.migration_database_url:
        url = settings.migration_database_url
    target = database_target(url.get_secret_value(), settings.database_ssl)
    connect_args: dict[str, object] = {
        "timeout": settings.database_connect_timeout_seconds,
        "command_timeout": settings.database_command_timeout_seconds,
        "prepared_statement_cache_size": target.statement_cache_size,
    }
    # Always verify both the CA chain and host name, including sslmode=require URLs.
    ca_file = (
        str(settings.database_ssl_root_cert) if settings.database_ssl_root_cert else target.ca_file
    )
    connect_args["ssl"] = ssl.create_default_context(cafile=ca_file) if target.tls else False
    pool_options: dict[str, object] = (
        {"poolclass": NullPool}
        if migration
        else {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
            "pool_timeout": settings.database_pool_timeout_seconds,
            "pool_recycle": settings.database_pool_recycle_seconds,
        }
    )
    return create_async_engine(
        target.url,
        connect_args=connect_args,
        pool_pre_ping=True,
        hide_parameters=True,
        **pool_options,
    )


async def session_dependency(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with factory() as session:
        yield session
