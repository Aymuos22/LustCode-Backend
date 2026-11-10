"""Server-authored, idempotent coin credits backed by PostgreSQL, never Redis."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CoinReason,
    CoinTransaction,
    DailyChallenge,
    Submission,
    SubmissionMode,
    User,
    Verdict,
)
from app.schemas import (
    CheckInView,
    CoinRules,
    CoinTransactionView,
    CoinWallet,
    Page,
    RewardCatalog,
    RewardPlaceholder,
)

CHECK_IN_COINS = 5
DAILY_PROBLEM_COINS = 20


def day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def rules() -> CoinRules:
    return CoinRules(daily_check_in=CHECK_IN_COINS, daily_problem=DAILY_PROBLEM_COINS)


def reward_catalog() -> RewardCatalog:
    return RewardCatalog(
        rewards=[
            RewardPlaceholder(
                id="profile-badges",
                name="Profile badges",
                description="Collectible profile badges. Details and pricing coming soon.",
            ),
            RewardPlaceholder(
                id="editor-themes",
                name="Editor themes",
                description="Additional editor themes. Details and pricing coming soon.",
            ),
            RewardPlaceholder(
                id="lustcode-stickers",
                name="LustCode stickers",
                description="Sticker rewards. Availability and pricing coming soon.",
            ),
            RewardPlaceholder(
                id="lustcode-shirt",
                name="LustCode T-shirt",
                description="Merchandise rewards. Availability and pricing coming soon.",
            ),
        ]
    )


class CoinService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_user(self, user_id: UUID) -> None:
        # Match admission/auth lock ordering before credit FKs or progress updates.
        await self.session.scalar(select(User.id).where(User.id == user_id).with_for_update())

    async def credit(
        self,
        user_id: UUID,
        reason: CoinReason,
        day: date,
        *,
        question_id: UUID | None = None,
        submission_id: UUID | None = None,
    ) -> tuple[CoinTransaction, bool]:
        amount = CHECK_IN_COINS if reason == CoinReason.DAILY_CHECK_IN else DAILY_PROBLEM_COINS
        key = f"{reason.value}:{day.isoformat()}"
        identifier = await self.session.scalar(
            insert(CoinTransaction)
            .values(
                user_id=user_id,
                amount=amount,
                reason=reason,
                reward_date=day,
                event_key=key,
                question_id=question_id,
                submission_id=submission_id,
            )
            .on_conflict_do_nothing(
                index_elements=[CoinTransaction.user_id, CoinTransaction.event_key]
            )
            .returning(CoinTransaction.id)
        )
        transaction = await self.session.scalar(
            select(CoinTransaction).where(
                CoinTransaction.user_id == user_id, CoinTransaction.event_key == key
            )
        )
        assert transaction is not None
        return transaction, identifier is not None

    async def wallet(self, user_id: UUID, now: datetime | None = None) -> CoinWallet:
        day = (now or datetime.now(UTC)).astimezone(UTC).date()
        total = await self.session.scalar(
            select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
                CoinTransaction.user_id == user_id
            )
        )
        checked_in = await self.session.scalar(
            select(CoinTransaction.id).where(
                CoinTransaction.user_id == user_id,
                CoinTransaction.event_key == f"daily_check_in:{day.isoformat()}",
            )
        )
        return CoinWallet(
            balance=total or 0,
            total_earned=total or 0,
            check_in_claimed_today=checked_in is not None,
            next_reset_at=day_window(day)[1],
            rules=rules(),
        )

    async def check_in(self, user_id: UUID) -> CheckInView:
        now = datetime.now(UTC)
        await self.lock_user(user_id)
        transaction, awarded = await self.credit(user_id, CoinReason.DAILY_CHECK_IN, now.date())
        await self.session.commit()
        return CheckInView(
            awarded=awarded,
            credited_amount=transaction.amount if awarded else 0,
            transaction=CoinTransactionView.model_validate(transaction),
            wallet=await self.wallet(user_id, now),
        )

    async def history(self, user_id: UUID, page: int, size: int) -> Page[CoinTransactionView]:
        predicate = CoinTransaction.user_id == user_id
        count = await self.session.scalar(
            select(func.count()).select_from(CoinTransaction).where(predicate)
        )
        rows = await self.session.scalars(
            select(CoinTransaction)
            .where(predicate)
            .order_by(CoinTransaction.created_at.desc(), CoinTransaction.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return Page(
            data=[CoinTransactionView.model_validate(row) for row in rows],
            total=count or 0,
            page=page,
            page_size=size,
        )

    async def award_daily_problem(self, submission: Submission) -> None:
        day = submission.daily_challenge_date
        if (
            submission.mode != SubmissionMode.SUBMIT
            or submission.status != Verdict.ACCEPTED
            or day is None
            or submission.created_at.astimezone(UTC).date() != day
        ):
            return
        challenge = await self.session.get(DailyChallenge, day)
        if challenge is None or challenge.question_id != submission.question_id:
            return
        await self.credit(
            submission.user_id,
            CoinReason.DAILY_PROBLEM,
            day,
            question_id=submission.question_id,
            submission_id=submission.id,
        )
