import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.errors import ProviderError
from app.ingestion.catalog import CatalogBundle, onboard
from app.integrations.judge0 import ExecutionResult
from app.judging.contracts import suite_hash
from app.judging.suites import build_suites, install_suites
from app.models import Question, Submission, SubmissionTestResult, UserProgress, Verdict
from app.models import TestCase as Case
from app.worker import EvaluationWorker
from tests.test_ingestion import fixture_bundle
from tests.test_integration import auth, register

pytestmark = pytest.mark.integration


@pytest.fixture
async def sample_question(sessions):
    public = CatalogBundle.model_validate_json(
        await asyncio.to_thread(Path("data/questions/leetcode_001_300.json").read_text)
    )
    bundle = fixture_bundle((1,))
    bundle.questions[0].interface = public.questions[0].interface
    bundle.questions[0].examples = public.questions[0].examples
    suite = build_suites(bundle)[1]
    await onboard(sessions, bundle)
    await install_suites(sessions, {1: suite})
    return suite


async def snapshot_account(api, tokens):
    return [
        (await api.get(path, headers=auth(tokens))).json()
        for path in [
            "/api/v1/users/me/progress",
            "/api/v1/users/me/statistics",
            "/api/v1/leaderboard",
        ]
    ]


@pytest.mark.parametrize("language", ["python", "java", "cpp"])
@pytest.mark.parametrize("existing_progress", [False, True])
async def test_sample_runs_snapshot_only_visible_cases_and_leave_progress_unchanged(
    api, sessions, provider, settings, redis, sample_question, language, existing_progress
):
    suite = sample_question
    visible = [c for c in suite["cases"] if not c["hidden"]]
    tokens = await register(api)
    user_id = UUID((await api.get("/api/v1/users/me", headers=auth(tokens))).json()["data"]["id"])
    if existing_progress:
        async with sessions() as session:
            session.add(
                UserProgress(
                    user_id=user_id,
                    question_id=suite["id"],
                    attempts=3,
                    solved_at=datetime.now(UTC),
                )
            )
            await session.commit()
    before = await snapshot_account(api, tokens)
    response = await api.post(
        f"/api/v1/questions/{suite['id']}/runs",
        headers=auth(tokens),
        json={"language": language, "source_code": suite["starter_code"][language]},
    )
    assert response.status_code == 202
    summary = response.json()["data"]
    assert summary["mode"] == "run" and summary["question_id"] == str(suite["id"])
    assert summary["total_tests"] == len(visible) < len(suite["cases"])
    submission_id = UUID(summary["id"])
    async with sessions() as session:
        record = await session.get(Submission, submission_id)
        assert record.evaluation == suite["profile"].model_dump(mode="json")
        rows = list(
            await session.scalars(
                select(SubmissionTestResult)
                .where(SubmissionTestResult.submission_id == submission_id)
                .order_by(SubmissionTestResult.position)
            )
        )
        assert [r.stdin for r in rows] == [c["stdin"] for c in visible]
        assert all(not r.hidden for r in rows)
        # Later catalog changes must not alter an already-admitted sample run.
        question = await session.get(Question, suite["id"])
        question.content = {**question.content, "judging": {"invalid": "later edit"}}
        case = await session.get(Case, rows[0].test_case_id)
        case.expected_output = "unverified later edit"
        await session.commit()
    assert await snapshot_account(api, tokens) == before
    provider.results = [
        ExecutionResult(status=Verdict.ACCEPTED, stdout=c["expected_output"]) for c in visible
    ]
    assert await EvaluationWorker(sessions, provider, settings).once()
    detail = (await api.get(f"/api/v1/submissions/{submission_id}", headers=auth(tokens))).json()[
        "data"
    ]
    assert detail["status"] == "accepted" and detail["passed_tests"] == len(visible)
    assert [r["stdin"] for r in detail["results"]] == [c["stdin"] for c in visible]
    assert [r["expected_output"] for r in detail["results"]] == [
        c["expected_output"] for c in visible
    ]
    assert all(c["expected"] is None for c in provider.created)
    assert await snapshot_account(api, tokens) == before
    keys = await redis.keys("quota:*:executions")
    assert len(keys) == 1 and int(await redis.get(keys[0])) == len(visible)
    history = (
        await api.get(
            "/api/v1/submissions", headers=auth(tokens), params={"question_id": str(suite["id"])}
        )
    ).json()
    assert history["total"] == 1 and history["data"][0]["mode"] == "run"
    other = await register(api, "other")
    assert (
        await api.get(f"/api/v1/submissions/{submission_id}", headers=auth(other))
    ).status_code == 404


@pytest.mark.parametrize(
    "status,stdout,expected",
    [
        (Verdict.ACCEPTED, "[0,0]", "wrong_answer"),
        (Verdict.ACCEPTED, "not json", "wrong_answer"),
        (Verdict.COMPILATION_ERROR, None, "compilation_error"),
        (Verdict.RUNTIME_ERROR, None, "runtime_error"),
        (Verdict.TIME_LIMIT_EXCEEDED, None, "time_limit_exceeded"),
        (Verdict.MEMORY_LIMIT_EXCEEDED, None, "memory_limit_exceeded"),
        (Verdict.PROVIDER_ERROR, None, "provider_error"),
    ],
)
async def test_sample_run_failures_return_real_verdicts_without_credit(
    api, sessions, provider, settings, sample_question, status, stdout, expected
):
    tokens = await register(api)
    before = await snapshot_account(api, tokens)
    response = await api.post(
        f"/api/v1/questions/{sample_question['id']}/runs",
        headers=auth(tokens),
        json={"language": "python", "source_code": "class Solution: pass"},
    )
    assert response.status_code == 202
    summary = response.json()["data"]
    provider.results = [
        ExecutionResult(status=status, stdout=stdout) for _ in range(summary["total_tests"])
    ]
    assert await EvaluationWorker(sessions, provider, settings).once()
    detail = (await api.get("/api/v1/submissions/" + summary["id"], headers=auth(tokens))).json()[
        "data"
    ]
    assert detail["status"] == expected and detail["passed_tests"] == 0
    assert await snapshot_account(api, tokens) == before


async def test_passing_samples_does_not_imply_passing_submission(
    api, sessions, provider, settings, sample_question
):
    suite = sample_question
    tokens = await register(api)
    payload = {"language": "python", "source_code": "class Solution: pass"}
    response = await api.post(
        f"/api/v1/questions/{suite['id']}/runs", headers=auth(tokens), json=payload
    )
    provider.results = [
        ExecutionResult(status=Verdict.ACCEPTED, stdout=c["expected_output"])
        for c in suite["cases"]
        if not c["hidden"]
    ]
    worker = EvaluationWorker(sessions, provider, settings)
    await worker.once()
    assert (
        await api.get("/api/v1/submissions/" + response.json()["data"]["id"], headers=auth(tokens))
    ).json()["data"]["status"] == "accepted"
    submitted = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={**payload, "question_id": str(suite["id"])},
    )
    provider.results = [
        ExecutionResult(
            status=Verdict.ACCEPTED, stdout="[0,0]" if c["hidden"] else c["expected_output"]
        )
        for c in suite["cases"]
    ]
    await worker.once()
    detail = (
        await api.get("/api/v1/submissions/" + submitted.json()["data"]["id"], headers=auth(tokens))
    ).json()["data"]
    assert detail["status"] == "wrong_answer"
    assert detail["passed_tests"] == response.json()["data"]["total_tests"]
    assert all(
        r["stdin"] is None and r["expected_output"] is None and r["stdout"] is None
        for r in detail["results"]
        if r["hidden"]
    )
    progress = (await api.get("/api/v1/users/me/progress", headers=auth(tokens))).json()["data"]
    assert len(progress) == 1 and progress[0]["attempts"] == 1 and progress[0]["solved_at"] is None


@pytest.mark.parametrize("state", ["no_samples", "unsupported", "tampered_hidden", "unpublished"])
async def test_unavailable_samples_fail_before_registry_quota_or_job_creation(
    api, sessions, provider, redis, sample_question, state
):
    suite = sample_question
    async with sessions() as session:
        question = await session.get(Question, suite["id"])
        if state == "no_samples":
            cases = list(await session.scalars(select(Case).order_by(Case.position)))
            for c in cases:
                c.hidden = True
            saved = [
                {"stdin": c.stdin, "expected_output": c.expected_output, "hidden": True}
                for c in cases
            ]
            profile = {**question.content["judging"], "suite_sha256": suite_hash(saved)}
            question.content = {**question.content, "judging": profile}
        elif state == "unsupported":
            question.content = {**question.content, "supported_languages": []}
        elif state == "tampered_hidden":
            case = await session.scalar(select(Case).where(Case.hidden.is_(True)).limit(1))
            case.expected_output = "unverified hidden edit"
        else:
            question.published = False
        await session.commit()
    provider.languages = AsyncMock(side_effect=AssertionError("Discovery must not happen"))
    tokens = await register(api)
    response = await api.post(
        f"/api/v1/questions/{suite['id']}/runs",
        headers=auth(tokens),
        json={"language": "python", "source_code": "class Solution: pass"},
    )
    assert response.status_code == (404 if state == "unpublished" else 409)
    if state == "no_samples":
        assert response.json()["error"]["code"] == "samples_unavailable"
    provider.languages.assert_not_called()
    assert await redis.keys("quota:*") == []
    async with sessions() as session:
        assert await session.scalar(select(Submission.id)) is None


async def test_sample_run_auth_shape_missing_question_and_quota(
    api, sessions, provider, settings, sample_question
):
    path = f"/api/v1/questions/{sample_question['id']}/runs"
    payload = {"language": "python", "source_code": "class Solution: pass"}
    assert (await api.post(path, json=payload)).status_code == 401
    tokens = await register(api)
    for injected in [
        {"stdin": "private input"},
        {"include_hidden": True},
        {"expected_output": "x"},
    ]:
        assert (
            await api.post(path, headers=auth(tokens), json={**payload, **injected})
        ).status_code == 422
    assert (
        await api.post(f"/api/v1/questions/{uuid4()}/runs", headers=auth(tokens), json=payload)
    ).status_code == 404
    settings.daily_test_executions = 1
    assert (await api.post(path, headers=auth(tokens), json=payload)).status_code == 429
    assert provider.created == []


async def test_sample_run_reports_registry_outage_without_creating_job(
    api, sessions, provider, sample_question
):
    provider.languages = AsyncMock(side_effect=ProviderError())
    tokens = await register(api)
    response = await api.post(
        f"/api/v1/questions/{sample_question['id']}/runs",
        headers=auth(tokens),
        json={"language": "python", "source_code": "class Solution: pass"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    async with sessions() as session:
        assert await session.scalar(select(Submission.id)) is None
