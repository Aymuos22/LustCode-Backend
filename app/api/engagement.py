from fastapi import APIRouter

from app.api.dependencies import Config, CurrentUser, OptionalUser, Session
from app.api.features import PageNumber, PageSize
from app.core.errors import AppError
from app.schemas import (
    CheckInRequest,
    CheckInView,
    CoinRules,
    CoinTransactionView,
    CoinWallet,
    DailyProblemView,
    Data,
    Page,
    RedeemRequest,
    RewardCatalog,
    StreakView,
)
from app.services.coins import CoinService, reward_catalog, rules
from app.services.daily import DailyProblemService
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
async def rewards() -> Data[RewardCatalog]:
    return Data(data=reward_catalog())


@router.post("/coins/redeem", response_model=Data[CoinWallet], tags=["coins"])
async def redeem(payload: RedeemRequest, user: CurrentUser) -> Data[CoinWallet]:
    if payload.reward_id not in {r.id for r in reward_catalog().rewards}:
        raise AppError("reward_not_found", "Reward not found", 404)
    raise AppError("redemption_unavailable", "Rewards are coming soon; no coins were spent", 409)
