"""Operator-only staff assignment using private database credentials; never an API grant."""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.db import create_engine
from app.models import User


async def set_staff(username: str, enabled: bool) -> None:
    engine = create_engine(Settings())
    try:
        async with async_sessionmaker(engine)() as session:
            user = await session.scalar(
                select(User).where(User.username == username.lower()).with_for_update()
            )
            if user is None or not user.is_active:
                raise ValueError("Active account not found")
            user.is_staff = enabled
            await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(set_staff(args.username, not args.revoke))
    except Exception as exc:
        # Driver exceptions may include credentials; never print their string or traceback.
        print(f"Staff assignment failed ({type(exc).__name__})")
        raise SystemExit(1) from None
    print("Fulfillment staff permission updated")


if __name__ == "__main__":
    main()
