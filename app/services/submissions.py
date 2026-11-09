import json
import logging
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.integrations.judge0 import ExecutionProvider, select_language
from app.integrations.redis import Limits
from app.judging.contracts import JudgeProfile, arguments, suite_hash
from app.judging.readiness import readiness
from app.models import Submission, SubmissionMode, SubmissionTestResult, User, UserProgress, Verdict
from app.repositories import QuestionRepository, SubmissionRepository
from app.schemas import ResultView, RunRequest, SampleRunRequest, SubmissionView, SubmitRequest

logger = logging.getLogger(__name__)


class SubmissionService:
    def __init__(
        self,
        session: AsyncSession,
        provider: ExecutionProvider,
        limits: Limits,
        settings: Settings,
        redis: Redis,
    ) -> None:
        self.session = session
        self.provider = provider
        self.limits = limits
        self.settings = settings
        self.redis = redis

    async def run_samples(
        self, user_id: UUID, question_id: UUID, payload: SampleRunRequest
    ) -> Submission:
        return await self.create(
            user_id,
            SubmitRequest(question_id=question_id, **payload.model_dump(exclude={"test_cases"})),
            samples_only=True,
            custom_cases=[case.stdin for case in payload.test_cases]
            if payload.test_cases
            else None,
        )

    async def create(
        self,
        user_id: UUID,
        payload: SubmitRequest | RunRequest,
        *,
        samples_only: bool = False,
        custom_cases: list[str] | None = None,
    ) -> Submission:
        tests: list[dict[str, object]] = []
        evaluation: dict = {}
        profile: JudgeProfile | None = None
        question_id = None
        cpu = min(2.0, self.settings.max_cpu_seconds)
        memory = min(131072, self.settings.max_memory_kb)
        mode = SubmissionMode.RUN
        if isinstance(payload, SubmitRequest):
            questions = QuestionRepository(self.session)
            question = await questions.published(payload.question_id)
            cases = await questions.tests(question.id)
            status, ready_languages = readiness(question, len(cases), self.settings.max_test_cases)
            if status != "ready":
                raise AppError(
                    "question_unavailable", "Question has no valid evaluation test suite", 409
                )
            if payload.language not in ready_languages:
                raise AppError(
                    "language_unavailable",
                    "This question has no verified driver for that language",
                    422,
                )
            if raw_profile := question.content.get("judging"):
                try:
                    profile = JudgeProfile.model_validate(raw_profile)
                    if suite_hash(
                        [
                            {
                                "stdin": c.stdin,
                                "expected_output": c.expected_output,
                                "hidden": c.hidden,
                            }
                            for c in cases
                        ]
                    ) != profile.suite_sha256 or [c.position for c in cases] != list(
                        range(len(cases))
                    ):
                        raise ValueError("Evaluation suite changed without verification")
                    for case in cases:
                        arguments(case.stdin, profile)
                        # Expected data stays only in the private case snapshot.
                        json.loads(case.expected_output)
                except (ValueError, TypeError):
                    raise AppError(
                        "question_unavailable", "Question evaluation suite is invalid", 409
                    ) from None
                evaluation = profile.model_dump(mode="json")
            selected = [case for case in cases if not case.hidden] if samples_only else cases
            if not selected and custom_cases is None:
                raise AppError(
                    "samples_unavailable", "Question has no executable visible samples", 409
                )
            tests = [
                dict(
                    test_case_id=t.id,
                    position=position,
                    hidden=t.hidden,
                    stdin=t.stdin,
                    expected_output=t.expected_output,
                )
                for position, t in enumerate(selected)
            ]
            if custom_cases is not None:
                if not samples_only or profile is None:
                    raise AppError(
                        "custom_run_unavailable", "Question has no custom-input contract", 409
                    )
                try:
                    for stdin in custom_cases:
                        arguments(stdin, profile)
                except (ValueError, TypeError, OverflowError, RecursionError):
                    raise AppError(
                        "invalid_custom_input",
                        "Custom cases do not match the evaluation contract",
                        422,
                    ) from None
                tests = [
                    dict(position=i, hidden=False, stdin=value, expected_output=None)
                    for i, value in enumerate(custom_cases)
                ]
            question_id = question.id
            cpu = min(question.cpu_seconds, self.settings.max_cpu_seconds)
            memory = min(question.memory_kb, self.settings.max_memory_kb)
            mode = SubmissionMode.RUN if samples_only else SubmissionMode.SUBMIT
        else:
            tests = [dict(position=0, hidden=False, stdin=payload.stdin, expected_output=None)]
        language = await select_language(self.provider, payload.language, payload.language_id)
        # Serialize per-user admission; simultaneous requests cannot bypass the pending cap.
        await self.session.scalar(select(User).where(User.id == user_id).with_for_update())
        pending = await self.session.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.user_id == user_id,
                Submission.status.in_([Verdict.QUEUED, Verdict.RUNNING]),
            )
        )
        if (pending or 0) >= self.settings.max_pending_submissions:
            raise AppError("pending_limit", "Too many unfinished submissions", 429)
        await self.limits.execution(str(user_id), len(tests))
        submission = Submission(
            user_id=user_id,
            question_id=question_id,
            language=payload.language,
            language_id=language.id,
            language_version=language.name,
            source_code=payload.source_code,
            evaluation=evaluation,
            custom_input=custom_cases is not None,
            mode=mode,
            cpu_seconds=cpu,
            memory_kb=memory,
            total_tests=len(tests),
        )
        self.session.add(submission)
        await self.session.flush()
        self.session.add_all(
            [SubmissionTestResult(submission_id=submission.id, **test) for test in tests]
        )
        if mode == SubmissionMode.SUBMIT:
            stmt = insert(UserProgress).values(
                user_id=user_id,
                question_id=question_id,
                attempts=1,
                last_submission_id=submission.id,
            )
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[UserProgress.user_id, UserProgress.question_id],
                    set_={
                        "attempts": UserProgress.attempts + 1,
                        "last_submission_id": submission.id,
                    },
                )
            )
        await self.session.commit()
        try:
            # Bounded wakeup queue; PostgreSQL is the durable source of work.
            async with self.redis.pipeline(transaction=True) as pipeline:
                pipeline.lpush("worker:wakeup", "1")
                pipeline.ltrim("worker:wakeup", 0, 99)
                await pipeline.execute()
        except RedisError:
            logger.warning("Worker wakeup unavailable; database polling will recover submission")
        return submission

    async def detail(self, submission_id: UUID, user_id: UUID) -> SubmissionView:
        repo = SubmissionRepository(self.session)
        submission = await repo.owned(submission_id, user_id)
        results = await repo.results(submission.id)
        views = []
        for row in results:
            views.append(
                ResultView(
                    position=row.position,
                    hidden=row.hidden,
                    status=row.status,
                    execution_time=row.execution_time,
                    memory_kb=row.memory_kb,
                    stdin=None if row.hidden else row.stdin,
                    expected_output=None if row.hidden else row.expected_output,
                    stdout=None if row.hidden else row.stdout,
                    stderr=None if row.hidden else row.stderr,
                    compile_output=None if row.hidden else row.compile_output,
                )
            )
        values = {
            field: getattr(submission, field)
            for field in SubmissionView.model_fields
            if field != "results"
        }
        return SubmissionView(**values, results=views)
