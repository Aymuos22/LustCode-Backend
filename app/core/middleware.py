import hashlib
import logging
from ipaddress import ip_network
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import AppError
from app.core.proxy import client_address, forwarded_scheme
from app.integrations.redis import Limits

logger = logging.getLogger(__name__)


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.proxy_networks = tuple(ip_network(value) for value in settings.trusted_proxy_networks)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scope = {**scope, "scheme": forwarded_scheme(scope, self.proxy_networks)}
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"x-content-type-options", b"nosniff"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                message["headers"] = headers
            await send(message)

        try:
            headers = dict(scope.get("headers", []))
            max_bytes = (
                self.settings.avatar_max_bytes
                if scope["path"] == "/api/v1/users/me/avatar" and scope["method"] == "PUT"
                else self.settings.request_max_bytes
            )
            length = headers.get(b"content-length")
            if length is not None:
                try:
                    size = int(length)
                except ValueError as exc:
                    raise AppError("invalid_request", "Invalid Content-Length", 400) from exc
                if size < 0:
                    raise AppError("invalid_request", "Invalid Content-Length", 400)
                if size > max_bytes:
                    raise AppError("body_too_large", "Request body exceeds size limit", 413)
            if headers.get(b"content-encoding", b"identity").lower() != b"identity":
                raise AppError(
                    "unsupported_encoding", "Compressed request bodies are unsupported", 415
                )
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > max_bytes:
                    raise AppError("body_too_large", "Request body exceeds size limit", 413)
                if not message.get("more_body", False):
                    break
            path = scope["path"]
            if path.startswith("/api/v1/") and not path.startswith("/api/v1/health/"):
                # Resolve identity from explicitly trusted peers; Uvicorn proxy parsing is off.
                ip = client_address(
                    scope, self.proxy_networks, self.settings.trusted_client_ip_header
                )
                identity = hashlib.sha256(ip.encode()).hexdigest()
                limits = Limits(scope["app"].state.redis, self.settings)
                await limits.rate(f"ip:{identity}")
                if path.startswith("/api/v1/auth/"):
                    await limits.rate(f"auth:{identity}", auth=True)
        except AppError as exc:
            response = JSONResponse(
                {"error": {"code": exc.code, "message": exc.message, "request_id": request_id}},
                status_code=exc.status,
                headers={"Retry-After": "60"} if exc.status == 429 else None,
            )
            await response(scope, receive, secure_send)
            return

        delivered = False

        async def buffered_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, secure_send)
