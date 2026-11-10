import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import CoinReason, CoinTransaction, RewardOrder, RewardProduct, User
from app.schemas import RedeemRequest
from app.services.orders import CATALOG_PRODUCT_IDS, OrderService
from tests.test_orders import ADDRESS

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
async def test_catalog_migration_preserves_old_orders_and_protects_new_history(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for isolated migration verification")
    name = "catalog_" + uuid4().hex
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    engine = None
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        target = make_url(url).set(database=name).render_as_string(hide_password=False)
        for key, value in {
            "DATABASE_URL": target,
            "MIGRATION_DATABASE_URL": target,
            "DATABASE_SSL": "false",
            "ENVIRONMENT": "test",
            "JWT_SECRET": "synthetic-catalog-test-secret-at-least-32-characters",
        }.items():
            monkeypatch.setenv(key, value)
        cfg = Config(str(ROOT / "alembic.ini"))
        await asyncio.to_thread(command.upgrade, cfg, "55b1518bb710")
        engine = create_async_engine(target)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(email="fixture@example.com", username="fixture", password_hash="unused")
            session.add(user)
            await session.flush()
            user_id = user.id
            old_key = uuid4()
            old_payload = RedeemRequest(reward_id="lustcode-stickers", shipping_address=ADDRESS)
            old_order = RewardOrder(
                user_id=user.id,
                reward_id="lustcode-stickers",
                product_name="LustCode Sticker Pack",
                coin_cost=500,
                shipping_address=ADDRESS,
                idempotency_key=old_key,
                request_fingerprint=OrderService.fingerprint(old_payload),
            )
            session.add(old_order)
            await session.flush()
            old_id = old_order.id
            session.add_all(
                [
                    CoinTransaction(
                        user_id=user.id,
                        amount=1500,
                        reason=CoinReason.DAILY_CHECK_IN,
                        event_key="fixture-credit",
                        reward_date=datetime.now(UTC).date(),
                    ),
                    CoinTransaction(
                        user_id=user.id,
                        amount=-500,
                        reason=CoinReason.REDEMPTION,
                        event_key="fixture-debit",
                        order_id=old_id,
                        reward_date=datetime.now(UTC).date(),
                    ),
                ]
            )
            await session.commit()
        await asyncio.to_thread(command.upgrade, cfg, "head")
        async with sessions() as session:
            old = await session.get(RewardOrder, old_id)
            assert (old.product_name, old.coin_cost, old.shipping_address) == (
                "LustCode Sticker Pack",
                500,
                ADDRESS,
            )
            assert not (await session.get(RewardProduct, "lustcode-stickers")).active
            service = OrderService(session)
            assert (await service.coins.wallet(user_id)).balance == 1000
            assert [p.id for p in (await service.catalog()).rewards] == list(CATALOG_PRODUCT_IDS)
            replay = await service.redeem(user_id, old_key, old_payload)
            assert replay.replayed and replay.order.id == old_id and replay.coins_spent == 0
            cancelled = await service.cancel(user_id, old_id)
            assert cancelled.coins_refunded == 500 and cancelled.wallet.balance == 1500
            receipt = await service.redeem(
                user_id,
                uuid4(),
                RedeemRequest(reward_id="premium-condom-pack", shipping_address=ADDRESS),
            )
            assert receipt.wallet.balance == 1000 and receipt.coins_spent == 500
        with pytest.raises(RuntimeError, match="order history"):
            await asyncio.to_thread(command.downgrade, cfg, "55b1518bb710")
        async with sessions() as session:
            assert (
                await session.scalar(text("SELECT version_num FROM alembic_version"))
                == "8ae36dc2f109"
            )
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await asyncio.to_thread(command.downgrade, cfg, "55b1518bb710")
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(RewardProduct)
                    .where(RewardProduct.id.in_(CATALOG_PRODUCT_IDS))
                )
                == 0
            )
            assert not (await session.get(RewardProduct, "lustcode-stickers")).active
        await asyncio.to_thread(command.upgrade, cfg, "head")
        await asyncio.to_thread(command.check, cfg)
    finally:
        if engine:
            await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
