from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.ingestion.catalog import CatalogBundle, onboard
from app.integrations.judge0 import ExecutionResult
from app.judging.suites import build_suites, install_suites
from app.models import Question, Submission, Verdict
from app.models import TestCase as Case
from app.worker import EvaluationWorker
from tests.test_ingestion import fixture_bundle
from tests.test_integration import auth, register

pytestmark = pytest.mark.integration


@pytest.fixture
def bundle_and_suite():
    public = CatalogBundle.model_validate_json(
        Path("data/questions/leetcode_001_300.json").read_text()
    )
    neutral = fixture_bundle((1,))
    neutral.questions[0].interface = public.questions[0].interface
    neutral.questions[0].examples = public.questions[0].examples
    return neutral, build_suites(neutral)


async def test_install_is_idempotent_and_catalog_reimport_preserves_judging(
    sessions, bundle_and_suite
):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    first = await install_suites(sessions, suites)
    second = await install_suites(sessions, suites)
    assert first["created"] == 1 and second["unchanged"] == 1
    assert (await onboard(sessions, bundle))["unchanged"] == 1
    async with sessions() as session:
        question = await session.get(Question, bundle.questions[0].id)
        assert question.content["judging"]["version"] == 1
        assert await session.scalar(select(func.count()).select_from(Case)) == len(
            suites[1]["cases"]
        )


async def test_correct_answer_is_compared_in_backend_and_awards_progress(
    api, sessions, provider, settings, bundle_and_suite
):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    question = bundle.questions[0]
    public = (await api.get(f"/api/v1/questions/{question.id}")).json()["data"]
    assert public["is_judgeable"] and public["judgeable_languages"] == ["python", "java", "cpp"]
    assert "judging" not in public and "evaluation" not in public
    tokens = await register(api)
    response = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={
            "question_id": str(question.id),
            "language": "python",
            "source_code": "class Solution:\n    def twoSum(self, nums, target): return [0,1]\n",
        },
    )
    assert response.status_code == 202
    submission_id = UUID(response.json()["data"]["id"])
    # Editing catalog policy after admission must not change this queued contract.
    async with sessions() as session:
        record = await session.get(Submission, submission_id)
        assert record.evaluation == suites[1]["profile"].model_dump(mode="json")
        q = await session.get(Question, question.id)
        q.content = {**q.content, "judging": {"invalid": "later edit"}}
        await session.commit()
    provider.results = [
        ExecutionResult(status=Verdict.ACCEPTED, stdout=c["expected_output"])
        for c in suites[1]["cases"]
    ]
    assert await EvaluationWorker(sessions, provider, settings).once()
    assert all(c["expected"] is None for c in provider.created)
    assert all("Solution().twoSum(" in c["source"] for c in provider.created)
    detail = (await api.get(f"/api/v1/submissions/{submission_id}", headers=auth(tokens))).json()[
        "data"
    ]
    assert detail["status"] == "accepted" and detail["passed_tests"] == len(suites[1]["cases"])
    assert all(
        c["stdout"] is None and c["compile_output"] is None
        for c in detail["results"]
        if c["hidden"]
    )
    assert "evaluation" not in detail and "provider_token" not in str(detail)
    stats = (await api.get("/api/v1/users/me/statistics", headers=auth(tokens))).json()["data"]
    assert stats["solved_questions"] == 1


@pytest.mark.parametrize(
    "provider_status,stdout,expected",
    [
        (Verdict.ACCEPTED, "[0,0]", "wrong_answer"),
        (Verdict.ACCEPTED, "not json", "wrong_answer"),
        (Verdict.COMPILATION_ERROR, None, "compilation_error"),
        (Verdict.RUNTIME_ERROR, None, "runtime_error"),
        (Verdict.TIME_LIMIT_EXCEEDED, None, "time_limit_exceeded"),
    ],
)
async def test_incorrect_and_failed_programs_never_award_progress(
    api, sessions, provider, settings, bundle_and_suite, provider_status, stdout, expected
):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    tokens = await register(api)
    response = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={
            "question_id": str(bundle.questions[0].id),
            "language": "python",
            "source_code": "class Solution: pass",
        },
    )
    assert response.status_code == 202
    provider.results = [
        ExecutionResult(status=provider_status, stdout=stdout) for _ in suites[1]["cases"]
    ]
    await EvaluationWorker(sessions, provider, settings).once()
    detail = (
        await api.get("/api/v1/submissions/" + response.json()["data"]["id"], headers=auth(tokens))
    ).json()["data"]
    assert detail["status"] == expected and detail["passed_tests"] == 0
    assert (await api.get("/api/v1/users/me/statistics", headers=auth(tokens))).json()["data"][
        "solved_questions"
    ] == 0


async def test_incomplete_suite_is_rejected_before_registry_or_quota(
    api, sessions, provider, redis, bundle_and_suite
):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    async with sessions() as session:
        case = await session.scalar(select(Case).limit(1))
        await session.delete(case)
        await session.commit()
    tokens = await register(api)
    detail = (await api.get(f"/api/v1/questions/{bundle.questions[0].id}")).json()["data"]
    assert detail["is_judgeable"] is False and detail["judging_status"] == "invalid_suite"
    response = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={
            "question_id": str(bundle.questions[0].id),
            "language": "python",
            "source_code": "class Solution: pass",
        },
    )
    assert response.status_code == 409 and await redis.keys("quota:*") == []
    assert provider.created == []


@pytest.mark.parametrize("edit", ["case", "statement"])
async def test_unverified_edits_reject_judging_before_quota(
    api, sessions, redis, bundle_and_suite, edit
):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    async with sessions() as session:
        if edit == "case":
            case = await session.scalar(select(Case).order_by(Case.position).limit(1))
            case.expected_output = "[0,0]"
        else:
            question = await session.get(Question, bundle.questions[0].id)
            question.statement += " Changed after verification."
        await session.commit()
    detail = (await api.get(f"/api/v1/questions/{bundle.questions[0].id}")).json()["data"]
    assert detail["is_judgeable"] is False and detail["judging_status"] == "invalid_suite"
    tokens = await register(api)
    response = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={
            "question_id": str(bundle.questions[0].id),
            "language": "python",
            "source_code": "class Solution: pass",
        },
    )
    assert response.status_code == 409 and await redis.keys("quota:*") == []


async def test_contract_metadata_upgrade_preserves_existing_case_ids(sessions, bundle_and_suite):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    async with sessions() as session:
        original = list(await session.scalars(select(Case.id).order_by(Case.position)))
    suites[1]["profile"] = suites[1]["profile"].model_copy(
        update={"suite_version": "reviewed-metadata-update"}
    )
    result = await install_suites(sessions, suites)
    assert result["updated"] == 1
    async with sessions() as session:
        assert list(await session.scalars(select(Case.id).order_by(Case.position))) == original


async def test_public_constraint_refresh_requires_review_of_existing_judging(
    sessions, bundle_and_suite
):
    bundle, suites = bundle_and_suite
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    bundle.questions[0].constraints = ["A newly revised public constraint."]
    with pytest.raises(ValueError, match="needs review"):
        await onboard(sessions, bundle)
