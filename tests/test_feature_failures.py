import asyncio

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.judge0 import ExecutionResult
from app.judging.wire import INVALID_RESULT
from app.models import Verdict
from app.worker import EvaluationWorker
from tests.test_frontend_features import png_bytes
from tests.test_integration import auth, register
from tests.test_sample_runs import sample_question as sample_question

pytestmark = pytest.mark.integration


async def test_empty_catalog_and_invalid_optional_auth(api):
    assert (await api.get("/api/v1/topics")).json() == {"data": []}
    assert (await api.get("/api/v1/questions/featured")).json()["data"]["questions"] == []
    assert (await api.get("/api/v1/questions/random")).status_code == 404
    assert (
        await api.get("/api/v1/collections", headers={"Authorization": "Basic invalid"})
    ).status_code == 401


async def test_concurrent_first_draft_save_has_one_winner(api):
    headers = auth(await register(api))
    path = "/api/v1/users/me/drafts/playground/python"
    responses = await asyncio.gather(
        *[
            api.put(path, headers=headers, json={"revision": 0, "source_code": str(i)})
            for i in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (await api.get(path, headers=headers)).json()["data"]["revision"] == 1


async def test_avatar_database_failure_preserves_previous_image(
    api, settings, tmp_path, monkeypatch
):
    settings.avatar_storage_dir = tmp_path / "avatars"
    headers = auth(await register(api))
    old = (
        await api.put(
            "/api/v1/users/me/avatar",
            headers={**headers, "Content-Type": "image/png"},
            content=png_bytes(),
        )
    ).json()["data"]["avatar_url"]

    async def failure(self):
        raise OperationalError("fixture", {}, Exception("private database details"))

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", failure)
        response = await api.put(
            "/api/v1/users/me/avatar",
            headers={**headers, "Content-Type": "image/png"},
            content=png_bytes(),
        )
    assert response.status_code == 503 and "private database" not in response.text
    assert len(list(settings.avatar_storage_dir.iterdir())) == 1
    assert (await api.get(old)).status_code == 200


@pytest.mark.parametrize(
    "status,stdout,expected",
    [
        (Verdict.ACCEPTED, INVALID_RESULT, "runtime_error"),
        (Verdict.COMPILATION_ERROR, None, "compilation_error"),
        (Verdict.RUNTIME_ERROR, None, "runtime_error"),
        (Verdict.PROVIDER_ERROR, None, "provider_error"),
    ],
)
async def test_custom_run_execution_failures_remain_failures(
    api, sessions, provider, settings, sample_question, status, stdout, expected
):
    headers = auth(await register(api))
    response = await api.post(
        f"/api/v1/questions/{sample_question['id']}/runs",
        headers=headers,
        json={
            "language": "python",
            "source_code": "class Solution: pass",
            "test_cases": [{"stdin": "[[2,3],5]"}],
        },
    )
    assert response.status_code == 202
    provider.results = [ExecutionResult(status=status, stdout=stdout)]
    assert await EvaluationWorker(sessions, provider, settings).once()
    result = (
        await api.get("/api/v1/submissions/" + response.json()["data"]["id"], headers=headers)
    ).json()["data"]
    assert result["status"] == expected
    assert (await api.get("/api/v1/users/me/progress", headers=headers)).json()["total"] == 0
