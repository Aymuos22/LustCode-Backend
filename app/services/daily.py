"""One persisted UTC problem per day, shared across users and server restarts."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models import CoinReason, CoinTransaction, DailyChallenge, Question
from app.repositories import QuestionRepository
from app.schemas import DailyProblemView
from app.services.coins import DAILY_PROBLEM_COINS, day_window
from app.services.questions import QuestionService


class DailyProblemService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.repo = QuestionRepository(session)
        self.questions = QuestionService(self.repo, settings)

    async def ensure(self, day: date) -> DailyChallenge | None:
        assigned = await self.session.get(DailyChallenge, day)
        if assigned is not None:
            return assigned
        rows = list(
            await self.session.scalars(
                select(Question)
                .where(Question.published.is_(True))
                .order_by(*self.repo.catalog_order())
            )
        )
        counts = await self.repo.test_counts([row.id for row in rows])
        eligible = [
            row for row in rows if self.questions.summary(row, counts.get(row.id, 0)).is_judgeable
        ]
        if not eligible:
            return None
        offset = (day - date(2026, 1, 1)).days % len(eligible)
        for index in range(len(eligible)):
            question = eligible[(offset + index) % len(eligible)]
            if not (await self.questions.detail(question.id)).is_judgeable:
                continue
            await self.session.execute(
                insert(DailyChallenge)
                .values(day=day, question_id=question.id)
                .on_conflict_do_nothing(index_elements=[DailyChallenge.day])
            )
            # A concurrent request can win with a different catalog snapshot: its row wins.
            return await self.session.get(DailyChallenge, day)
        return None

    async def today(self, user_id: UUID | None) -> DailyProblemView:
        day = datetime.now(UTC).date()
        challenge = await self.ensure(day)
        if challenge is None:
            raise AppError(
                "daily_problem_unavailable", "No judgeable daily problem is available", 404
            )
        question = await self.session.get(Question, challenge.question_id)
        if question is None or not question.published:
            raise AppError(
                "daily_problem_unavailable", "Today's problem is temporarily unavailable", 409
            )
        detail = await self.questions.detail(question.id)
        if not detail.is_judgeable:
            raise AppError(
                "daily_problem_unavailable", "Today's problem is temporarily unavailable", 409
            )
        counts = await self.repo.test_counts([question.id])
        completed = None
        if user_id is not None:
            completed = (
                await self.session.scalar(
                    select(CoinTransaction.id).where(
                        CoinTransaction.user_id == user_id,
                        CoinTransaction.event_key
                        == f"{CoinReason.DAILY_PROBLEM.value}:{day.isoformat()}",
                    )
                )
                is not None
            )
        await self.session.commit()
        start, end = day_window(day)
        return DailyProblemView(
            date=day,
            starts_at=start,
            expires_at=end,
            question=self.questions.summary(question, counts.get(question.id, 0)),
            reward_coins=DAILY_PROBLEM_COINS,
            completed=completed,
            reward_claimed=completed,
        )
