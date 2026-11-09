"""Serialize Alembic upgrades across Render web/worker pre-deploy jobs."""

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db import create_engine

RELEASE_LOCK_ID = 846219340153
logger = logging.getLogger(__name__)


async def upgrade(settings: Settings, config_path: Path = Path("alembic.ini")) -> None:
    engine = create_engine(settings, migration=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": RELEASE_LOCK_ID}
            )
            # Alembic's async environment owns its event loop, so run it in a thread.
            await asyncio.to_thread(command.upgrade, Config(str(config_path)), "head")
        logger.info("Database migrations are at the release head")
    finally:
        await engine.dispose()


def main() -> None:
    configure_logging()
    try:
        asyncio.run(upgrade(Settings()))
    except Exception as exc:
        # URL/driver exceptions may contain connection credentials; report classification only.
        logger.error("Release migrations failed (%s)", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
