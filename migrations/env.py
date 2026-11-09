import asyncio

from alembic import context

from app.core.config import Settings
from app.db import create_engine
from app.models import Base


def offline() -> None:
    settings = Settings()
    url = settings.migration_database_url or settings.database_url
    context.configure(
        url=url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_engine(Settings(), migration=True)
    try:
        async with engine.connect() as connection:

            def migrate(sync_connection: object) -> None:
                context.configure(
                    connection=sync_connection, target_metadata=Base.metadata, compare_type=True
                )
                with context.begin_transaction():
                    context.run_migrations()

            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    offline()
else:
    asyncio.run(online())
