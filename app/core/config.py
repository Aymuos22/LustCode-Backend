from ipaddress import ip_network
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_config import database_target


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    migration_database_url: SecretStr | None = None
    database_ssl: bool = False
    database_ssl_root_cert: Path | None = None
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=10, ge=1, le=60)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60)
    database_connect_timeout_seconds: float = Field(default=5, ge=1, le=30)
    database_command_timeout_seconds: float = Field(default=30, ge=1, le=120)
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    redis_connect_timeout_seconds: float = Field(default=2, ge=0.1, le=10)
    redis_socket_timeout_seconds: float = Field(default=3, ge=3, le=30)
    readiness_timeout_seconds: float = Field(default=2, ge=0.1, le=10)
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str = "lustcode"
    jwt_audience: str = "lustcode-api"
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_allow_all_origins: bool = False
    trusted_proxy_networks: list[str] = []
    trusted_client_ip_header: Literal["x-forwarded-for", "cf-connecting-ip"] = "x-forwarded-for"
    password_hash_concurrency: int = Field(default=2, ge=1, le=8)
    avatar_processing_concurrency: int = Field(default=2, ge=1, le=8)
    judge0_url: str = "https://ce.judge0.com"
    judge0_auth_token: SecretStr | None = None
    judge0_auth_header: str = "X-Auth-Token"
    judge0_max_connections: int = Field(default=20, ge=1, le=100)
    judge0_max_keepalive_connections: int = Field(default=10, ge=0, le=100)
    judge0_timeout_seconds: float = Field(default=10, ge=1, le=30)
    judge0_poll_seconds: float = Field(default=0.5, ge=0.1, le=5)
    judge0_poll_timeout_seconds: float = Field(default=60, ge=1, le=90)
    judge0_response_bytes: int = Field(default=1_000_000, ge=1024)
    request_max_bytes: int = Field(default=131_072, ge=1024)
    rate_requests_per_minute: int = Field(default=120, ge=1)
    auth_requests_per_minute: int = Field(default=10, ge=1)
    daily_submissions: int = Field(default=100, ge=1)
    daily_test_executions: int = Field(default=1000, ge=1)
    max_pending_submissions: int = Field(default=5, ge=1)
    max_test_cases: int = Field(default=100, ge=1, le=1000)
    max_cpu_seconds: float = Field(default=5, ge=0.1, le=15)
    max_memory_kb: int = Field(default=262144, ge=16384, le=524288)
    worker_lease_seconds: int = Field(default=180, ge=150)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    embedded_worker_enabled: bool = False
    embedded_worker_shutdown_seconds: float = Field(default=10, ge=0.01, le=20)
    avatar_storage_dir: Path = Path("var/avatars")
    avatar_max_bytes: int = Field(default=262144, ge=1024, le=2097152)

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        targets = [database_target(self.database_url.get_secret_value(), self.database_ssl)]
        if self.migration_database_url:
            targets.append(
                database_target(self.migration_database_url.get_secret_value(), self.database_ssl)
            )
        redis = urlsplit(self.redis_url.get_secret_value())
        if redis.scheme not in ("redis", "rediss") or not redis.hostname:
            raise ValueError("REDIS_URL requires a redis:// or rediss:// host URL")
        if self.cors_allow_all_origins:
            self.cors_origins = ["*"]
        elif "*" in self.cors_origins:
            raise ValueError("Explicit CORS origins are required")
        for value in self.trusted_proxy_networks:
            network = ip_network(value)
            if network.prefixlen == 0:
                raise ValueError("Trust specific proxy networks, never the entire internet")
        if self.environment == "production":
            if any(not target.tls for target in targets):
                raise ValueError("Production database connections require TLS")
            if not self.cors_allow_all_origins and any(
                not origin.startswith("https://") for origin in self.cors_origins
            ):
                raise ValueError("Production CORS origins must use HTTPS")
        judge = urlsplit(self.judge0_url)
        if judge.scheme not in ("http", "https") or not judge.hostname:
            raise ValueError("JUDGE0_URL requires an HTTP(S) host URL")
        if judge.username or judge.password or judge.query or judge.fragment:
            raise ValueError(
                "JUDGE0_URL must not contain credentials, query parameters, or fragments"
            )
        if not self.judge0_auth_header or any(
            char
            not in "!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for char in self.judge0_auth_header
        ):
            raise ValueError("Invalid Judge0 authentication header name")
        if judge.hostname.lower() == "ce.judge0.com" and self.judge0_auth_header.lower().startswith(
            "x-rapidapi-"
        ):
            raise ValueError(
                "RapidAPI authentication headers must not be used with public Judge0 CE"
            )
        if self.judge0_max_keepalive_connections > self.judge0_max_connections:
            raise ValueError("Judge0 keepalive connections cannot exceed maximum connections")
        return self
