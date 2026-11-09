import asyncio
import io
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy import select

from app.core.errors import ProviderError
from app.ingestion.catalog import CatalogBundle, onboard
from app.integrations.judge0 import ExecutionResult
from app.judging.suites import build_suites, install_suites
from app.models import (
    Difficulty,
    Language,
    Question,
    QuestionCollection,
    Submission,
    SubmissionMode,
    SubmissionTestResult,
    UserProgress,
    Verdict,
)
from app.services.profiles import current_streak
from app.worker import EvaluationWorker
from tests.test_ingestion import fixture_bundle
from tests.test_integration import auth, register
from tests.test_sample_runs import sample_question as sample_question

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog(sessions):
    async with sessions() as session:
        rows = []
        for i, (level, tags, published) in enumerate(
            [
                (Difficulty.EASY, ["array", "array", "hash-table"], True),
                (Difficulty.EASY, ["array"], True),
                (Difficulty.MEDIUM, ["array", "tree"], True),
                (Difficulty.HARD, ["tree"], True),
                (Difficulty.HARD, ["secret-topic"], False),
            ]
        ):
            q = Question(
                slug=f"q-{i}",
                title=f"Problem {i}",
                statement="Neutral fixture",
                difficulty=level,
                tags=tags,
                published=published,
                content={},
            )
            q.created_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=i)
            session.add(q)
            rows.append(q)
        collections = []
        for i, level in enumerate(Difficulty):
            c = QuestionCollection(
                slug=f"collection-{i}",
                name=f"Collection {i}",
                description="Fixture",
                position=i,
                difficulty=level,
            )
            session.add(c)
            collections.append(c)
        await session.commit()
        return rows, collections


async def test_topics_filters_pagination_random_and_navigation(api, catalog):
    questions, _ = catalog
    topics = (await api.get("/api/v1/topics")).json()["data"]
    assert {r["slug"]: r["question_count"] for r in topics} == {
        "array": 3,
        "hash-table": 1,
        "tree": 2,
    }
    assert next(r for r in topics if r["slug"] == "hash-table")["name"] == "Hash Table"
    for page, index in [(1, 0), (2, 1)]:
        response = await api.get(
            "/api/v1/questions",
            params={
                "topic": "array",
                "difficulty": "easy",
                "search": "Problem",
                "page_size": 1,
                "page": page,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2 and body["data"][0]["id"] == str(questions[index].id)
    assert (await api.get("/api/v1/questions", params={"topic": "unknown"})).json()["total"] == 0
    for _ in range(3):
        picked = (
            await api.get(
                "/api/v1/questions/random", params={"topic": "tree", "difficulty": "medium"}
            )
        ).json()["data"]
        assert picked["id"] == str(questions[2].id)
    assert (
        await api.get("/api/v1/questions/random", params={"topic": "unknown"})
    ).status_code == 404
    for i in range(2):
        nav = (
            await api.get(
                f"/api/v1/questions/{questions[i].id}/navigation",
                params={"difficulty": "easy", "topic": "array"},
            )
        ).json()["data"]
        assert nav["total"] == 2 and nav["position"] == i + 1
        assert nav["previous_id"] == (str(questions[0].id) if i else None)
        assert nav["next_id"] == (None if i else str(questions[1].id))
    assert (
        await api.get(
            f"/api/v1/questions/{questions[2].id}/navigation", params={"difficulty": "easy"}
        )
    ).status_code == 404
    assert (await api.get(f"/api/v1/questions/{questions[4].id}/navigation")).status_code == 404
    featured = (await api.get("/api/v1/questions/featured", params={"limit": 2})).json()["data"]
    assert featured["selection_rule"] == "first_in_catalog"
    assert [q["id"] for q in featured["questions"]] == [str(q.id) for q in questions[:2]]


async def test_collections_counts_private_completion_and_filtering(api, sessions, catalog):
    questions, collections = catalog
    guest = (await api.get("/api/v1/collections")).json()
    assert [c["question_count"] for c in guest["data"]] == [2, 1, 1]
    assert all(
        c["solved_count"] is None and c["completion_percentage"] is None for c in guest["data"]
    )
    tokens = await register(api)
    uid = UUID((await api.get("/api/v1/users/me", headers=auth(tokens))).json()["data"]["id"])
    async with sessions() as s:
        s.add_all(
            [
                UserProgress(
                    user_id=uid,
                    question_id=questions[i].id,
                    attempts=1,
                    solved_at=datetime.now(UTC),
                )
                for i in [0, 4]
            ]
        )
        await s.commit()
    own = (await api.get("/api/v1/collections", headers=auth(tokens))).json()["data"]
    assert own[0]["solved_count"] == 1 and own[0]["completion_percentage"] == 50
    assert own[2]["solved_count"] == 0
    detail = (
        await api.get(
            f"/api/v1/collections/{collections[0].id}",
            headers=auth(tokens),
            params={"topic": "hash-table"},
        )
    ).json()["data"]
    assert detail["collection"]["question_count"] == 2 and detail["questions"]["total"] == 1
    other = await register(api, "other")
    assert (await api.get("/api/v1/collections", headers=auth(other))).json()["data"][0][
        "solved_count"
    ] == 0
    assert (
        await api.get("/api/v1/collections", headers={"Authorization": "Bearer invalid"})
    ).status_code == 401
    assert (await api.get(f"/api/v1/collections/{uuid4()}")).status_code == 404


@pytest.mark.parametrize("workspace_kind", ["question", "playground"])
async def test_draft_revision_conflicts_deletion_recreation_and_ownership(
    api, catalog, workspace_kind
):
    questions, _ = catalog
    workspace = str(questions[0].id) if workspace_kind == "question" else "playground"
    path = f"/api/v1/users/me/drafts/{workspace}/python"
    assert (await api.get(path)).status_code == 401
    tokens = await register(api)
    headers = auth(tokens)
    empty = (await api.get(path, headers=headers)).json()["data"]
    assert empty["exists"] is False and empty["revision"] == 0
    body = {"source_code": "print(1)", "revision": 0}
    if workspace_kind == "playground":
        body["stdin"] = "hello"
    first = await api.put(path, headers=headers, json=body)
    assert first.status_code == 200 and first.json()["data"]["revision"] == 1
    concurrent = await asyncio.gather(
        *[
            api.put(
                path, headers=headers, json={**body, "source_code": f"print({i})", "revision": 1}
            )
            for i in [2, 3]
        ]
    )
    assert sorted(r.status_code for r in concurrent) == [200, 409]
    conflict = next(r for r in concurrent if r.status_code == 409).json()["error"]
    assert conflict["code"] == "draft_conflict" and conflict["current_revision"] == 2
    assert "print(" not in str(conflict)
    other = await register(api, "other")
    assert (await api.get(path, headers=auth(other))).json()["data"]["exists"] is False
    removed = await api.delete(path, headers=headers, params={"revision": 2})
    assert removed.status_code == 200
    assert removed.json()["data"]["revision"] == 3 and removed.json()["data"]["source_code"] is None
    # A stale first save cannot resurrect a reset draft.
    assert (await api.put(path, headers=headers, json=body)).status_code == 409
    restored = await api.put(path, headers=headers, json={"revision": 3, "source_code": ""})
    assert restored.json()["data"]["revision"] == 4 and restored.json()["data"]["exists"]
    java = await api.get(path.replace("/python", "/java"), headers=headers)
    assert java.json()["data"]["revision"] == 0


async def test_draft_validation_and_empty_reset_tombstone(api, catalog):
    tokens = await register(api)
    headers = auth(tokens)
    question = catalog[0][0]
    path = f"/api/v1/users/me/drafts/{question.id}/python"
    assert (
        await api.put(path, headers=headers, json={"source_code": "x", "revision": 0, "stdin": ""})
    ).status_code == 422
    for payload in [
        {"source_code": "\0", "revision": 0},
        {"source_code": "😎" * 20000, "revision": 0},
        {"source_code": "x", "revision": True},
        {"source_code": "x", "revision": 0, "user_id": str(uuid4())},
    ]:
        assert (await api.put(path, headers=headers, json=payload)).status_code in [413, 422]
    assert (
        await api.get("/api/v1/users/me/drafts/not-a-workspace/python", headers=headers)
    ).status_code == 422
    assert (
        await api.get(f"/api/v1/users/me/drafts/{uuid4()}/python", headers=headers)
    ).status_code == 404
    assert (await api.delete(path, headers=headers, params={"revision": 0})).json()["data"][
        "revision"
    ] == 1
    assert (
        await api.put(path, headers=headers, json={"source_code": "old", "revision": 0})
    ).status_code == 409


async def test_preferences_defaults_partial_updates_concurrency_and_runtime_validation(
    api, provider
):
    assert (await api.get("/api/v1/users/me/preferences")).status_code == 401
    tokens = await register(api)
    headers = auth(tokens)
    assert (await api.get("/api/v1/users/me/preferences", headers=headers)).json()["data"] == {
        "font_size": 14,
        "editor_mode": "standard",
        "preferred_language": "python",
        "preferred_runtime_id": None,
        "pane_split": 50.0,
    }
    results = await asyncio.gather(
        api.patch("/api/v1/users/me/preferences", headers=headers, json={"font_size": 20}),
        api.patch("/api/v1/users/me/preferences", headers=headers, json={"pane_split": 65}),
    )
    assert all(r.status_code == 200 for r in results)
    prefs = (await api.get("/api/v1/users/me/preferences", headers=headers)).json()["data"]
    assert prefs["font_size"] == 20 and prefs["pane_split"] == 65
    assert (
        await api.patch(
            "/api/v1/users/me/preferences", headers=headers, json={"preferred_runtime_id": 62}
        )
    ).status_code == 422
    assert (
        await api.patch(
            "/api/v1/users/me/preferences",
            headers=headers,
            json={"preferred_language": "java", "preferred_runtime_id": 62},
        )
    ).status_code == 200
    switched = (
        await api.patch(
            "/api/v1/users/me/preferences", headers=headers, json={"preferred_language": "cpp"}
        )
    ).json()["data"]
    assert switched["preferred_runtime_id"] is None
    for payload in [
        {"font_size": 9},
        {"pane_split": 81},
        {"editor_mode": "unknown"},
        {"font_size": None},
        {"theme": "anything"},
    ]:
        assert (
            await api.patch("/api/v1/users/me/preferences", headers=headers, json=payload)
        ).status_code == 422
    provider.languages = AsyncMock(side_effect=ProviderError())
    assert (
        await api.patch("/api/v1/users/me/preferences", headers=headers, json={"font_size": 18})
    ).status_code == 200
    assert (
        await api.patch(
            "/api/v1/users/me/preferences", headers=headers, json={"preferred_runtime_id": 54}
        )
    ).status_code == 503
    other = await register(api, "other")
    assert (await api.get("/api/v1/users/me/preferences", headers=auth(other))).json()["data"][
        "font_size"
    ] == 14


@pytest.mark.parametrize("language", ["python", "java", "cpp"])
async def test_custom_function_run_output_without_reference_answers_or_credit(
    api, sessions, provider, settings, sample_question, language
):
    tokens = await register(api)
    headers = auth(tokens)
    baseline = (await api.get("/api/v1/users/me/statistics", headers=headers)).json()
    inputs = ["[[2,8],10]", "[[3,4],7]"]
    response = await api.post(
        f"/api/v1/questions/{sample_question['id']}/runs",
        headers=headers,
        json={
            "language": language,
            "source_code": sample_question["starter_code"][language],
            "test_cases": [{"stdin": x} for x in inputs],
        },
    )
    assert response.status_code == 202
    summary = response.json()["data"]
    assert summary["evaluation_scope"] == "custom"
    assert summary["total_tests"] == 2 and summary["mode"] == "run"
    provider.results = [ExecutionResult(status=Verdict.ACCEPTED, stdout="[0,0]") for _ in inputs]
    assert await EvaluationWorker(sessions, provider, settings).once()
    detail = (await api.get("/api/v1/submissions/" + summary["id"], headers=headers)).json()["data"]
    # No hidden oracle is called: successful execution can return a logically wrong answer.
    assert detail["status"] == "accepted"
    assert [r["stdin"] for r in detail["results"]] == inputs
    assert all(r["expected_output"] is None and not r["hidden"] for r in detail["results"])
    assert all(c["expected"] is None for c in provider.created)
    assert (await api.get("/api/v1/users/me/statistics", headers=headers)).json() == baseline
    assert (await api.get("/api/v1/users/me/progress", headers=headers)).json()["total"] == 0
    async with sessions() as s:
        cases = list(await s.scalars(select(SubmissionTestResult)))
        assert all(c.test_case_id is None for c in cases)


@pytest.mark.parametrize(
    "stdin", ["not json", "[[1,2]]", "[[true,2],3]", '{"nums":[1,2]}', "[[],NaN]"]
)
async def test_invalid_custom_inputs_rejected_before_registry_and_quota(
    api, provider, redis, sample_question, stdin
):
    tokens = await register(api)
    provider.languages = AsyncMock(side_effect=AssertionError("Must not discover"))
    response = await api.post(
        f"/api/v1/questions/{sample_question['id']}/runs",
        headers=auth(tokens),
        json={
            "language": "python",
            "source_code": "class Solution: pass",
            "test_cases": [{"stdin": stdin}],
        },
    )
    assert (
        response.status_code == 422 and response.json()["error"]["code"] == "invalid_custom_input"
    )
    assert await redis.keys("quota:*") == []
    provider.languages.assert_not_called()


def png_bytes(size=(32, 32), format="PNG"):
    output = io.BytesIO()
    image = Image.new("RGB", size, (255, 100, 20))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "strip-me")
    image.save(output, format=format, **({"pnginfo": metadata} if format == "PNG" else {}))
    return output.getvalue()


async def test_avatar_upload_reencoding_public_profiles_replacement_and_removal(
    api, settings, tmp_path, sessions, catalog
):
    settings.avatar_storage_dir = tmp_path / "avatars"
    tokens = await register(api)
    headers = auth(tokens)
    image = png_bytes((800, 600))
    assert (
        await api.put(
            "/api/v1/users/me/avatar", content=image, headers={"Content-Type": "image/png"}
        )
    ).status_code == 401
    response = await api.put(
        "/api/v1/users/me/avatar", content=image, headers={**headers, "Content-Type": "image/png"}
    )
    assert response.status_code == 200
    own = response.json()["data"]
    url = own["avatar_url"]
    public = (await api.get("/api/v1/users/coder")).json()["data"]
    assert public["avatar_url"] == url and "email" not in public
    asset = await api.get(url)
    assert asset.status_code == 200 and asset.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(asset.content)) as normalized:
        assert max(normalized.size) <= 256 and "private" not in normalized.info
    other = await register(api, "other")
    assert (await api.delete("/api/v1/users/me/avatar", headers=auth(other))).json()["data"][
        "avatar_url"
    ] is None
    assert (await api.get(url)).status_code == 200
    async with sessions() as s:
        s.add(
            UserProgress(
                user_id=UUID(own["id"]),
                question_id=catalog[0][0].id,
                attempts=1,
                solved_at=datetime.now(UTC),
            )
        )
        await s.commit()
    assert (await api.get("/api/v1/leaderboard")).json()["data"][0]["avatar_url"] == url
    second = await api.put(
        "/api/v1/users/me/avatar",
        headers={**headers, "Content-Type": "image/jpeg"},
        content=png_bytes(format="JPEG"),
    )
    assert second.status_code == 200 and second.json()["data"]["avatar_url"] != url
    assert (await api.get(url)).status_code == 404
    assert len(list(settings.avatar_storage_dir.iterdir())) == 1
    newer = second.json()["data"]["avatar_url"]
    assert (await api.delete("/api/v1/users/me/avatar", headers=headers)).json()["data"][
        "avatar_url"
    ] is None
    assert (await api.get(newer)).status_code == 404 and list(
        settings.avatar_storage_dir.iterdir()
    ) == []


@pytest.mark.parametrize(
    "kind,content,status",
    [
        ("image/svg+xml", b"<svg/>", 415),
        ("image/png", b"not an image", 422),
        ("image/jpeg", png_bytes(), 422),
        ("image/png", png_bytes((2100, 2100)), 422),
    ],
)
async def test_avatar_invalid_content(api, settings, tmp_path, kind, content, status):
    settings.avatar_storage_dir = tmp_path / "avatars"
    tokens = await register(api)
    response = await api.put(
        "/api/v1/users/me/avatar", headers={**auth(tokens), "Content-Type": kind}, content=content
    )
    assert response.status_code == status
    assert not settings.avatar_storage_dir.exists()


async def test_avatar_chunked_upload_limit(api, settings):
    tokens = await register(api)

    async def body():
        yield b"x" * settings.avatar_max_bytes
        yield b"x"

    response = await api.put(
        "/api/v1/users/me/avatar",
        headers={**auth(tokens), "Content-Type": "image/png"},
        content=body(),
    )
    assert response.status_code == 413


async def test_statistics_streak_rate_timezone_and_run_isolation(api, sessions, catalog):
    tokens = await register(api)
    headers = auth(tokens)
    uid = UUID((await api.get("/api/v1/users/me", headers=headers)).json()["data"]["id"])
    now = datetime.now(UTC)
    async with sessions() as s:
        for days, status, mode in [
            (0, Verdict.ACCEPTED, SubmissionMode.SUBMIT),
            (1, Verdict.WRONG_ANSWER, SubmissionMode.SUBMIT),
            (2, Verdict.PROVIDER_ERROR, SubmissionMode.SUBMIT),
            (0, Verdict.QUEUED, SubmissionMode.SUBMIT),
            (3, Verdict.ACCEPTED, SubmissionMode.RUN),
        ]:
            s.add(
                Submission(
                    user_id=uid,
                    question_id=catalog[0][0].id,
                    language=Language.PYTHON,
                    language_id=71,
                    language_version="Fixture",
                    source_code="Fixture",
                    evaluation={},
                    mode=mode,
                    status=status,
                    cpu_seconds=2,
                    memory_kb=131072,
                    total_tests=1,
                    passed_tests=1 if status == Verdict.ACCEPTED else 0,
                    created_at=now - timedelta(days=days),
                )
            )
        await s.commit()
    stats = (await api.get("/api/v1/users/me/statistics", headers=headers)).json()["data"]
    assert stats["submissions"] == 4 and stats["accepted_submissions"] == 1
    assert stats["evaluated_submissions"] == 2 and stats["acceptance_rate"] == 50
    assert stats["current_streak"] == 3 and stats["timezone"] == "UTC"
    assert sum(stats["daily_activity"].values()) == 4


def test_streak_grace_and_gaps():
    today = date(2026, 11, 9)
    assert current_streak(set(), today) == 0
    assert current_streak({today - timedelta(days=1), today - timedelta(days=2)}, today) == 2
    assert current_streak({today - timedelta(days=2)}, today) == 0
    assert current_streak({today, today - timedelta(days=2)}, today) == 1


async def test_custom_design_runs_validate_operation_sequences(api, sessions, provider, settings):
    public = CatalogBundle.model_validate_json(
        await asyncio.to_thread(Path("data/questions/leetcode_001_300.json").read_text)
    )
    bundle = fixture_bundle((155,))
    bundle.questions[0].interface = public.questions[154].interface
    bundle.questions[0].examples = public.questions[154].examples
    suites = build_suites(bundle)
    await onboard(sessions, bundle)
    await install_suites(sessions, suites)
    tokens = await register(api)
    headers = auth(tokens)
    path = f"/api/v1/questions/{bundle.questions[0].id}/runs"
    payload = {"language": "python", "source_code": suites[155]["starter_code"]["python"]}
    for stdin in [
        '[["WrongClass"],[[]]]',
        '[["MinStack","unknown"],[[],[]]]',
        '[["MinStack","push"],[[],[]]]',
    ]:
        assert (
            await api.post(
                path, headers=headers, json={**payload, "test_cases": [{"stdin": stdin}]}
            )
        ).status_code == 422
    response = await api.post(
        path,
        headers=headers,
        json={**payload, "test_cases": [{"stdin": '[["MinStack","push","getMin"],[[],[5],[]]]'}]},
    )
    assert response.status_code == 202
    provider.results = [ExecutionResult(status=Verdict.ACCEPTED, stdout="[null,null,5]")]
    assert await EvaluationWorker(sessions, provider, settings).once()
    result = (
        await api.get("/api/v1/submissions/" + response.json()["data"]["id"], headers=headers)
    ).json()["data"]
    assert result["status"] == "accepted" and result["evaluation_scope"] == "custom"
    assert result["results"][0]["expected_output"] is None


async def test_custom_cases_are_bounded_and_do_not_accept_expected_or_hidden_flags(
    api, sample_question
):
    headers = auth(await register(api))
    path = f"/api/v1/questions/{sample_question['id']}/runs"
    payload = {"language": "python", "source_code": "class Solution: pass"}
    for cases in [
        [],
        [{"stdin": "[[1,2],3]"}] * 11,
        [{"stdin": "[[1,2],3]", "expected_output": "[0,1]"}],
        [{"stdin": "[[1,2],3]", "hidden": True}],
    ]:
        assert (
            await api.post(path, headers=headers, json={**payload, "test_cases": cases})
        ).status_code == 422


async def test_avatar_webp_and_animation_rejection(api, settings, tmp_path):
    settings.avatar_storage_dir = tmp_path / "avatars"
    headers = auth(await register(api))
    webp = await api.put(
        "/api/v1/users/me/avatar",
        headers={**headers, "Content-Type": "image/webp"},
        content=png_bytes(format="WEBP"),
    )
    assert webp.status_code == 200
    data = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(
        data,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")],
        duration=100,
        loop=0,
    )
    animated = await api.put(
        "/api/v1/users/me/avatar",
        headers={**headers, "Content-Type": "image/png"},
        content=data.getvalue(),
    )
    assert animated.status_code == 422
    assert (await api.get("/api/v1/users/me", headers=headers)).json()["data"][
        "avatar_url"
    ] == webp.json()["data"]["avatar_url"]
