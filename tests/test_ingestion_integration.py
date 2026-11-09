import asyncio

import pytest
from sqlalchemy import func, select

from app.ingestion.catalog import build_bundle, onboard
from app.ingestion.workbook import WorkbookData, WorkbookProblem
from app.models import Difficulty, Question, Submission
from app.models import TestCase as Case
from tests.test_ingestion import fixture_bundle, public_problem
from tests.test_integration import auth, register

pytestmark = pytest.mark.integration


async def test_catalog_onboarding_is_idempotent_and_creates_no_judge_cases(sessions) -> None:
    bundle = fixture_bundle()
    assert await onboard(sessions, bundle) == {
        "created": 2,
        "updated": 0,
        "unchanged": 0,
        "total": 2,
    }
    assert await onboard(sessions, bundle) == {
        "created": 0,
        "updated": 0,
        "unchanged": 2,
        "total": 2,
    }
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Question)) == 2
        assert await session.scalar(select(func.count()).select_from(Case)) == 0
        question = await session.get(Question, bundle.questions[0].id)
        assert question.published and question.statement == bundle.questions[0].statement


async def test_concurrent_catalog_import_does_not_duplicate(sessions) -> None:
    results = await asyncio.gather(
        onboard(sessions, fixture_bundle()), onboard(sessions, fixture_bundle())
    )
    assert sum(item["created"] for item in results) == 2
    assert sum(item["unchanged"] for item in results) == 2


async def test_manual_body_edits_abort_the_entire_import(sessions) -> None:
    initial = fixture_bundle((2,))
    await onboard(sessions, initial)
    async with sessions() as session:
        question = await session.get(Question, initial.questions[0].id)
        question.statement = "An administrator manually edited this problem."
        await session.commit()
    with pytest.raises(ValueError, match="manual edits"):
        await onboard(sessions, fixture_bundle((1, 2)))
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Question)) == 1
        assert await session.get(Question, fixture_bundle().questions[0].id) is None


async def test_import_preserves_private_test_cases(sessions) -> None:
    bundle = fixture_bundle((1,))
    await onboard(sessions, bundle)
    async with sessions() as session:
        session.add(
            Case(
                question_id=bundle.questions[0].id,
                position=0,
                stdin="private-input",
                expected_output="private-output",
                hidden=True,
            )
        )
        await session.commit()
    await onboard(sessions, bundle)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Case)) == 1


async def test_browsable_catalog_api_exposes_enrichment_and_readiness(api, sessions) -> None:
    bundle = fixture_bundle((1, 2, 3))
    await onboard(sessions, bundle)
    response = await api.get("/api/v1/questions?page_size=2")
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3 and len(page["data"]) == 2
    assert [item["source"]["frontend_id"] for item in page["data"]] == [1, 2]
    assert all(item["is_judgeable"] is False for item in page["data"])
    detail = await api.get(f"/api/v1/questions/{bundle.questions[0].id}")
    data = detail.json()["data"]
    assert data["statement"] == bundle.questions[0].statement
    assert data["examples"] == [{"input": "nums = [1,2]", "output": "3"}]
    assert data["samples"] == [] and data["is_judgeable"] is False
    assert "workbook_sha256" not in detail.text and "provided.xlsx" not in detail.text
    async with sessions() as session:
        session.add(
            Case(
                question_id=bundle.questions[0].id,
                position=0,
                stdin="private",
                expected_output="secret",
                hidden=True,
            )
        )
        await session.commit()
    data = (await api.get(f"/api/v1/questions/{bundle.questions[0].id}")).json()["data"]
    assert data["is_judgeable"] is False and data["samples"] == []
    assert data["judging_status"] == "not_configured"
    assert "secret" not in str(data)


async def test_catalog_without_judge_cases_rejects_submission_without_quota_use(
    api, sessions, redis, provider
) -> None:
    bundle = fixture_bundle((1,))
    await onboard(sessions, bundle)
    tokens = await register(api)
    response = await api.post(
        "/api/v1/submissions",
        headers=auth(tokens),
        json={
            "question_id": str(bundle.questions[0].id),
            "language": "python",
            "source_code": "print(1)",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "question_unavailable"
    assert await redis.keys("quota:*") == []
    assert provider.created == []
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Submission)) == 0


async def test_branded_titles_survive_reimport_and_preserve_source_search_and_private_cases(
    api, sessions
) -> None:
    workbook = WorkbookData(
        "provided.xlsx",
        "a" * 64,
        "Sheet",
        [WorkbookProblem(1, "Two Sum", Difficulty.EASY, "Neutral original statement.", 2)],
    )
    source = public_problem(1, title="Two Sum").model_copy(update={"titleSlug": "two-sum"})
    bundle = build_bundle(workbook, {1: source}, {})
    await onboard(sessions, bundle)
    async with sessions() as session:
        case = Case(
            question_id=bundle.questions[0].id,
            position=0,
            hidden=True,
            stdin="private-title-test-input",
            expected_output="private-title-test-output",
        )
        session.add(case)
        await session.commit()
        case_id = case.id
    # A freshly rebuilt source bundle uses the same curated display title.
    assert (await onboard(sessions, build_bundle(workbook, {1: source}, {})))["unchanged"] == 1
    for search in ["Two Sum", "Friends With Benefits"]:
        response = await api.get("/api/v1/questions", params={"search": search})
        assert response.status_code == 200 and response.json()["total"] == 1
        item = response.json()["data"][0]
        assert item["title"] == "Two Sum: Friends With Benefits"
        assert item["source"]["title"] == "Two Sum"
    detail = (await api.get(f"/api/v1/questions/{bundle.questions[0].id}")).json()["data"]
    assert detail["statement"] == "Neutral original statement."
    assert "private-title-test" not in str(detail)
    async with sessions() as session:
        assert await session.get(Case, case_id) is not None
