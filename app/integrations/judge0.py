import asyncio
import base64
import binascii
import hashlib
import json
import math
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.errors import AppError, ProviderError
from app.models import Language, Verdict
from app.schemas import LanguageView


class ExecutionResult(BaseModel):
    status: Verdict
    stdout: str | None = None
    stderr: str | None = None
    compile_output: str | None = None
    execution_time: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    memory_kb: int | None = Field(default=None, ge=0)


class RawStatus(BaseModel):
    id: int = Field(strict=True, gt=0)


class RawLanguage(BaseModel):
    id: int = Field(strict=True, gt=0)
    name: str = Field(strict=True, min_length=1, max_length=150)


class RawResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: RawStatus
    stdout: str | None = None
    stderr: str | None = None
    compile_output: str | None = None
    message: str | None = None
    time: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    memory: int | None = Field(default=None, ge=0)


class ExecutionProvider(Protocol):
    async def languages(self) -> list[LanguageView]: ...

    async def create(
        self,
        source: str,
        language_id: int,
        stdin: str,
        expected: str | None,
        cpu: float,
        memory: int,
        compiler_options: str | None = None,
    ) -> str: ...

    async def poll(self, token: str) -> ExecutionResult: ...


def classify_language(name: str) -> Language | None:
    if name.startswith("Python (3"):
        return Language.PYTHON
    if name.startswith("Java ("):
        return Language.JAVA
    if name.startswith("C++ ("):
        return Language.CPP
    return None


def decode_text(value: str | None, limit: int | None = 16384) -> str | None:
    if value is None:
        return None
    # Judge0's Base64 encoder may wrap lines and append a newline.
    value = re.sub(r"[ \t\r\n]", "", value)
    decoded = (
        base64.b64decode(value, validate=True)
        .decode(
            "utf-8",
            errors="replace",
        )
        .replace("\x00", "\ufffd")
    )
    return decoded if limit is None else decoded[:limit]


def validate_token(value: object) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower():
            raise ValueError("Invalid token")
    except (ValueError, AttributeError) as exc:
        raise ProviderError(
            "Execution provider returned an invalid submission token", retryable=False
        ) from exc
    return value.lower()


def retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        try:
            until = parsedate_to_datetime(value)
            if until.tzinfo is None:
                until = until.replace(tzinfo=UTC)
            seconds = math.ceil((until - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None
    return max(1, min(seconds, 300))


class Judge0:
    def __init__(
        self, client: httpx.AsyncClient, settings: Settings, redis: Redis | None = None
    ) -> None:
        self.client = client
        self.settings = settings
        self.redis = redis
        self.public_ce = urlsplit(settings.judge0_url).hostname == "ce.judge0.com"
        self.cache_key = (
            "judge0:languages:" + hashlib.sha256(settings.judge0_url.encode()).hexdigest()
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
    ) -> object:
        headers = {}
        headers["Accept-Encoding"] = "identity"
        if self.settings.judge0_auth_token:
            headers[self.settings.judge0_auth_header] = (
                self.settings.judge0_auth_token.get_secret_value()
            )
        try:
            # Bound decoded body size even when Content-Length is missing or compressed.
            async with asyncio.timeout(self.settings.judge0_timeout_seconds):
                request = self.client.build_request(
                    method,
                    self.settings.judge0_url.rstrip("/") + path,
                    headers=headers,
                    timeout=self.settings.judge0_timeout_seconds,
                    params=params,
                    json=payload,
                )
                if self.public_ce:
                    # Also protect against credentials inherited from an injected HTTPX client.
                    for name in list(request.headers):
                        lower = name.lower()
                        if lower.startswith("x-rapidapi-") or (
                            lower
                            in {
                                "authorization",
                                "proxy-authorization",
                                "cookie",
                                "x-auth-token",
                                "x-auth-user",
                            }
                            and lower not in {key.lower() for key in headers}
                        ):
                            del request.headers[name]
                response = await self.client.send(
                    request, stream=True, auth=None, follow_redirects=False
                )
                try:
                    cooldown = retry_after_seconds(response.headers.get("Retry-After"))
                    if response.status_code == 429:
                        raise ProviderError(
                            "Execution provider rate limit reached; retry later",
                            retry_after=cooldown or 60,
                        )
                    if not response.is_success:
                        raise ProviderError(
                            retryable=response.status_code in (408, 425)
                            or response.status_code >= 500,
                            retry_after=cooldown,
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        if len(body) + len(chunk) > self.settings.judge0_response_bytes:
                            raise ProviderError(
                                "Execution provider response exceeded its size limit"
                            )
                        body.extend(chunk)
                    return json.loads(body)
                finally:
                    await response.aclose()
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            raise ProviderError() from exc

    async def languages(self) -> list[LanguageView]:
        try:
            cached = await self.redis.get(self.cache_key) if self.redis is not None else None
            if cached:
                items = TypeAdapter(list[LanguageView]).validate_json(cached)
                if any(
                    item.id <= 0 or classify_language(item.name) != item.language for item in items
                ):
                    raise ValueError("Invalid language cache")
                return items
        except (RedisError, ValueError, TypeError):
            pass  # Cache failures must not prevent provider discovery.
        payload = await self._request("GET", "/languages")
        try:
            result = []
            for item in TypeAdapter(list[RawLanguage]).validate_python(payload):
                language = classify_language(item.name)
                if language:
                    result.append(LanguageView(id=item.id, name=item.name, language=language))
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Execution provider returned invalid languages") from exc
        try:
            if self.redis is not None:
                await self.redis.set(
                    self.cache_key, json.dumps([x.model_dump() for x in result]), ex=3600
                )
        except RedisError:
            pass
        return result

    async def create(
        self,
        source: str,
        language_id: int,
        stdin: str,
        expected: str | None,
        cpu: float,
        memory: int,
        compiler_options: str | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "source_code": base64.b64encode(source.encode()).decode(),
            "language_id": language_id,
            "stdin": base64.b64encode(stdin.encode()).decode(),
            "cpu_time_limit": min(cpu, self.settings.max_cpu_seconds),
            "wall_time_limit": min(cpu * 3 + 1, 30),
            "memory_limit": min(memory, self.settings.max_memory_kb),
            "stack_limit": min(memory, 65536),
            "max_file_size": 64,
            "number_of_runs": 1,
            "enable_network": False,
        }
        if expected is not None:
            payload["expected_output"] = base64.b64encode(expected.encode()).decode()
        if compiler_options is not None:
            payload["compiler_options"] = compiler_options
        # POST is deliberately not retried: a lost response may already have executed code.
        result = await self._request(
            "POST",
            "/submissions",
            params={"base64_encoded": "true", "wait": "false"},
            payload=payload,
        )
        if not isinstance(result, dict) or not isinstance(result.get("token"), str):
            raise ProviderError(
                "Execution provider returned an invalid submission token", retryable=False
            )
        return validate_token(result["token"])

    async def poll(self, token: str) -> ExecutionResult:
        token = validate_token(token)
        try:
            async with asyncio.timeout(self.settings.judge0_poll_timeout_seconds):
                return await self._poll(token)
        except TimeoutError as exc:
            raise ProviderError(
                "Execution provider did not finish within the polling deadline"
            ) from exc

    async def _poll(self, token: str) -> ExecutionResult:
        deadline = time.monotonic() + self.settings.judge0_poll_timeout_seconds
        failures = 0
        while time.monotonic() < deadline:
            try:
                data = await self._request(
                    "GET",
                    f"/submissions/{token}",
                    params={
                        "base64_encoded": "true",
                        "fields": "status,stdout,stderr,compile_output,time,memory,message",
                    },
                )
                raw = RawResult.model_validate(data)
                failures = 0
            except ProviderError as exc:
                failures += 1
                if not exc.retryable or exc.retry_after is not None or failures >= 3:
                    raise
                await asyncio.sleep(min(2**failures, 5))
                continue
            except ValidationError as exc:
                raise ProviderError("Execution provider returned an invalid result") from exc
            if raw.status.id in (1, 2):
                await asyncio.sleep(self.settings.judge0_poll_seconds)
                continue
            statuses = {
                3: Verdict.ACCEPTED,
                4: Verdict.WRONG_ANSWER,
                5: Verdict.TIME_LIMIT_EXCEEDED,
                6: Verdict.COMPILATION_ERROR,
                7: Verdict.RUNTIME_ERROR,
                8: Verdict.RUNTIME_ERROR,
                9: Verdict.RUNTIME_ERROR,
                10: Verdict.RUNTIME_ERROR,
                11: Verdict.RUNTIME_ERROR,
                12: Verdict.PROVIDER_ERROR,
                13: Verdict.RUNTIME_ERROR,
            }
            status = statuses.get(raw.status.id, Verdict.PROVIDER_ERROR)
            try:
                stderr = decode_text(raw.stderr)
                message = decode_text(raw.message)
                # CE has no portable dedicated MLE status; only classify explicit evidence.
                evidence = ((stderr or "") + (message or "")).lower()
                if status == Verdict.RUNTIME_ERROR and any(
                    marker in evidence
                    for marker in (
                        "memory limit",
                        "memoryerror",
                        "outofmemoryerror",
                        "std::bad_alloc",
                    )
                ):
                    status = Verdict.MEMORY_LIMIT_EXCEEDED
                return ExecutionResult(
                    status=status,
                    stdout=decode_text(raw.stdout, limit=None),
                    stderr=stderr,
                    compile_output=decode_text(raw.compile_output),
                    execution_time=raw.time,
                    memory_kb=raw.memory,
                )
            except (ValueError, binascii.Error) as exc:
                raise ProviderError("Execution provider returned invalid encoded output") from exc
        raise ProviderError("Execution provider did not finish within the polling deadline")


async def select_language(
    provider: ExecutionProvider,
    language: Language,
    language_id: int | None,
) -> LanguageView:
    options = [item for item in await provider.languages() if item.language == language]
    if language_id is not None:
        options = [item for item in options if item.id == language_id]
    if not options:
        raise AppError("language_unavailable", "Requested language/version is unavailable", 422)
    return max(options, key=lambda item: item.id)
