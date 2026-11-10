from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Response

from app.api.dependencies import Config, CurrentStaff, CurrentUser, OptionalUser, Session
from app.api.features import PageNumber, PageSize
from app.models import OrderStatus
from app.schemas import (
    CheckInRequest,
    CheckInView,
    CoinRules,
    CoinTransactionView,
    CoinWallet,
    DailyProblemView,
    Data,
    OrderDetail,
    OrderReceipt,
    OrderStatusPatch,
    OrderSummary,
    Page,
    ProductAvailabilityPatch,
    RedeemRequest,
    RewardCatalog,
    RewardProductView,
    StreakView,
)
from app.services.coins import CoinService, rules
from app.services.daily import DailyProblemService
from app.services.orders import OrderService
from app.services.profiles import ProfileService

router = APIRouter(prefix="/api/v1")


@router.get("/users/me/streak", response_model=Data[StreakView], tags=["users"])
async def streak(user: CurrentUser, session: Session) -> Data[StreakView]:
    return Data(data=await ProfileService(session).streak(user.id))


@router.get("/questions/daily", response_model=Data[DailyProblemView], tags=["questions"])
async def daily_problem(
    session: Session, settings: Config, user: OptionalUser
) -> Data[DailyProblemView]:
    return Data(data=await DailyProblemService(session, settings).today(user.id if user else None))


@router.get("/coins/rules", response_model=Data[CoinRules], tags=["coins"])
async def coin_rules() -> Data[CoinRules]:
    return Data(data=rules())


@router.get("/users/me/coins", response_model=Data[CoinWallet], tags=["coins"])
async def wallet(user: CurrentUser, session: Session) -> Data[CoinWallet]:
    return Data(data=await CoinService(session).wallet(user.id))


@router.get(
    "/users/me/coins/transactions", response_model=Page[CoinTransactionView], tags=["coins"]
)
async def transactions(
    user: CurrentUser, session: Session, page: PageNumber = 1, page_size: PageSize = 20
) -> Page[CoinTransactionView]:
    return await CoinService(session).history(user.id, page, page_size)


@router.post("/users/me/coins/check-in", response_model=Data[CheckInView], tags=["coins"])
async def check_in(
    user: CurrentUser, session: Session, payload: CheckInRequest | None = None
) -> Data[CheckInView]:
    return Data(data=await CoinService(session).check_in(user.id))


@router.get("/coins/rewards", response_model=Data[RewardCatalog], tags=["coins"])
async def rewards(session: Session) -> Data[RewardCatalog]:
    return Data(data=await OrderService(session).catalog())


@router.post("/coins/redeem", response_model=Data[OrderReceipt], status_code=201, tags=["orders"])
async def redeem(
    payload: RedeemRequest,
    user: CurrentUser,
    session: Session,
    response: Response,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> Data[OrderReceipt]:
    result = await OrderService(session).redeem(user.id, idempotency_key, payload)
    response.status_code = 200 if result.replayed else 201
    return Data(data=result)


@router.get("/users/me/orders", response_model=Page[OrderSummary], tags=["orders"])
async def orders(
    user: CurrentUser, session: Session, page: PageNumber = 1, page_size: PageSize = 20
) -> Page[OrderSummary]:
    return await OrderService(session).orders(user.id, page, page_size)


@router.get("/users/me/orders/{order_id}", response_model=Data[OrderDetail], tags=["orders"])
async def order(order_id: UUID, user: CurrentUser, session: Session) -> Data[OrderDetail]:
    return Data(
        data=OrderDetail.model_validate(await OrderService(session).owned(user.id, order_id))
    )


@router.post(
    "/users/me/orders/{order_id}/cancel", response_model=Data[OrderReceipt], tags=["orders"]
)
async def cancel_order(order_id: UUID, user: CurrentUser, session: Session) -> Data[OrderReceipt]:
    return Data(data=await OrderService(session).cancel(user.id, order_id))


@router.get("/admin/orders", response_model=Page[OrderSummary], tags=["fulfillment"])
async def fulfillment_queue(
    staff: CurrentStaff,
    session: Session,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    status: OrderStatus | None = None,
) -> Page[OrderSummary]:
    return await OrderService(session).orders(None, page, page_size, status)


@router.get("/admin/orders/{order_id}", response_model=Data[OrderDetail], tags=["fulfillment"])
async def fulfillment_order(
    order_id: UUID, staff: CurrentStaff, session: Session
) -> Data[OrderDetail]:
    return Data(data=OrderDetail.model_validate(await OrderService(session).staff_order(order_id)))


@router.patch("/admin/orders/{order_id}", response_model=Data[OrderDetail], tags=["fulfillment"])
async def update_fulfillment(
    order_id: UUID, payload: OrderStatusPatch, staff: CurrentStaff, session: Session
) -> Data[OrderDetail]:
    return Data(data=await OrderService(session).transition(order_id, payload))


@router.patch(
    "/admin/rewards/{reward_id}", response_model=Data[RewardProductView], tags=["fulfillment"]
)
async def update_availability(
    reward_id: str, payload: ProductAvailabilityPatch, staff: CurrentStaff, session: Session
) -> Data[RewardProductView]:
    return Data(data=await OrderService(session).availability(reward_id, payload))
