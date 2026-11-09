from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    access_token,
    decode_access,
    new_refresh_token,
    password_hasher,
    token_hash,
)
from app.schemas import Register, RunRequest, SubmitRequest


def test_argon2_and_refresh_secrets() -> None:
    digest = password_hasher.hash("correct-horse-battery-staple")
    assert digest.startswith("$argon2id$")
    assert password_hasher.verify("correct-horse-battery-staple", digest)
    assert not password_hasher.verify("wrong", digest)
    token = new_refresh_token()
    assert len(token) >= 40 and token_hash(token) != token
    assert new_refresh_token() != token


def test_access_roundtrip(settings) -> None:
    user_id = uuid4()
    assert decode_access(access_token(user_id, settings), settings) == user_id


@pytest.mark.parametrize(
    "mutation", ["expiry", "audience", "issuer", "type", "subject", "signature", "missing"]
)
def test_invalid_access(settings, mutation) -> None:
    token = access_token(uuid4(), settings)
    payload = jwt.decode(token, options={"verify_signature": False})
    if mutation == "expiry":
        payload["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    elif mutation == "audience":
        payload["aud"] = "other"
    elif mutation == "issuer":
        payload["iss"] = "other"
    elif mutation == "type":
        payload["type"] = "refresh"
    elif mutation == "subject":
        payload["sub"] = "not-a-uuid"
    elif mutation == "missing":
        del payload["jti"]
    secret = "x" * 40 if mutation == "signature" else settings.jwt_secret.get_secret_value()
    with pytest.raises(AppError) as error:
        decode_access(jwt.encode(payload, secret, algorithm="HS256"), settings)
    assert error.value.status == 401


def test_configuration_rejects_insecure_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///test", jwt_secret="short")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://host/db",
            jwt_secret="a" * 40,
            environment="production",
            database_ssl=True,
            cors_origins=["*"],
        )


def test_validation_and_normalization() -> None:
    result = Register(email="TEST@example.com", username="Coder", password="a" * 12)
    assert result.email == "test@example.com" and result.username == "coder"
    assert "aaaaaaaaaaaa" not in repr(result)
    with pytest.raises(ValidationError):
        SubmitRequest(question_id=uuid4(), language="python", source_code="a", cpu_seconds=999)
    for source in (" ", "a\0", "😎" * 20000, "\ud800"):
        with pytest.raises(ValidationError):
            RunRequest(language="python", source_code=source)
    for stdin in ("\0", "\ud800", "😎" * 5000):
        with pytest.raises(ValidationError):
            RunRequest(language="python", source_code="print(1)", stdin=stdin)
