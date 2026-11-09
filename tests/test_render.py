import asyncio
import json
import os
import sys
import threading
import time
from ipaddress import ip_network
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
import yaml
from anyio import CapacityLimiter
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app import release, serve
from app.core.config import Settings
from app.core.errors import AppError
from app.core.proxy import client_address, forwarded_scheme
from app.db import create_engine
from app.main import create_app
from app.schemas import Credentials
from app.services.auth import AuthService
from app.services.avatars import AvatarService

ROOT = Path(__file__).resolve().parents[1]
TRUSTED = (ip_network("10.0.0.0/8"), ip_network("2606:4700::/32"))


def config(settings, **updates):
    return Settings(_env_file=None, **(settings.model_dump() | updates))


def scope(peer="10.1.2.3", **headers):
    return {
        "client": (peer, 1234),
        "scheme": "http",
        "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()],
    }


def test_blueprint_matches_official_schema_and_production_settings():
    # Snapshot: https://render.com/schema/render.yaml.json, retrieved 2026-11-10.
    schema = json.loads((ROOT / "deploy/render.schema.json").read_text())
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text())
    Draft202012Validator(schema).validate(blueprint)
    shared = {
        item["key"].lower(): item["value"]
        for item in blueprint["envVarGroups"][0]["envVars"]
        if "value" in item
    }
    for key in ("cors_origins", "trusted_proxy_networks"):
        shared[key] = json.loads(shared[key])
    settings = Settings(
        _env_file=None,
        **shared,
        database_url="postgresql+asyncpg://postgres.fixture:synthetic@pooler.supabase.com:5432/postgres",
        redis_url="redis://red-fixture:6379",
        jwt_secret="synthetic-render-secret-with-at-least-32-characters",
        avatar_storage_dir="/srv/lustcode/var/avatars",
    )
    assert settings.environment == "production" and settings.cors_origins == ["*"]
    assert settings.readiness_timeout_seconds < 5
    assert settings.trusted_client_ip_header == "cf-connecting-ip"
    kv, api, worker = blueprint["services"]
    assert kv["ipAllowList"] == [] and kv["maxmemoryPolicy"] == "noeviction"
    assert kv["persistenceMode"] == "journal-snapshot" and kv["plan"] != "free"
    assert api["disk"]["mountPath"] == str(settings.avatar_storage_dir)
    assert api["numInstances"] == worker["numInstances"] == 1
    assert api["healthCheckPath"] == "/api/v1/health/ready"
    assert api["preDeployCommand"] == worker["preDeployCommand"] == "python -m app.release"
    assert all(s["autoDeployTrigger"] == "checksPass" for s in (api, worker))
    db = next(item for item in api["envVars"] if item.get("key") == "DATABASE_URL")
    assert db == {"key": "DATABASE_URL", "sync": False}
    db_ref = next(item for item in worker["envVars"] if item.get("key") == "DATABASE_URL")
    assert db_ref["fromService"]["envVarKey"] == "DATABASE_URL"
    jwt = next(
        item for item in blueprint["envVarGroups"][0]["envVars"] if item["key"] == "JWT_SECRET"
    )
    assert jwt == {"key": "JWT_SECRET", "generateValue": True}


@pytest.mark.parametrize("origin", ["http://localhost:5173", "https://frontend.example"])
async def test_open_cors_keeps_credentials_disabled_and_auth_required(settings, redis, origin):
    app = create_app(config(settings, cors_allow_all_origins=True))
    async with app.router.lifespan_context(app):
        app.state.redis = redis
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            preflight = await client.options(
                "/api/v1/users/me",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == "*"
            assert "access-control-allow-credentials" not in preflight.headers
            response = await client.get("/api/v1/users/me", headers={"Origin": origin})
            assert response.status_code == 401
            assert response.headers["access-control-allow-origin"] == "*"


def test_cors_and_proxy_trust_require_explicit_configuration(settings):
    with pytest.raises(ValidationError):
        config(settings, cors_origins=["*"])
    for networks in (["0.0.0.0/0"], ["::/0"], ["invalid"]):
        with pytest.raises(ValidationError):
            config(settings, trusted_proxy_networks=networks)
    app = create_app(
        config(settings, environment="production", database_ssl=True, cors_allow_all_origins=True)
    )
    assert app.docs_url is None and app.openapi_url is None


@pytest.mark.parametrize("header", ["x-forwarded-for", "cf-connecting-ip"])
def test_untrusted_peer_cannot_override_identity_or_scheme(header):
    request = scope("198.51.100.10", x_forwarded_for="1.2.3.4", cf_connecting_ip="1.2.3.4")
    request["headers"].append((b"x-forwarded-proto", b"https"))
    assert client_address(request, TRUSTED, header) == "198.51.100.10"
    assert forwarded_scheme(request, TRUSTED) == "http"


def test_trusted_cloudflare_identity_ignores_spoofed_xff():
    request = scope(cf_connecting_ip="198.51.100.20", x_forwarded_for="1.2.3.4")
    assert client_address(request, TRUSTED, "cf-connecting-ip") == "198.51.100.20"
    request["headers"].append((b"x-forwarded-proto", b"https"))
    assert forwarded_scheme(request, TRUSTED) == "https"


@pytest.mark.parametrize("value", ["", "invalid", "198.51.100.1,1.2.3.4"])
def test_malformed_cloudflare_identity_falls_back_to_peer(value):
    assert client_address(scope(cf_connecting_ip=value), TRUSTED, "cf-connecting-ip") == "10.1.2.3"


def test_duplicate_headers_are_not_trusted():
    request = scope(cf_connecting_ip="198.51.100.1", x_forwarded_proto="https")
    request["headers"] *= 2
    assert client_address(request, TRUSTED, "cf-connecting-ip") == "10.1.2.3"
    assert forwarded_scheme(request, TRUSTED) == "http"


def test_xff_walks_from_trusted_peer_and_ignores_attacker_prefix():
    request = scope(x_forwarded_for="1.2.3.4, 198.51.100.20, 10.2.3.4")
    assert client_address(request, TRUSTED) == "198.51.100.20"
    assert client_address(request, ()) == "10.1.2.3"
    assert client_address(scope(x_forwarded_for="invalid"), TRUSTED) == "10.1.2.3"
    assert client_address(scope(x_forwarded_for=",".join(["1.2.3.4"] * 33)), TRUSTED) == "10.1.2.3"


def test_ipv6_cloudflare_peer_and_client():
    request = scope("2606:4700::1", cf_connecting_ip="2001:db8::12")
    assert client_address(request, TRUSTED, "cf-connecting-ip") == "2001:db8::12"


@pytest.mark.parametrize("value", ["0", "65536", "invalid"])
def test_invalid_port_fails_before_server_start(value):
    with pytest.raises(ValueError):
        serve.port(value)


@pytest.mark.parametrize("value,expected", [(None, 8000), ("10000", 10000)])
def test_server_uses_platform_port_and_disables_implicit_proxy_trust(monkeypatch, value, expected):
    monkeypatch.delenv("PORT", raising=False)
    if value:
        monkeypatch.setenv("PORT", value)
    run = MagicMock()
    monkeypatch.setattr(serve.uvicorn, "run", run)
    serve.main()
    options = run.call_args.kwargs
    assert options["port"] == expected and options["host"] == "0.0.0.0"
    assert options["proxy_headers"] is False and options["access_log"] is False
    assert options["timeout_graceful_shutdown"] < 30


def test_image_ca_override_replaces_native_url_path(settings, monkeypatch):
    settings = config(
        settings,
        database_url="postgresql+asyncpg://host/db?sslmode=verify-full&sslrootcert=/native/ca.crt",
        database_ssl_root_cert=ROOT / "certs/supabase-root-2021.crt",
    )
    factory = MagicMock()
    ssl_factory = MagicMock()
    monkeypatch.setattr("app.db.create_async_engine", factory)
    monkeypatch.setattr("app.db.ssl.create_default_context", ssl_factory)
    create_engine(settings)
    ssl_factory.assert_called_once_with(cafile=str(settings.database_ssl_root_cert))
    assert factory.call_args.args[0].query == {}


@pytest.mark.parametrize("failure", [False, True])
async def test_release_holds_transaction_lock_and_disposes_on_failure(
    settings, monkeypatch, failure
):
    connection = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = context
    engine.dispose = AsyncMock()
    monkeypatch.setattr(release, "create_engine", MagicMock(return_value=engine))

    def upgrade(*args):
        assert connection.execute.await_count == 1
        assert context.__aexit__.await_count == 0
        if failure:
            raise RuntimeError("synthetic migration failure")

    monkeypatch.setattr(release.command, "upgrade", upgrade)
    if failure:
        with pytest.raises(RuntimeError, match="synthetic migration failure"):
            await release.upgrade(settings)
    else:
        await release.upgrade(settings)
    assert "pg_advisory_xact_lock" in str(connection.execute.call_args.args[0])
    engine.dispose.assert_awaited_once()
    context.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("kind", ["password", "avatar"])
async def test_expensive_work_is_bounded_without_blocking_event_loop(settings, monkeypatch, kind):
    lock = threading.Lock()
    active = peak = 0

    def expensive(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return False if kind == "password" else b"normalized"

    limiter = CapacityLimiter(2)
    session = AsyncMock()
    if kind == "password":
        monkeypatch.setattr("app.services.auth.password_hasher", SimpleNamespace(verify=expensive))
        service = AuthService(session, settings, "dummy", limiter)
        service.repo.user_by_email = AsyncMock(return_value=None)
        payload = Credentials(email="test@example.com", password="synthetic-password")
        operations = [service.login(payload) for _ in range(8)]
    else:
        monkeypatch.setattr("app.services.avatars.normalized_avatar", expensive)
        session.scalar.side_effect = AppError("fixture", "stop before storage", 409)
        service = AvatarService(session, settings, limiter)
        operations = [service.update(uuid4(), b"input", "image/png") for _ in range(8)]
    group = asyncio.gather(*operations, return_exceptions=True)
    ticks = 0
    while not group.done():
        await asyncio.sleep(0.005)
        ticks += 1
    results = await group
    assert all(isinstance(result, AppError) for result in results)
    assert peak == 2 and active == 0
    assert ticks >= 5


@pytest.mark.integration
async def test_concurrent_release_processes_serialize_real_migrations():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for isolated release verification")
    # Own database: never downgrade or reset the application database.
    name = "release_" + uuid4().hex
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    processes = []
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        target = make_url(url).set(database=name).render_as_string(hide_password=False)
        env = os.environ | {
            "DATABASE_URL": target,
            "MIGRATION_DATABASE_URL": target,
            "DATABASE_SSL": "false",
            "ENVIRONMENT": "test",
            "JWT_SECRET": "synthetic-release-test-secret-at-least-32-characters",
        }
        for _ in range(2):
            processes.append(
                await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "app.release",
                    cwd=ROOT,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            )
        await asyncio.wait_for(asyncio.gather(*(p.communicate() for p in processes)), timeout=60)
        assert all(p.returncode == 0 for p in processes)
        engine = create_async_engine(target)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "e42b19c06d31"
                )
                tables = await connection.scalar(
                    text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity")
                )
                assert tables == 9
        finally:
            await engine.dispose()
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
