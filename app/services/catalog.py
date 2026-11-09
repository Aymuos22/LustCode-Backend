from collections import Counter
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Difficulty, Question, QuestionCollection, UserProgress
from app.repositories import QuestionRepository
from app.schemas import (
    CollectionDetail,
    CollectionView,
    FeaturedQuestions,
    Page,
    QuestionNavigation,
    QuestionSummary,
    TopicView,
)
from app.services.questions import QuestionService


class CatalogService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.repo = QuestionRepository(session)
        self.questions = QuestionService(self.repo, settings)

    async def topics(self) -> list[TopicView]:
        tags = await self.session.scalars(select(Question.tags).where(Question.published.is_(True)))
        counts: Counter[str] = Counter()
        for row in tags:
            counts.update(set(row))
        return [
            TopicView(slug=slug, name=slug.replace("-", " ").title(), question_count=count)
            for slug, count in sorted(counts.items())
        ]

    async def random(
        self, difficulty: Difficulty | None, search: str | None, topic: str | None
    ) -> QuestionSummary:
        question = await self.session.scalar(
            select(Question)
            .where(*self.repo.catalog_filters(difficulty, search, topic))
            .order_by(func.random())
            .limit(1)
        )
        if question is None:
            raise AppError("no_matching_questions", "No questions match these filters", 404)
        counts = await self.repo.test_counts([question.id])
        return self.questions.summary(question, counts.get(question.id, 0))

    async def featured(self, limit: int) -> FeaturedQuestions:
        page = await self.questions.list(1, limit, None, None)
        return FeaturedQuestions(questions=page.data)

    async def navigation(
        self,
        question_id: UUID,
        difficulty: Difficulty | None,
        search: str | None,
        topic: str | None,
    ) -> QuestionNavigation:
        await self.repo.published(question_id)
        order = self.repo.catalog_order()
        ranked = (
            select(
                Question.id,
                func.lag(Question.id).over(order_by=order).label("previous_id"),
                func.lead(Question.id).over(order_by=order).label("next_id"),
                func.row_number().over(order_by=order).label("position"),
                func.count().over().label("total"),
            )
            .where(*self.repo.catalog_filters(difficulty, search, topic))
            .subquery()
        )
        row = (
            (await self.session.execute(select(ranked).where(ranked.c.id == question_id)))
            .mappings()
            .first()
        )
        if row is None:
            raise AppError(
                "question_not_in_catalog", "Question is outside the filtered catalog", 404
            )
        return QuestionNavigation(
            question_id=question_id,
            **{k: row[k] for k in ["previous_id", "next_id", "position", "total"]},
        )

    async def collection_views(
        self, rows: list[QuestionCollection], user_id: UUID | None
    ) -> list[CollectionView]:
        counts: dict[Difficulty, int] = dict(
            (
                await self.session.execute(
                    select(Question.difficulty, func.count())
                    .where(Question.published.is_(True))
                    .group_by(Question.difficulty)
                )
            )
            .tuples()
            .all()
        )
        solved: dict[Difficulty, int] = {}
        if user_id:
            solved = dict(
                (
                    await self.session.execute(
                        select(Question.difficulty, func.count())
                        .join(UserProgress, UserProgress.question_id == Question.id)
                        .where(
                            Question.published.is_(True),
                            UserProgress.user_id == user_id,
                            UserProgress.solved_at.is_not(None),
                        )
                        .group_by(Question.difficulty)
                    )
                )
                .tuples()
                .all()
            )
        result = []
        for row in rows:
            count = counts.get(row.difficulty, 0)
            done = solved.get(row.difficulty, 0) if user_id else None
            result.append(
                CollectionView(
                    id=row.id,
                    slug=row.slug,
                    name=row.name,
                    description=row.description,
                    position=row.position,
                    difficulty=row.difficulty,
                    question_count=count,
                    solved_count=done,
                    completion_percentage=(round(100 * done / count, 2) if count else 0)
                    if done is not None
                    else None,
                )
            )
        return result

    async def collections(self, user_id: UUID | None, page: int, size: int) -> Page[CollectionView]:
        count = await self.session.scalar(select(func.count()).select_from(QuestionCollection))
        rows = list(
            await self.session.scalars(
                select(QuestionCollection)
                .order_by(QuestionCollection.position, QuestionCollection.id)
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        return Page(
            data=await self.collection_views(rows, user_id),
            total=count or 0,
            page=page,
            page_size=size,
        )

    async def collection(
        self,
        collection_id: UUID,
        user_id: UUID | None,
        page: int,
        size: int,
        topic: str | None,
        search: str | None,
    ) -> CollectionDetail:
        row = await self.session.get(QuestionCollection, collection_id)
        if row is None:
            raise AppError("not_found", "Collection not found", 404)
        return CollectionDetail(
            collection=(await self.collection_views([row], user_id))[0],
            questions=await self.questions.list(page, size, row.difficulty, search, topic),
        )
