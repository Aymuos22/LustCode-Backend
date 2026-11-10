"""Coin-funded physical orders; fulfillment is manual and address data stays private."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import CoinReason, CoinTransaction, OrderStatus, RewardOrder, RewardProduct
from app.schemas import (
    OrderDetail,
    OrderReceipt,
    OrderStatusPatch,
    OrderSummary,
    Page,
    ProductAvailabilityPatch,
    RedeemRequest,
    RewardCatalog,
    RewardProductView,
)
from app.services.coins import CoinService

INITIAL_PRODUCTS: tuple[dict[str, Any], ...] = (
    dict(
        id="premium-condom-pack",
        name="Premium Condom Pack (12 pcs)",
        description="A pack of 12 premium condoms, fulfilled manually within India.",
        coin_cost=500,
        available_sizes=[],
        active=True,
        stock_quantity=None,
    ),
    dict(
        id="water-based-lubricant",
        name="Water-Based Lubricant (100ml)",
        description="Water-based lubricant, 100ml, fulfilled manually within India.",
        coin_cost=1000,
        available_sizes=[],
        active=True,
        stock_quantity=None,
    ),
    dict(
        id="body-massage-oil",
        name="Body Massage Oil (100ml)",
        description="Body massage oil, 100ml, fulfilled manually within India.",
        coin_cost=2000,
        available_sizes=[],
        active=True,
        stock_quantity=None,
    ),
    dict(
        id="soft-adjustable-blindfold",
        name="Soft Adjustable Blindfold",
        description="A soft adjustable blindfold, fulfilled manually within India.",
        coin_cost=4000,
        available_sizes=[],
        active=True,
        stock_quantity=None,
    ),
)
CATALOG_PRODUCT_IDS = tuple(product["id"] for product in INITIAL_PRODUCTS)


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.coins = CoinService(session)

    async def catalog(self) -> RewardCatalog:
        rows = await self.session.scalars(
            select(RewardProduct)
            .where(RewardProduct.id.in_(CATALOG_PRODUCT_IDS))
            .order_by(RewardProduct.coin_cost, RewardProduct.id)
        )
        return RewardCatalog(rewards=[RewardProductView.model_validate(p) for p in rows])

    async def availability(
        self, reward_id: str, payload: ProductAvailabilityPatch
    ) -> RewardProductView:
        row = await self.session.scalar(
            select(RewardProduct)
            .where(RewardProduct.id == reward_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise AppError("reward_not_found", "Product not found", 404)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        await self.session.commit()
        return RewardProductView.model_validate(row)

    @staticmethod
    def fingerprint(payload: RedeemRequest) -> str:
        return hashlib.sha256(
            json.dumps(
                payload.model_dump(mode="json"),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    async def redeem(self, user_id: UUID, key: UUID, payload: RedeemRequest) -> OrderReceipt:
        await self.coins.lock_user(user_id)
        fingerprint = self.fingerprint(payload)
        existing = await self.session.scalar(
            select(RewardOrder).where(
                RewardOrder.user_id == user_id, RewardOrder.idempotency_key == key
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise AppError(
                    "idempotency_conflict",
                    "Idempotency-Key was already used for a different order",
                    409,
                )
            return OrderReceipt(
                order=OrderDetail.model_validate(existing),
                wallet=await self.coins.wallet(user_id),
                replayed=True,
            )
        product = await self.session.scalar(
            select(RewardProduct)
            .where(
                RewardProduct.id == payload.reward_id,
                RewardProduct.id.in_(CATALOG_PRODUCT_IDS),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if product is None:
            raise AppError("reward_not_found", "Product not found", 404)
        if not product.active:
            raise AppError("product_unavailable", "This product is currently unavailable", 409)
        if product.stock_quantity == 0:
            raise AppError("out_of_stock", "This product is out of stock", 409)
        if product.available_sizes and payload.size not in product.available_sizes:
            raise AppError("size_required", "Select an available apparel size", 422)
        if not product.available_sizes and payload.size is not None:
            raise AppError("invalid_size", "This product does not have size options", 422)
        wallet = await self.coins.wallet(user_id)
        if wallet.balance < product.coin_cost:
            raise AppError("insufficient_coins", "Not enough LustCoins to order this product", 409)
        order = RewardOrder(
            user_id=user_id,
            reward_id=product.id,
            product_name=product.name,
            coin_cost=product.coin_cost,
            size=payload.size,
            shipping_address=payload.shipping_address.model_dump(),
            idempotency_key=key,
            request_fingerprint=fingerprint,
            stock_reserved=product.stock_quantity is not None,
        )
        self.session.add(order)
        await self.session.flush()
        self.session.add(
            CoinTransaction(
                user_id=user_id,
                amount=-order.coin_cost,
                reason=CoinReason.REDEMPTION,
                event_key=f"redemption:{order.id}",
                reward_date=datetime.now(UTC).date(),
                order_id=order.id,
            )
        )
        if product.stock_quantity is not None:
            product.stock_quantity -= 1
        await self.session.commit()
        return OrderReceipt(
            order=OrderDetail.model_validate(order),
            wallet=await self.coins.wallet(user_id),
            replayed=False,
            coins_spent=order.coin_cost,
        )

    async def owned(self, user_id: UUID, order_id: UUID, *, lock: bool = False) -> RewardOrder:
        query = select(RewardOrder).where(
            RewardOrder.id == order_id, RewardOrder.user_id == user_id
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = await self.session.scalar(query)
        if row is None:
            raise AppError("order_not_found", "Order not found", 404)
        return row

    async def orders(
        self, user_id: UUID | None, page: int, size: int, status: OrderStatus | None = None
    ) -> Page[OrderSummary]:
        conditions = []
        if user_id is not None:
            conditions.append(RewardOrder.user_id == user_id)
        if status is not None:
            conditions.append(RewardOrder.status == status)
        count = await self.session.scalar(
            select(func.count()).select_from(RewardOrder).where(*conditions)
        )
        rows = await self.session.scalars(
            select(RewardOrder)
            .where(*conditions)
            .order_by(RewardOrder.created_at.desc(), RewardOrder.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return Page(
            data=[OrderSummary.model_validate(row) for row in rows],
            total=count or 0,
            page=page,
            page_size=size,
        )

    async def refund(self, order: RewardOrder) -> None:
        product = await self.session.scalar(
            select(RewardProduct)
            .where(RewardProduct.id == order.reward_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if order.stock_reserved and product is not None and product.stock_quantity is not None:
            product.stock_quantity += 1
        self.session.add(
            CoinTransaction(
                user_id=order.user_id,
                amount=order.coin_cost,
                reason=CoinReason.REDEMPTION_REFUND,
                event_key=f"redemption_refund:{order.id}",
                reward_date=datetime.now(UTC).date(),
                order_id=order.id,
            )
        )
        order.status = OrderStatus.CANCELLED
        order.updated_at = order.cancelled_at = datetime.now(UTC)

    async def cancel(self, user_id: UUID, order_id: UUID) -> OrderReceipt:
        await self.coins.lock_user(user_id)
        order = await self.owned(user_id, order_id, lock=True)
        replayed = order.status == OrderStatus.CANCELLED
        if not replayed:
            if order.status != OrderStatus.PLACED:
                raise AppError(
                    "order_not_cancellable",
                    "Fulfillment has started; contact the store operator",
                    409,
                )
            await self.refund(order)
            await self.session.commit()
        return OrderReceipt(
            order=OrderDetail.model_validate(order),
            wallet=await self.coins.wallet(user_id),
            replayed=replayed,
            coins_refunded=0 if replayed else order.coin_cost,
        )

    async def staff_order(self, order_id: UUID) -> RewardOrder:
        row = await self.session.get(RewardOrder, order_id)
        if row is None:
            raise AppError("order_not_found", "Order not found", 404)
        return row

    async def transition(self, order_id: UUID, payload: OrderStatusPatch) -> OrderDetail:
        owner_id = await self.session.scalar(
            select(RewardOrder.user_id).where(RewardOrder.id == order_id)
        )
        if owner_id is None:
            raise AppError("order_not_found", "Order not found", 404)
        await self.coins.lock_user(owner_id)
        order = await self.owned(owner_id, order_id, lock=True)
        if order.status == payload.status:
            if payload.courier not in (None, order.courier) or payload.tracking_number not in (
                None,
                order.tracking_number,
            ):
                raise AppError("order_state_conflict", "Tracking details are already recorded", 409)
            return OrderDetail.model_validate(order)
        transitions = {
            OrderStatus.PLACED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
            OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
            OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
        }
        if payload.status not in transitions.get(order.status, set()):
            raise AppError("invalid_order_transition", "This order cannot move to that status", 409)
        if payload.status != OrderStatus.SHIPPED and (
            payload.courier is not None or payload.tracking_number is not None
        ):
            raise AppError(
                "invalid_tracking", "Add tracking details only when marking an order shipped", 422
            )
        if payload.status == OrderStatus.CANCELLED:
            await self.refund(order)
        else:
            if payload.status == OrderStatus.SHIPPED:
                if (
                    not payload.courier
                    or not payload.courier.strip()
                    or not payload.tracking_number
                ):
                    raise AppError(
                        "tracking_required", "Courier and tracking number are required", 422
                    )
                order.courier, order.tracking_number = (
                    payload.courier.strip(),
                    payload.tracking_number,
                )
                order.shipped_at = datetime.now(UTC)
            if payload.status == OrderStatus.DELIVERED:
                order.delivered_at = datetime.now(UTC)
            order.status = payload.status
            order.updated_at = datetime.now(UTC)
        await self.session.commit()
        return OrderDetail.model_validate(order)
