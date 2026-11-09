import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import LeaseLost, ProviderError
from app.integrations.judge0 import ExecutionResult
from app.models import (
    Difficulty,
    Question,
    Submission,
    UserProgress,
    Verdict,
)
from app.models import (
    TestCase as Case,
)
from app.repositories import SubmissionRepository
from app.worker import EvaluationWorker

pytestmark = pytest.mark.integration


async def register(api, username="coder") -> dict:
    response = await api.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "a-good-password-123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
async def question_id(sessions) -> UUID:
    async with sessions() as session:
        question = Question(
            slug="fixture",
            title="Fixture",
            statement="Fixture only",
            difficulty=Difficulty.EASY,
            published=True,
            content={"hints": ["hint"], "secret_tests": "do-not-leak"},
        )
        session.add(question)
        await session.flush()
        session.add_all(
            [
                Case(
                    question_id=question.id,
                    position=0,
                    stdin="sample",
                    expected_output="public",
                    hidden=False,
                ),
                Case(
                    question_id=question.id,
                    position=1,
                    stdin="hidden-input",
                    expected_output="hidden-expected",
                    hidden=True,
                ),
            ]
        )
        await session.commit()
        return question.id


async def submit(api, tokens, question_id) -> dict:
    response = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={
            "question_id": str(question_id),
            "language": "python",
            "source_code": "print(input())",
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]


async def test_auth_rotation_reuse_and_logout(api) -> None:
    first = await register(api)
    assert (await api.get("/api/v1/users/me", headers=auth(first))).json()["data"][
        "email"
    ] == "coder@example.com"
    duplicate = await api.post(
        "/api/v1/auth/register",
        json={
            "email": "coder@example.com",
            "username": "other",
            "password": "a-good-password-123",
        },
    )
    assert duplicate.status_code == 409
    wrong = await api.post(
        "/api/v1/auth/login", json={"email": "coder@example.com", "password": "wrong-password-123"}
    )
    assert wrong.status_code == 401
    rotated = await api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()["data"]
    assert (
        await api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    ).status_code == 401
    assert (
        await api.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    ).status_code == 401
    login = await api.post(
        "/api/v1/auth/login", json={"email": "coder@example.com", "password": "a-good-password-123"}
    )
    third = login.json()["data"]
    assert (
        await api.post("/api/v1/auth/logout", json={"refresh_token": third["refresh_token"]})
    ).status_code == 204
    assert (
        await api.post("/api/v1/auth/refresh", json={"refresh_token": third["refresh_token"]})
    ).status_code == 401


async def test_simultaneous_refresh_invalidates_family(api) -> None:
    tokens = await register(api)
    responses = await asyncio.gather(
        *[
            api.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response.json()["data"] for response in responses if response.status_code == 200)
    assert (
        await api.post("/api/v1/auth/refresh", json={"refresh_token": winner["refresh_token"]})
    ).status_code == 401


async def test_question_privacy_filters_and_unpublished(api, sessions, question_id) -> None:
    response = await api.get(f"/api/v1/questions/{question_id}")
    assert response.status_code == 200
    assert response.json()["data"]["samples"] == [{"stdin": "sample", "expected_output": "public"}]
    assert "hidden-input" not in response.text and "do-not-leak" not in response.text
    assert (await api.get("/api/v1/questions?difficulty=hard")).json()["total"] == 0
    async with sessions() as session:
        row = await session.get(Question, question_id)
        row.published = False
        await session.commit()
    assert (await api.get(f"/api/v1/questions/{question_id}")).status_code == 404


async def test_complete_evaluation_privacy_ownership_and_progress(
    api,
    sessions,
    provider,
    settings,
    question_id,
) -> None:
    owner = await register(api)
    other = await register(api, "other")
    submitted = await submit(api, owner, question_id)
    provider.results = [
        ExecutionResult(
            status=Verdict.ACCEPTED, stdout="public-output", execution_time=0.1, memory_kb=500
        ),
        ExecutionResult(
            status=Verdict.ACCEPTED,
            stdout="hidden-input",
            stderr="hidden-expected",
            compile_output="hidden-compiler-output",
            execution_time=0.2,
            memory_kb=1000,
        ),
    ]
    worker = EvaluationWorker(sessions, provider, settings)
    assert await worker.once()
    assert not await worker.once()
    detail = await api.get(f"/api/v1/submissions/{submitted['id']}", headers=auth(owner))
    data = detail.json()["data"]
    assert data["status"] == "accepted" and data["passed_tests"] == 2
    assert data["execution_time"] == pytest.approx(0.3) and data["memory_used_kb"] == 1000
    assert data["results"][0]["stdout"] == "public-output"
    assert data["results"][1]["stdout"] is None
    assert all(
        value not in detail.text
        for value in ("hidden-input", "hidden-expected", "hidden-compiler-output", "provider_token")
    )
    assert (
        await api.get(f"/api/v1/submissions/{submitted['id']}", headers=auth(other))
    ).status_code == 404
    assert (await api.get("/api/v1/submissions", headers=auth(other))).json()["total"] == 0
    stats = (await api.get("/api/v1/users/me/statistics", headers=auth(owner))).json()["data"]
    assert stats["submissions"] == 1 and stats["solved_questions"] == 1
    assert stats["by_difficulty"]["easy"] == 1
    progress = (await api.get("/api/v1/users/me/progress", headers=auth(owner))).json()["data"]
    assert progress[0]["attempts"] == 1 and progress[0]["solved_at"] is not None
    leaderboard = (await api.get("/api/v1/leaderboard")).json()["data"]
    assert leaderboard[0]["username"] == "coder" and leaderboard[0]["solved_questions"] == 1


async def test_run_does_not_award_progress(api, sessions, provider, settings) -> None:
    tokens = await register(api)
    response = await api.post(
        "/api/v1/runs",
        headers=auth(tokens),
        json={
            "language": "java",
            "source_code": "class Main {}",
            "stdin": "custom-input",
        },
    )
    assert response.status_code == 202
    assert await EvaluationWorker(sessions, provider, settings).once()
    assert (
        provider.created[0]["stdin"] == "custom-input" and provider.created[0]["expected"] is None
    )
    stats = (await api.get("/api/v1/users/me/statistics", headers=auth(tokens))).json()["data"]
    assert stats["submissions"] == 0 and stats["solved_questions"] == 0


@pytest.mark.parametrize(
    "verdict",
    [
        Verdict.WRONG_ANSWER,
        Verdict.COMPILATION_ERROR,
        Verdict.RUNTIME_ERROR,
        Verdict.TIME_LIMIT_EXCEEDED,
        Verdict.MEMORY_LIMIT_EXCEEDED,
    ],
)
async def test_failed_evaluation_does_not_solve(
    api, sessions, provider, settings, question_id, verdict
) -> None:
    tokens = await register(api)
    item = await submit(api, tokens, question_id)
    provider.results = [ExecutionResult(status=verdict), ExecutionResult(status=Verdict.ACCEPTED)]
    await EvaluationWorker(sessions, provider, settings).once()
    detail = (await api.get(f"/api/v1/submissions/{item['id']}", headers=auth(tokens))).json()[
        "data"
    ]
    assert detail["status"] == verdict and detail["passed_tests"] == 1
    async with sessions() as session:
        assert (await session.scalar(select(UserProgress))).solved_at is None


async def test_restart_reuses_persisted_token(
    api, sessions, provider, settings, question_id
) -> None:
    tokens = await register(api)
    item = await submit(api, tokens, question_id)
    worker = EvaluationWorker(sessions, provider, settings)
    async with sessions() as session:
        claimed = await SubmissionRepository(session).claim(settings)
        result = (await SubmissionRepository(session).results(claimed.id))[0]
    await worker.checkpoint(claimed.id, claimed.lease_id, result.id, token="existing-token")
    async with sessions() as session:
        row = await session.get(Submission, claimed.id)
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert await worker.once()
    assert provider.polled[0] == "existing-token" and len(provider.created) == 1
    with pytest.raises(LeaseLost):
        await worker.checkpoint(claimed.id, claimed.lease_id, result.id, token="stale-worker-token")
    assert (await api.get(f"/api/v1/submissions/{item['id']}", headers=auth(tokens))).json()[
        "data"
    ]["status"] == "accepted"


async def test_provider_failure_retries_and_terminates(
    api, sessions, provider, settings, question_id
) -> None:
    tokens = await register(api)
    item = await submit(api, tokens, question_id)
    provider.error = ProviderError()
    worker = EvaluationWorker(sessions, provider, settings)
    for _ in range(settings.worker_max_attempts):
        assert await worker.once()
        async with sessions() as session:
            row = await session.get(Submission, UUID(item["id"]))
            if row.lease_until:
                row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
    assert not await worker.once()
    detail = (await api.get(f"/api/v1/submissions/{item['id']}", headers=auth(tokens))).json()[
        "data"
    ]
    assert detail["status"] == "provider_error"


async def test_permanent_provider_error_terminates_without_repeated_submissions(
    api,
    sessions,
    provider,
    settings,
    question_id,
) -> None:
    tokens = await register(api)
    item = await submit(api, tokens, question_id)
    provider.error = ProviderError(retryable=False)
    worker = EvaluationWorker(sessions, provider, settings)
    assert await worker.once()
    assert not await worker.once()
    async with sessions() as session:
        row = await session.get(Submission, UUID(item["id"]))
        assert row.status == Verdict.PROVIDER_ERROR and row.attempts == 1
        assert row.completed_at is not None


async def test_worker_honors_provider_cooldown_without_blocking_other_jobs(
    api,
    sessions,
    provider,
    settings,
    question_id,
) -> None:
    tokens = await register(api)
    item = await submit(api, tokens, question_id)
    provider.error = ProviderError(retry_after=120)
    worker = EvaluationWorker(sessions, provider, settings)
    started = datetime.now(UTC)
    assert await worker.once()
    assert not await worker.once()
    async with sessions() as session:
        row = await session.get(Submission, UUID(item["id"]))
        assert row.status == Verdict.RUNNING
        assert row.lease_until >= started + timedelta(seconds=120)


async def test_concurrent_worker_claims_and_solve_once(
    api, sessions, provider, settings, question_id
) -> None:
    tokens = await register(api)
    await submit(api, tokens, question_id)

    async def claim():
        async with sessions() as session:
            return await SubmissionRepository(session).claim(settings)

    claims = await asyncio.gather(claim(), claim())
    assert sum(row is not None for row in claims) == 1
    first = next(row for row in claims if row)
    await EvaluationWorker(sessions, provider, settings).process(first)
    await submit(api, tokens, question_id)
    await EvaluationWorker(sessions, provider, settings).once()
    board = (await api.get("/api/v1/leaderboard")).json()["data"]
    assert board[0]["solved_questions"] == 1
    progress = (await api.get("/api/v1/users/me/progress", headers=auth(tokens))).json()["data"]
    assert progress[0]["attempts"] == 2


async def test_pending_limit_is_atomic(
    api, settings, sessions, redis, provider, question_id
) -> None:
    settings.max_pending_submissions = 1
    tokens = await register(api)
    responses = await asyncio.gather(
        *[
            api.post(
                "/api/v1/submissions",
                headers=auth(tokens),
                json={
                    "question_id": str(question_id),
                    "language": "cpp",
                    "source_code": "int main(){}",
                },
            )
            for _ in range(3)
        ]
    )
    assert sorted(response.status_code for response in responses) == [202, 429, 429]


async def test_admission_validation_and_language_mismatch(api, question_id, sessions) -> None:
    tokens = await register(api)
    base = {"question_id": str(question_id), "language": "python", "source_code": "print(1)"}
    assert (
        await api.post(
            "/api/v1/submissions", headers=auth(tokens), json={**base, "language_id": 62}
        )
    ).status_code == 422
    assert (
        await api.post(
            "/api/v1/submissions", headers=auth(tokens), json={**base, "question_id": str(uuid4())}
        )
    ).status_code == 404
    async with sessions() as session:
        from sqlalchemy import delete

        await session.execute(delete(Case))
        await session.commit()
    assert (
        await api.post("/api/v1/submissions", headers=auth(tokens), json=base)
    ).status_code == 409


async def test_redis_wakeup_failure_keeps_durable_submission(
    api, sessions, provider, settings, question_id, redis, monkeypatch
) -> None:
    tokens = await register(api)
    from redis.exceptions import ConnectionError

    def broken_pipeline(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(redis, "pipeline", broken_pipeline)
    await submit(api, tokens, question_id)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Submission)) == 1
    assert await EvaluationWorker(sessions, provider, settings).once()


async def test_failed_commit_rolls_back_job_but_conservatively_keeps_quota(
    api,
    sessions,
    provider,
    settings,
    question_id,
    redis,
    monkeypatch,
) -> None:
    from sqlalchemy.exc import OperationalError

    from app.core.errors import AppError
    from app.core.security import decode_access
    from app.integrations.redis import Limits
    from app.schemas import SubmitRequest
    from app.services.submissions import SubmissionService

    tokens = await register(api)
    user_id = decode_access(tokens["access_token"], settings)
    payload = SubmitRequest(question_id=question_id, language="python", source_code="print(1)")
    settings.daily_submissions = 1
    limits = Limits(redis, settings)
    async with sessions() as session:

        async def fail_commit():
            raise OperationalError("commit", {}, Exception("offline"))

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(OperationalError):
            await SubmissionService(session, provider, limits, settings, redis).create(
                user_id, payload
            )
        await session.rollback()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Submission)) == 0
    with pytest.raises(AppError, match="Daily execution quota"):
        await limits.execution(str(user_id), 1)


async def test_replay_races_with_newer_generation(api) -> None:
    first = await register(api)
    second = (
        await api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()["data"]
    responses = await asyncio.gather(
        api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}),
        api.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}),
    )
    assert responses[0].status_code == 401
    for response in responses:
        if response.status_code == 200:
            newer = response.json()["data"]["refresh_token"]
            assert (
                await api.post("/api/v1/auth/refresh", json={"refresh_token": newer})
            ).status_code == 401
