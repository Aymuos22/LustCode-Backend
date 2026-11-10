import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anyio import CapacityLimiter
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from app.api.engagement import router as engagement_router
from app.api.features import router as features_router
from app.api.routes import router
from app.core.config import Settings
from app.core.errors import AppError, ProviderError
from app.core.logging import configure_logging
from app.core.middleware import SecurityMiddleware
from app.core.security import password_hasher
from app.embedded_worker import embedded_worker
from app.runtime import runtime_resources
from app.schemas import ErrorResponse
from app.services.health import check_readiness

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        async with runtime_resources(config) as resources:
            app.state.settings = config
            app.state.sessions = resources.sessions
            app.state.redis = resources.redis
            app.state.http_client = resources.http
            app.state.provider = resources.provider
            app.state.password_limiter = CapacityLimiter(config.password_hash_concurrency)
            app.state.avatar_limiter = CapacityLimiter(config.avatar_processing_concurrency)
            app.state.dummy_hash = await run_in_threadpool(
                password_hasher.hash, secrets.token_hex(32)
            )
            async with embedded_worker(resources, config) as task:
                app.state.embedded_worker_task = task
                yield

    app = FastAPI(
        title="LustCode API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/v1/docs" if config.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json" if config.environment != "production" else None,
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 404, 409, 413, 415, 422, 429, 500, 503)
        },
    )
    app.state.settings = config
    app.add_middleware(SecurityMiddleware, settings=config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    def error_response(request: Request, code: str, message: str, status: int) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        if status == 429:
            headers["Retry-After"] = "60"
        return JSONResponse(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
            status_code=status,
            headers=headers,
        )

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        response = error_response(request, exc.code, exc.message, exc.status)
        if exc.current_revision is not None:
            import json

            body = json.loads(response.body)
            body["error"]["current_revision"] = exc.current_revision
            response = JSONResponse(
                body,
                status_code=exc.status,
                headers={
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() != "content-length"
                },
            )
        if isinstance(exc, ProviderError) and exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        response = error_response(request, "validation_error", "Invalid request", 422)
        # Pydantic error input and context can contain passwords/source code; omit both.
        import json

        body = json.loads(response.body)
        body["error"]["details"] = [
            {"location": list(e["loc"]), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse(body, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, "http_error", str(exc.detail), exc.status_code)

    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(RedisError)
    @app.exception_handler(OSError)
    async def infrastructure_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Infrastructure request failure",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return error_response(
            request, "infrastructure_unavailable", "Service temporarily unavailable", 503
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unexpected request failure",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return error_response(request, "internal_error", "Internal server error", 500)

    @app.get("/api/v1/health/live", tags=["health"])
    async def live() -> dict[str, dict[str, str]]:
        return {"data": {"status": "ok"}}

    @app.get("/api/v1/health/ready", tags=["health"])
    async def ready(request: Request) -> dict[str, dict[str, str]]:
        task = request.app.state.embedded_worker_task
        if config.embedded_worker_enabled and (task is None or task.done()):
            raise AppError("worker_unavailable", "Execution worker is unavailable", 503)
        await check_readiness(
            request.app.state.sessions, request.app.state.redis, config.readiness_timeout_seconds
        )
        return {"data": {"status": "ready"}}

    app.include_router(engagement_router)
    app.include_router(features_router)
    app.include_router(router)
    return app
