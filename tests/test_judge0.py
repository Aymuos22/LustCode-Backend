import base64
import json

import httpx
import pytest

from app.core.errors import AppError, ProviderError
from app.integrations.judge0 import Judge0, select_language
from app.models import Language, Verdict

TOKEN = "d85cd024-1548-4165-96c7-7bc88673f194"


def encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


async def test_language_discovery_cached_and_filtered(redis, settings) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=[
                {"id": 1, "name": "Python (2.7.17)"},
                {"id": 71, "name": "Python (3.8.1)"},
                {"id": 91, "name": "Python (3.11.2)"},
                {"id": 62, "name": "Java (OpenJDK 13)"},
                {"id": 54, "name": "C++ (GCC 9)"},
                {"id": 63, "name": "JavaScript (Node.js 12)"},
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = Judge0(client, settings, redis)
        assert len(await provider.languages()) == 4
        assert (await select_language(provider, Language.PYTHON, None)).id == 91
        assert (await select_language(provider, Language.PYTHON, 71)).id == 71
        with pytest.raises(AppError):
            await select_language(provider, Language.PYTHON, 62)
    assert len(calls) == 1


async def test_submission_encodes_text_and_enforces_limits(redis, settings) -> None:
    def handler(request):
        assert request.url.params["base64_encoded"] == "true"
        payload = json.loads(request.content)
        assert payload["source_code"] == encoded("print('💥')")
        assert payload["stdin"] == encoded("\x00💥")
        assert payload["expected_output"] == encoded("ok")
        assert payload["cpu_time_limit"] == settings.max_cpu_seconds
        assert payload["memory_limit"] == settings.max_memory_kb
        assert payload["enable_network"] is False
        return httpx.Response(201, json={"token": TOKEN})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (
            await Judge0(client, settings, redis).create(
                "print('💥')", 71, "\x00💥", "ok", 999, 9999999
            )
            == TOKEN
        )


@pytest.mark.parametrize(
    "status,expected",
    [
        (3, Verdict.ACCEPTED),
        (4, Verdict.WRONG_ANSWER),
        (5, Verdict.TIME_LIMIT_EXCEEDED),
        (6, Verdict.COMPILATION_ERROR),
        (7, Verdict.RUNTIME_ERROR),
        (8, Verdict.RUNTIME_ERROR),
        (9, Verdict.RUNTIME_ERROR),
        (10, Verdict.RUNTIME_ERROR),
        (11, Verdict.RUNTIME_ERROR),
        (12, Verdict.PROVIDER_ERROR),
        (13, Verdict.RUNTIME_ERROR),
        (999, Verdict.PROVIDER_ERROR),
    ],
)
async def test_verdicts(redis, settings, status, expected) -> None:
    def handler(request):
        return httpx.Response(
            200,
            json={"status": {"id": status}, "stdout": encoded("ok"), "time": "0.01", "memory": 500},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Judge0(client, settings, redis).poll(TOKEN)
        assert result.status == expected and result.stdout == "ok"


async def test_pending_poll_and_memory_detection(redis, settings) -> None:
    statuses = iter([1, 2, 11])

    def handler(request):
        return httpx.Response(
            200, json={"status": {"id": next(statuses)}, "stderr": encoded("MemoryError")}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (
            await Judge0(client, settings, redis).poll(TOKEN)
        ).status == Verdict.MEMORY_LIMIT_EXCEEDED


@pytest.mark.parametrize("http_status", [429, 500, 503, 401, 422])
async def test_provider_errors_not_retried_on_create(redis, settings, http_status) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(http_status, text="secret-provider-details")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as error:
            await Judge0(client, settings, redis).create("a", 71, "", None, 2, 100000)
        assert "secret-provider" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body", [b"not-json", b'{"status":{"id":3},"stdout":"!"}', b'{"status":{}}']
)
async def test_malformed_provider_response(redis, settings, body) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(ProviderError):
            await Judge0(client, settings, redis).poll(TOKEN)


async def test_provider_response_size_limit(redis, settings) -> None:
    settings.judge0_response_bytes = 1024
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 1025))
    ) as client:
        with pytest.raises(ProviderError):
            await Judge0(client, settings, redis).languages()


async def test_network_timeout_is_classified(redis, settings) -> None:
    def timeout(request):
        raise httpx.ReadTimeout("internal-network-details", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ProviderError):
            await Judge0(client, settings, redis).create("code", 71, "", None, 1, 100000)


async def test_provider_request_has_absolute_deadline(redis, settings) -> None:
    import asyncio

    settings.judge0_timeout_seconds = 1

    async def stalled_handler(request):
        await asyncio.sleep(5)
        return httpx.Response(201, json={"token": "too-late"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(stalled_handler)) as client:
        with pytest.raises(ProviderError):
            await Judge0(client, settings, redis).create("code", 71, "", None, 1, 100000)


async def test_get_retries_transient_errors(redis, settings, monkeypatch) -> None:
    from unittest.mock import AsyncMock

    import app.integrations.judge0 as module

    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"status": {"id": 3}, "stdout": encoded("a\0b")})

    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Judge0(client, settings, redis).poll(TOKEN)
        assert result.status == Verdict.ACCEPTED and result.stdout == "a\ufffdb"
    assert len(calls) == 3


async def test_wrapped_base64_output(redis, settings) -> None:
    output = "hello from Judge0\n" * 100
    wrapped = base64.encodebytes(output.encode()).decode()
    assert "\n" in wrapped
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"status": {"id": 3}, "stdout": wrapped}),
        )
    ) as client:
        result = await Judge0(client, settings, redis).poll(TOKEN)
        assert result.stdout == output


async def test_poll_deadline(redis, settings, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import app.integrations.judge0 as module

    clock = iter([0, 0, settings.judge0_poll_timeout_seconds + 1])
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"status": {"id": 2}}),
        )
    ) as client:
        with pytest.raises(ProviderError, match="polling deadline"):
            await Judge0(client, settings, redis).poll(TOKEN)


async def test_server_cpp_standard_and_backend_comparison_do_not_send_expected_output(settings):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["compiler_options"] == "-std=c++17"
        assert "expected_output" not in payload
        return httpx.Response(201, json={"token": TOKEN})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (
            await Judge0(client, settings).create(
                "int main(){}", 54, "A 0\n", None, 2, 131072, compiler_options="-std=c++17"
            )
            == TOKEN
        )
