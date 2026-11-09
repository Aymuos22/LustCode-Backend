import ssl
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database_config import database_target
from app.db import create_engine


def config(settings, **updates) -> Settings:
    return Settings(_env_file=None, **(settings.model_dump() | updates))


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_supabase_url_tls_is_normalized(settings, monkeypatch, mode) -> None:
    factory = MagicMock()
    monkeypatch.setattr("app.db.create_async_engine", factory)
    settings = config(
        settings,
        database_url=SecretStr(
            f"postgresql+asyncpg://postgres.project:password@aws-0.pooler.supabase.com:5432/postgres?sslmode={mode}"
        ),
        database_pool_size=2,
        database_max_overflow=1,
    )
    create_engine(settings)
    args, kwargs = factory.call_args
    assert args[0].query == {}  # asyncpg.connect does not accept sslmode as a keyword.
    tls = kwargs["connect_args"]["ssl"]
    assert isinstance(tls, ssl.SSLContext)
    assert tls.verify_mode == ssl.CERT_REQUIRED and tls.check_hostname
    assert kwargs["pool_size"] == 2 and kwargs["max_overflow"] == 1
    assert kwargs["pool_pre_ping"] is True and kwargs["hide_parameters"] is True
    assert kwargs["connect_args"]["timeout"] == settings.database_connect_timeout_seconds
    assert kwargs["pool_timeout"] == settings.database_pool_timeout_seconds
    assert kwargs["pool_recycle"] == settings.database_pool_recycle_seconds


def test_native_database_explicitly_disables_tls(settings, monkeypatch) -> None:
    factory = MagicMock()
    monkeypatch.setattr("app.db.create_async_engine", factory)
    create_engine(settings)
    assert factory.call_args.kwargs["connect_args"]["ssl"] is False


def test_migrations_use_separate_url_and_no_pool(settings, monkeypatch) -> None:
    factory = MagicMock()
    monkeypatch.setattr("app.db.create_async_engine", factory)
    settings = config(
        settings,
        migration_database_url=SecretStr(
            "postgresql+asyncpg://owner:private-password@db.project.supabase.co:5432/postgres?sslmode=require"
        ),
    )
    create_engine(settings, migration=True)
    args, kwargs = factory.call_args
    assert args[0].host == "db.project.supabase.co"
    assert kwargs["poolclass"] is NullPool and "pool_size" not in kwargs
    assert isinstance(kwargs["connect_args"]["ssl"], ssl.SSLContext)


def test_custom_ca_certificate_is_loaded(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(
            "postgresql+asyncpg://user:secret@db.project.supabase.co/postgres?sslmode=verify-full&sslrootcert=%2Ftmp%2Fsupabase-ca.crt"
        ),
        jwt_secret="a" * 40,
    )
    factory = MagicMock()
    context = MagicMock()
    monkeypatch.setattr("app.db.create_async_engine", factory)
    ssl_factory = MagicMock(return_value=context)
    monkeypatch.setattr("app.db.ssl.create_default_context", ssl_factory)
    create_engine(settings)
    ssl_factory.assert_called_once_with(cafile="/tmp/supabase-ca.crt")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:secret@host/db",
        "sqlite+aiosqlite:///test.db",
        "postgresql+asyncpg:///missing-host",
        "postgresql+asyncpg://host/",
        "postgresql+asyncpg://user:secret@aws-0.pooler.supabase.com:6543/postgres?sslmode=require",
        "postgresql+asyncpg://user:secret@db.project.supabase.co/postgres",
        "postgresql+asyncpg://host/db?sslmode=prefer",
        "postgresql+asyncpg://host/db?sslrootcert=/tmp/ca",
        "postgresql+asyncpg://host/db?prepared_statement_cache_size=-1",
        "postgresql+asyncpg://host/db?prepared_statement_cache_size=invalid",
        "postgresql+asyncpg://host/db?unknown=option",
    ],
)
def test_invalid_database_urls_are_rejected_and_redacted(settings, url) -> None:
    with pytest.raises(ValidationError) as error:
        config(settings, database_url=SecretStr(url))
    assert "input_value" not in str(error.value)
    assert "user:secret" not in str(error.value)


def test_migration_url_is_validated(settings) -> None:
    with pytest.raises(ValidationError):
        config(settings, migration_database_url=SecretStr("postgresql://host/db"))
    with pytest.raises(ValidationError):
        config(
            settings,
            database_ssl=True,
            database_url=SecretStr("postgresql+asyncpg://host/db?sslmode=disable"),
        )


@pytest.mark.parametrize("url", ["https://redis.example", "redis:///0"])
def test_invalid_redis_url(settings, url) -> None:
    with pytest.raises(ValidationError):
        config(settings, redis_url=SecretStr(url))


@pytest.mark.parametrize(
    "url",
    ["redis://localhost:6379/0", "redis://redis:6379/0", "rediss://:password@cache.example:6380/1"],
)
def test_redis_native_docker_and_tls_urls(settings, url) -> None:
    assert config(settings, redis_url=SecretStr(url)).redis_url.get_secret_value() == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/provider",
        "https:///missing-host",
        "https://user:secret@ce.judge0.com",
        "https://ce.judge0.com?api_key=secret",
        "https://ce.judge0.com/#fragment",
    ],
)
def test_invalid_provider_urls(settings, url) -> None:
    with pytest.raises(ValidationError):
        config(settings, judge0_url=url)


@pytest.mark.parametrize("header", ["X-RapidAPI-Key", "x-rapidapi-host", "Bad\r\nHeader"])
def test_public_provider_rejects_rapidapi_or_invalid_headers(settings, header) -> None:
    with pytest.raises(ValidationError):
        config(settings, judge0_auth_header=header)


def test_statement_cache_option_is_typed_and_removed_from_url() -> None:
    target = database_target("postgresql+asyncpg://host/db?prepared_statement_cache_size=0", False)
    assert target.statement_cache_size == 0 and not target.url.query
