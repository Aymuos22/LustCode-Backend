from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.core.errors import AppError, LeaseLost
from app.models import (
    Difficulty,
    Question,
    RefreshToken,
    Submission,
    SubmissionTestResult,
    TestCase,
    User,
    Verdict,
)


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def refresh_for_update(self, digest: str) -> RefreshToken | None:
        user_id = await self.session.scalar(
            select(RefreshToken.user_id).where(RefreshToken.token_hash == digest)
        )
        if user_id is None:
            return None
        # A common lock serializes rotation/replay across ALL generations in a family.
        # Locking only one token would let replay miss a concurrently inserted replacement.
        await self.session.scalar(select(User.id).where(User.id == user_id).with_for_update())
        return await self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def revoke_family(self, family_id: UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )


class QuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def catalog_filters(
        difficulty: Difficulty | None = None, search: str | None = None, topic: str | None = None
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [Question.published.is_(True)]
        if difficulty:
            filters.append(Question.difficulty == difficulty)
        if search:
            filters.append(Question.title.ilike(f"%{search}%", escape="\\"))
        if topic:
            filters.append(cast(Question.tags, JSONB).contains([topic]))
        return filters

    @staticmethod
    def catalog_order() -> tuple:
        return (
            Question.content["source"]["frontend_id"].as_integer().asc().nullslast(),
            Question.created_at,
            Question.id,
        )

    async def list_questions(
        self,
        page: int,
        size: int,
        difficulty: Difficulty | None,
        search: str | None,
        topic: str | None = None,
    ) -> tuple[list[Question], int]:
        filters = self.catalog_filters(difficulty, search, topic)
        total = await self.session.scalar(
            select(func.count()).select_from(Question).where(*filters)
        )
        rows = await self.session.scalars(
            select(Question)
            .where(*filters)
            .order_by(*self.catalog_order())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(rows), total or 0

    async def test_counts(self, question_ids: list[UUID]) -> dict[UUID, int]:
        if not question_ids:
            return {}
        rows = await self.session.execute(
            select(TestCase.question_id, func.count())
            .where(TestCase.question_id.in_(question_ids))
            .group_by(TestCase.question_id)
        )
        return dict(rows.tuples().all())

    async def published(self, question_id: UUID) -> Question:
        question = await self.session.scalar(
            select(Question).where(Question.id == question_id, Question.published.is_(True))
        )
        if not question:
            raise AppError("not_found", "Question not found", 404)
        return question

    async def tests(self, question_id: UUID, *, public_only: bool = False) -> list[TestCase]:
        stmt = select(TestCase).where(TestCase.question_id == question_id)
        if public_only:
            stmt = stmt.where(TestCase.hidden.is_(False))
        return list(await self.session.scalars(stmt.order_by(TestCase.position)))


class SubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def owned(self, submission_id: UUID, user_id: UUID) -> Submission:
        row = await self.session.scalar(
            select(Submission).where(Submission.id == submission_id, Submission.user_id == user_id)
        )
        if not row:
            raise AppError("not_found", "Submission not found", 404)
        return row

    async def results(self, submission_id: UUID) -> list[SubmissionTestResult]:
        return list(
            await self.session.scalars(
                select(SubmissionTestResult)
                .where(SubmissionTestResult.submission_id == submission_id)
                .order_by(SubmissionTestResult.position)
            )
        )

    async def list_submissions(
        self,
        user_id: UUID,
        page: int,
        size: int,
        question_id: UUID | None,
    ) -> tuple[list[Submission], int]:
        filters = [Submission.user_id == user_id]
        if question_id:
            filters.append(Submission.question_id == question_id)
        total = await self.session.scalar(
            select(func.count()).select_from(Submission).where(*filters)
        )
        rows = await self.session.scalars(
            select(Submission)
            .where(*filters)
            .order_by(Submission.created_at.desc(), Submission.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(rows), total or 0

    async def claim(self, settings: Settings) -> Submission | None:
        now = datetime.now(UTC)
        row = await self.session.scalar(
            select(Submission)
            .where(
                or_(
                    Submission.status == Verdict.QUEUED,
                    and_(Submission.status == Verdict.RUNNING, Submission.lease_until < now),
                )
            )
            .order_by(Submission.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        if row.attempts >= settings.worker_max_attempts:
            await self.fail(row)
            await self.session.commit()
            return None
        row.status = Verdict.RUNNING
        row.attempts += 1
        row.lease_id = uuid4()
        row.lease_until = now + timedelta(seconds=settings.worker_lease_seconds)
        await self.session.commit()
        return row

    async def fail(self, row: Submission) -> None:
        results = await self.results(row.id)
        for result in results:
            if result.status in (Verdict.QUEUED, Verdict.RUNNING):
                result.status = Verdict.PROVIDER_ERROR
        row.status = Verdict.PROVIDER_ERROR
        row.completed_at = datetime.now(UTC)
        row.lease_until = None
        row.passed_tests = sum(result.status == Verdict.ACCEPTED for result in results)
        row.execution_time = sum(result.execution_time or 0 for result in results)
        row.memory_used_kb = max((result.memory_kb or 0 for result in results), default=0)

    async def locked_lease(self, submission_id: UUID, lease_id: UUID) -> Submission:
        row = await self.session.scalar(
            select(Submission)
            .where(Submission.id == submission_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.lease_id != lease_id or row.status != Verdict.RUNNING:
            raise LeaseLost()
        return row
