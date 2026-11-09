from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Difficulty, Question, Submission, SubmissionMode, User, UserProgress, Verdict
from app.schemas import LeaderboardEntry, Page, ProgressView, Statistics, UserView


def current_streak(days: set[date], today: date) -> int:
    end = today if today in days else today - timedelta(days=1)
    streak = 0
    while end in days:
        streak += 1
        end -= timedelta(days=1)
    return streak


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def public(self, username: str) -> UserView:
        user = await self.session.scalar(
            select(User).where(
                User.username == username.lower(),
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise AppError("not_found", "User not found", 404)
        return UserView.model_validate(user)

    async def update(self, user: User, bio: str) -> User:
        user.bio = bio
        await self.session.commit()
        return user

    async def progress(self, user_id: UUID, page: int, size: int) -> Page[ProgressView]:
        filters = [UserProgress.user_id == user_id]
        total = await self.session.scalar(
            select(func.count()).select_from(UserProgress).where(*filters)
        )
        rows = await self.session.scalars(
            select(UserProgress)
            .where(*filters)
            .order_by(UserProgress.created_at, UserProgress.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return Page(
            data=[ProgressView.model_validate(r) for r in rows],
            total=total or 0,
            page=page,
            page_size=size,
        )

    async def stats(self, user_id: UUID) -> Statistics:
        filters = [Submission.user_id == user_id, Submission.mode == SubmissionMode.SUBMIT]
        verdicts = dict(
            (
                await self.session.execute(
                    select(Submission.status, func.count())
                    .where(*filters)
                    .group_by(Submission.status)
                )
            )
            .tuples()
            .all()
        )
        languages = dict(
            (
                await self.session.execute(
                    select(Submission.language, func.count())
                    .where(*filters)
                    .group_by(Submission.language)
                )
            )
            .tuples()
            .all()
        )
        difficulties = dict(
            (
                await self.session.execute(
                    select(Question.difficulty, func.count())
                    .join(
                        UserProgress,
                        UserProgress.question_id == Question.id,
                    )
                    .where(UserProgress.user_id == user_id, UserProgress.solved_at.is_not(None))
                    .group_by(Question.difficulty)
                )
            )
            .tuples()
            .all()
        )
        date = cast(func.timezone("UTC", Submission.created_at), Date)
        activity = (
            await self.session.execute(
                select(date, func.count())
                .where(
                    *filters,
                    Submission.created_at <= datetime.now(UTC),
                )
                .group_by(date)
                .order_by(date)
            )
        ).all()
        evaluated = sum(
            count
            for status, count in verdicts.items()
            if status not in {Verdict.QUEUED, Verdict.RUNNING, Verdict.PROVIDER_ERROR}
        )
        today = datetime.now(UTC).date()
        return Statistics(
            submissions=sum(verdicts.values()),
            accepted_submissions=verdicts.get(Verdict.ACCEPTED, 0),
            solved_questions=sum(difficulties.values()),
            by_difficulty={item.value: difficulties.get(item, 0) for item in Difficulty},
            by_language={str(k): v for k, v in languages.items()},
            by_verdict={str(k): v for k, v in verdicts.items()},
            daily_activity={
                str(day): count for day, count in activity if day >= today - timedelta(days=364)
            },
            current_streak=current_streak({day for day, _ in activity}, today),
            acceptance_rate=round(100 * verdicts.get(Verdict.ACCEPTED, 0) / evaluated, 2)
            if evaluated
            else 0,
            evaluated_submissions=evaluated,
        )

    async def leaderboard(self, page: int, size: int) -> Page[LeaderboardEntry]:
        count = func.count(UserProgress.id).label("solved")
        base = (
            select(User.id, User.username, User.avatar_key, count)
            .join(
                UserProgress,
                UserProgress.user_id == User.id,
            )
            .where(User.is_active.is_(True), UserProgress.solved_at.is_not(None))
        )
        grouped = base.group_by(User.id, User.username)
        total = await self.session.scalar(select(func.count()).select_from(grouped.subquery()))
        rows = (
            await self.session.execute(
                grouped.order_by(count.desc(), User.username, User.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
        return Page(
            data=[
                LeaderboardEntry(
                    rank=(page - 1) * size + index + 1,
                    user_id=row.id,
                    username=row.username,
                    solved_questions=row.solved,
                    avatar_url=f"/api/v1/avatars/{row.avatar_key}" if row.avatar_key else None,
                )
                for index, row in enumerate(rows)
            ],
            total=total or 0,
            page=page,
            page_size=size,
        )
