import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import yaml
from httpx import AsyncClient as HttpClient
from jsonschema import Draft202012Validator

from app import free_serve
from app.embedded_worker import embedded_worker
from app.integrations.judge0 import ExecutionResult
from app.main import create_app
from app.models import Verdict
from app.runtime import RuntimeResources
from tests.test_integration import auth, register
from tests.test_runtime import factories as factories
from tests.test_sample_runs import sample_question as sample_question


def test_free_blueprint_only_uses_free_services():
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "deploy/render.schema.json").read_text())
    blueprint = yaml.safe_load((root / "render.yaml").read_text())
    Draft202012Validator(schema).validate(blueprint)
    assert len(blueprint["services"]) == 2
    assert all(s["plan"] == "free" for s in blueprint["services"])
    kv, api = blueprint["services"]
    assert kv["ipAllowList"] == [] and kv["persistenceMode"] == "off"
    assert kv["maxmemoryPolicy"] == "noeviction"
    assert api["name"] == "LustCode-Backend"
    assert api["dockerCommand"] == "python -m app.free_serve"
    assert "disk" not in api and "preDeployCommand" not in api
    variables = {v["key"]: v for v in api["envVars"]}
    assert variables["EMBEDDED_WORKER_ENABLED"]["value"] == "true"
    assert variables["DATABASE_URL"]["sync"] is False
    assert variables["JWT_SECRET"]["generateValue"] is True
    assert variables["REDIS_URL"]["fromService"]["name"] == kv["name"]


async def test_embedded_worker_is_opt_in(settings, monkeypatch):
    constructor = MagicMock(side_effect=AssertionError("Must remain disabled"))
    monkeypatch.setattr("app.embedded_worker.EvaluationWorker", constructor)
    async with embedded_worker(MagicMock(), settings) as task:
        assert task is None
    constructor.assert_not_called()


async def test_embedded_worker_receives_shared_resources_and_stops(settings, monkeypatch):
    settings.embedded_worker_enabled = True
    resources = MagicMock()
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def run(redis, stop):
        assert redis is resources.redis
        started.set()
        await stop.wait()
        stopped.set()

    worker = MagicMock()
    worker.run = run
    constructor = MagicMock(return_value=worker)
    monkeypatch.setattr("app.embedded_worker.EvaluationWorker", constructor)
    async with embedded_worker(resources, settings) as task:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not task.done()
    assert stopped.is_set() and task.done() and not task.cancelled()
    constructor.assert_called_once_with(resources.sessions, resources.provider, settings)


async def test_shutdown_cancels_stalled_evaluation_within_budget(settings, monkeypatch):
    settings.embedded_worker_enabled = True
    settings.embedded_worker_shutdown_seconds = 0.02
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run(redis, stop):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    worker = MagicMock()
    worker.run = run
    monkeypatch.setattr("app.embedded_worker.EvaluationWorker", MagicMock(return_value=worker))
    async with embedded_worker(MagicMock(), settings) as task:
        await asyncio.wait_for(started.wait(), timeout=1)
    assert task.cancelled() and cancelled.is_set()


async def test_crashed_evaluator_fails_readiness_without_exposing_error(
    settings, factories, monkeypatch
):
    settings.embedded_worker_enabled = True
    engine, redis, http, *_ = factories
    worker = MagicMock()
    worker.run = AsyncMock(side_effect=RuntimeError("private fixture details"))
    monkeypatch.setattr("app.embedded_worker.EvaluationWorker", MagicMock(return_value=worker))
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
        async with HttpClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            result = await client.get("/api/v1/health/ready")
            assert result.status_code == 503
            assert result.json()["error"]["code"] == "worker_unavailable"
            assert "private fixture" not in result.text
            assert (await client.get("/api/v1/health/live")).status_code == 200
    assert http.is_closed
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.parametrize("failure", [False, True])
def test_free_server_migrates_before_serving_and_aborts_on_failure(monkeypatch, failure):
    calls = []

    def migrate():
        calls.append("migrate")
        if failure:
            raise SystemExit(1)

    monkeypatch.setattr(free_serve.release, "main", migrate)
    monkeypatch.setattr(free_serve.serve, "main", lambda: calls.append("serve"))
    if failure:
        with pytest.raises(SystemExit):
            free_serve.main()
        assert calls == ["migrate"]
    else:
        free_serve.main()
        assert calls == ["migrate", "serve"]


@pytest.mark.integration
async def test_api_background_worker_completes_sample_run(
    sessions, provider, redis, settings, sample_question, monkeypatch
):
    settings.embedded_worker_enabled = True
    visible = [row for row in sample_question["cases"] if not row["hidden"]]
    provider.results = [
        ExecutionResult(status=Verdict.ACCEPTED, stdout=row["expected_output"]) for row in visible
    ]

    @asynccontextmanager
    async def resources(config):
        async with httpx.AsyncClient() as http:
            yield RuntimeResources(MagicMock(), sessions, redis, http, provider)

    monkeypatch.setattr("app.main.runtime_resources", resources)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            tokens = await register(client)
            response = await client.post(
                f"/api/v1/questions/{sample_question['id']}/runs",
                headers=auth(tokens),
                json={"language": "python", "source_code": "class Solution: pass"},
            )
            assert response.status_code == 202
            identifier = response.json()["data"]["id"]
            async with asyncio.timeout(5):
                while True:
                    response = await client.get(
                        "/api/v1/submissions/" + identifier, headers=auth(tokens)
                    )
                    data = response.json()["data"]
                    if data["status"] not in ("queued", "running"):
                        break
                    await asyncio.sleep(0.03)
            assert data["status"] == "accepted"
            assert data["passed_tests"] == len(visible)
            assert len(provider.created) == len(visible)
            assert (await client.get("/api/v1/health/ready")).status_code == 200
