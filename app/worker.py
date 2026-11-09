import asyncio
import logging
import signal
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import LeaseLost, ProviderError
from app.core.logging import configure_logging
from app.integrations.judge0 import ExecutionProvider, ExecutionResult
from app.judging.compare import compare_output
from app.judging.contracts import JudgeProfile
from app.judging.drivers import build_source
from app.judging.wire import INVALID_RESULT, pack_stdin
from app.models import (
    Language,
    Submission,
    SubmissionMode,
    SubmissionTestResult,
    UserProgress,
    Verdict,
)
from app.repositories import SubmissionRepository
from app.runtime import runtime_resources

logger = logging.getLogger(__name__)


class EvaluationWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        provider: ExecutionProvider,
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.provider = provider
        self.settings = settings

    async def checkpoint(
        self,
        submission_id: UUID,
        lease_id: UUID,
        result_id: UUID,
        *,
        token: str | None = None,
        result: ExecutionResult | None = None,
    ) -> None:
        async with self.sessions() as session:
            submission = await SubmissionRepository(session).locked_lease(submission_id, lease_id)
            row = await session.get(SubmissionTestResult, result_id)
            if row is None:
                raise LeaseLost()
            if token is not None:
                row.provider_token = token
            if result is None:
                row.status = Verdict.RUNNING
            if result:
                row.status = result.status
                # Compare full bounded provider output before truncating stored diagnostics.
                row.stdout = result.stdout[:16384] if result.stdout is not None else None
                row.stderr = result.stderr
                row.compile_output = result.compile_output
                row.execution_time = result.execution_time
                row.memory_kb = result.memory_kb
            submission.lease_until = datetime.now(UTC) + timedelta(
                seconds=self.settings.worker_lease_seconds
            )
            await session.commit()

    async def finish(self, submission_id: UUID, lease_id: UUID) -> None:
        async with self.sessions() as session:
            repo = SubmissionRepository(session)
            row = await repo.locked_lease(submission_id, lease_id)
            results = await repo.results(submission_id)
            row.passed_tests = sum(t.status == Verdict.ACCEPTED for t in results)
            row.status = next(
                (t.status for t in results if t.status != Verdict.ACCEPTED), Verdict.ACCEPTED
            )
            row.execution_time = sum(t.execution_time or 0 for t in results)
            row.memory_used_kb = max((t.memory_kb or 0 for t in results), default=0)
            row.completed_at = datetime.now(UTC)
            row.lease_until = None
            if row.mode == SubmissionMode.SUBMIT and row.status == Verdict.ACCEPTED:
                await session.execute(
                    update(UserProgress)
                    .where(
                        UserProgress.user_id == row.user_id,
                        UserProgress.question_id == row.question_id,
                        UserProgress.solved_at.is_(None),
                    )
                    .values(solved_at=row.completed_at)
                )
            await session.commit()

    async def process(self, submission: Submission) -> None:
        if submission.lease_id is None:
            raise LeaseLost()
        lease_id = submission.lease_id
        profile = (
            JudgeProfile.model_validate(submission.evaluation) if submission.evaluation else None
        )
        async with self.sessions() as session:
            results = await SubmissionRepository(session).results(submission.id)
        for row in results:
            if row.status not in (Verdict.QUEUED, Verdict.RUNNING, Verdict.PROVIDER_ERROR):
                continue
            try:
                await self.checkpoint(submission.id, lease_id, row.id)
                token = row.provider_token
                if token is None:
                    token = await self.provider.create(
                        build_source(
                            submission.source_code, submission.language, row.stdin, profile
                        )
                        if profile
                        else submission.source_code,
                        submission.language_id,
                        pack_stdin(row.stdin, submission.language) if profile else row.stdin,
                        None if profile else row.expected_output,
                        submission.cpu_seconds,
                        submission.memory_kb,
                        compiler_options="-std=c++17"
                        if profile and submission.language == Language.CPP
                        else None,
                    )
                    await self.checkpoint(submission.id, lease_id, row.id, token=token)
                result = await self.provider.poll(token)
                if (
                    profile
                    and result.status == Verdict.ACCEPTED
                    and row.expected_output is not None
                ):
                    result.status = (
                        Verdict.ACCEPTED
                        if compare_output(
                            result.stdout, row.expected_output or "", row.stdin, profile
                        )
                        else Verdict.WRONG_ANSWER
                    )
                    if result.stdout and result.stdout.strip() == INVALID_RESULT:
                        result.stdout = None
                        result.stderr = "Returned value violates the question's evaluation contract"
                elif profile and result.status == Verdict.ACCEPTED:
                    if result.stdout and result.stdout.strip() == INVALID_RESULT:
                        result.status = Verdict.RUNTIME_ERROR
                        result.stdout = None
                        result.stderr = "Returned value violates the question's evaluation contract"
                await self.checkpoint(submission.id, lease_id, row.id, result=result)
                if result.status == Verdict.PROVIDER_ERROR:
                    raise ProviderError(retryable=False)
            except ProviderError as exc:
                # Keep a known token, so recovery polls it without resubmitting source.
                async with self.sessions() as session:
                    repo = SubmissionRepository(session)
                    current = await repo.locked_lease(submission.id, lease_id)
                    if not exc.retryable or current.attempts >= self.settings.worker_max_attempts:
                        await repo.fail(current)
                    else:
                        current.lease_until = datetime.now(UTC) + timedelta(
                            seconds=max(15 * current.attempts, exc.retry_after or 0)
                        )
                    await session.commit()
                return
        await self.finish(submission.id, lease_id)

    async def once(self) -> bool:
        async with self.sessions() as session:
            submission = await SubmissionRepository(session).claim(self.settings)
        if submission is None:
            return False
        await self.process(submission)
        return True


async def main() -> None:
    configure_logging()
    settings = Settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    try:
        async with runtime_resources(settings) as resources:
            worker = EvaluationWorker(resources.sessions, resources.provider, settings)
            logger.info("Evaluation worker started")
            while not stop.is_set():
                try:
                    if not await worker.once():
                        try:
                            await cast(
                                Awaitable[object], resources.redis.blpop("worker:wakeup", timeout=2)
                            )
                        except RedisError:
                            await asyncio.sleep(2)
                except LeaseLost:
                    logger.warning("Evaluation lease transferred to another worker")
                except SQLAlchemyError:
                    logger.exception("Database unavailable during evaluation; lease will recover")
                    await asyncio.sleep(2)
                except Exception:
                    # Process boundary: log classification, retain durable work for lease recovery.
                    logger.exception("Unexpected evaluation failure; lease will recover")
                    await asyncio.sleep(2)
    finally:
        for name in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(name)


if __name__ == "__main__":
    asyncio.run(main())
