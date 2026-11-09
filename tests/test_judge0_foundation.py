import asyncio
import base64
import json
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.errors import ProviderError
from app.integrations.judge0 import Judge0, retry_after_seconds
from app.models import Language, Verdict

TOKEN = "d85cd024-1548-4165-96c7-7bc88673f194"


def encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


async def test_public_ce_strips_inherited_rapidapi_headers_and_http_auth(redis, settings) -> None:
    def handler(request):
        assert not any(key.lower().startswith("x-rapidapi-") for key in request.headers)
        assert "authorization" not in request.headers and "x-auth-token" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(200, json=[{"id": 113, "name": "Python (3.14.0)"}])

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        auth=("unwanted", "credential"),
        headers={
            "X-RapidAPI-Key": "do-not-send",
            "X-RapidAPI-Host": "do-not-send",
            "Authorization": "Bearer do-not-send",
            "Cookie": "do-not-send",
            "X-Auth-Token": "do-not-send",
        },
    ) as client:
        assert (await Judge0(client, settings, redis).languages())[0].id == 113


async def test_custom_provider_auth_stays_in_headers(redis, settings) -> None:
    from pydantic import SecretStr

    settings.judge0_url = "https://judge.internal/api"
    settings.judge0_auth_token = SecretStr("private-token")
    settings.judge0_auth_header = "X-Auth-Token"

    def handler(request):
        assert request.url.path == "/api/languages"
        assert request.headers["X-Auth-Token"] == "private-token"
        assert "private-token" not in str(request.url)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await Judge0(client, settings, redis).languages() == []


@pytest.mark.parametrize(
    "token", [None, "", " ", "../languages", "bad?fields=*", "bad/token", "not-a-uuid", "a" * 200]
)
async def test_invalid_poll_tokens_never_make_http_requests(redis, settings, token) -> None:
    def unexpected(request):
        pytest.fail("Invalid token must not reach Judge0")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ProviderError) as error:
            await Judge0(client, settings, redis).poll(token)
        assert error.value.retryable is False


@pytest.mark.parametrize(
    "payload",
    [{}, {"token": None}, {"token": 123}, {"token": ""}, {"token": "../x"}, {"token": "invalid"}],
)
async def test_invalid_creation_tokens_are_not_retryable(redis, settings, payload) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json=payload))
    ) as client:
        with pytest.raises(ProviderError) as error:
            await Judge0(client, settings, redis).create("source", 71, "", None, 2, 131072)
        assert error.value.retryable is False


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 403, 404, 422])
async def test_redirects_and_permanent_get_errors_are_not_retried(redis, settings, status) -> None:
    calls = []
    responses = []

    def handler(request):
        calls.append(request)
        response = httpx.Response(
            status, json={"token": TOKEN}, headers={"Location": "https://untrusted.example"}
        )
        responses.append(response)
        return response

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(ProviderError) as error:
            await Judge0(client, settings, redis).poll(TOKEN)
        assert error.value.retryable is False
    assert len(calls) == 1 and responses[0].is_closed


@pytest.mark.parametrize("status", [429, 503])
async def test_provider_cooldown_is_preserved_without_immediate_poll_retry(
    redis, settings, status
) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="secret-provider-details", headers={"Retry-After": "120"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as error:
            await Judge0(client, settings, redis).poll(TOKEN)
        assert error.value.retry_after == 120 and error.value.retryable
        assert "secret-provider-details" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "value,expected",
    [(None, None), ("invalid", None), ("", None), ("-2", 1), ("9000000", 300), ("42", 42)],
)
def test_retry_after_parsing_is_bounded(value, expected) -> None:
    assert retry_after_seconds(value) == expected


def test_http_date_retry_after() -> None:
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=120), usegmt=True)
    assert 119 <= retry_after_seconds(future) <= 120


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        "invalid",
        [None],
        [{"id": 1, "name": 123}],
        [{"id": True, "name": "Python (3)"}],
        [{"id": -1, "name": "Java (17)"}],
        [{"name": "C++ (GCC)"}],
    ],
)
async def test_malformed_language_registry_maps_to_provider_error(redis, settings, payload) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(ProviderError):
            await Judge0(client, settings, redis).languages()


@pytest.mark.parametrize(
    "cached", ["{}", "[null]", '"invalid"', '[{"id":91,"name":"Java (17)","language":"python"}]']
)
async def test_corrupted_language_cache_falls_back_to_registry(redis, settings, cached) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[{"id": 113, "name": "Python (3.14.0)"}])
        )
    ) as client:
        provider = Judge0(client, settings, redis)
        await redis.set(provider.cache_key, cached)
        assert (await provider.languages())[0].id == 113


async def test_cache_outage_does_not_block_provider_discovery(redis, settings, monkeypatch) -> None:
    from redis.exceptions import ConnectionError

    monkeypatch.setattr(redis, "get", AsyncMock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(redis, "set", AsyncMock(side_effect=ConnectionError("offline")))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[{"id": 91, "name": "Java (JDK 17.0.6)"}])
        )
    ) as client:
        assert (await Judge0(client, settings, redis).languages())[0].language == Language.JAVA


async def test_total_poll_deadline_includes_a_slow_request(redis, settings) -> None:
    settings.judge0_poll_timeout_seconds = 1
    settings.judge0_timeout_seconds = 10

    async def stalled(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json={"status": {"id": 3}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(stalled)) as client:
        started = time.monotonic()
        with pytest.raises(ProviderError, match="polling deadline"):
            await Judge0(client, settings, redis).poll(TOKEN)
        assert time.monotonic() - started < 2


@pytest.mark.parametrize(
    "language,language_id", [(Language.PYTHON, 113), (Language.JAVA, 91), (Language.CPP, 105)]
)
async def test_all_language_submission_and_queued_processing_result_contracts(
    redis, settings, language, language_id
) -> None:
    states = iter([1, 2, 3])
    responses = []

    def handler(request):
        if request.method == "POST":
            assert json.loads(request.content)["language_id"] == language_id
            return httpx.Response(201, json={"token": TOKEN})
        assert (
            request.url.params["fields"]
            == "status,stdout,stderr,compile_output,time,memory,message"
        )
        response = httpx.Response(
            200,
            json={
                "status": {"id": next(states)},
                "stdout": encoded("ok\n"),
                "time": "0.01",
                "memory": 1024,
                "source_code": "do-not-return",
                "expected_output": "do-not-return",
                "token": TOKEN,
                "arbitrary_secret": "do-not-return",
            },
        )
        responses.append(response)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = Judge0(client, settings, redis)
        token = await provider.create("source", language_id, "stdin", "ok\n", 2, 131072)
        result = await provider.poll(token)
        assert result.status == Verdict.ACCEPTED and result.stdout == "ok\n"
        assert "do-not-return" not in result.model_dump_json()
        assert "token" not in result.model_dump()
    assert len(responses) == 3 and all(response.is_closed for response in responses)


@pytest.mark.parametrize("http_status", [429, 500, 503])
async def test_api_provider_unavailability_is_sanitized(
    client, redis, settings, http_status
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                http_status, text="secret-internal-provider-details", headers={"Retry-After": "30"}
            )
        )
    ) as provider_client:
        client._transport.app.state.provider = Judge0(provider_client, settings, redis)
        response = await client.get("/api/v1/languages")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "provider_unavailable"
        assert response.headers["Retry-After"] == "30"
        assert "secret-internal-provider-details" not in response.text


async def test_api_language_response_is_allowlisted(client, redis, settings) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=[{"id": 113, "name": "Python (3.14.0)", "arbitrary_secret": "do-not-return"}],
            )
        )
    ) as provider_client:
        client._transport.app.state.provider = Judge0(provider_client, settings, redis)
        data = (await client.get("/api/v1/languages")).json()["data"]
        assert len(data) == 1
        assert {k: data[0][k] for k in ("id", "name", "language")} == {
            "id": 113,
            "name": "Python (3.14.0)",
            "language": "python",
        }
        assert set(data[0]) == {
            "id",
            "name",
            "language",
            "display_name",
            "capabilities",
            "playground_starter_code",
        }
        assert data[0]["display_name"] == "Python" and data[0]["playground_starter_code"]
        assert "do-not-return" not in str(data)
