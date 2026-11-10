from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import decode_access
from app.db import session_dependency
from app.integrations.redis import Limits
from app.models import User
from app.services.auth import AuthService
from app.services.submissions import SubmissionService

Session = Annotated[AsyncSession, Depends(session_dependency)]
bearer = HTTPBearer(auto_error=False)


def settings_dependency(request: Request) -> Settings:
    return request.app.state.settings


Config = Annotated[Settings, Depends(settings_dependency)]


async def current_user(
    request: Request,
    session: Session,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise AppError("unauthorized", "Bearer access token required", 401)
    user_id = decode_access(credentials.credentials, request.app.state.settings)
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("unauthorized", "Account is unavailable", 401)
    await Limits(request.app.state.redis, request.app.state.settings).rate(f"user:{user_id}")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def fulfillment_staff(user: CurrentUser) -> User:
    if not user.is_staff:
        raise AppError("forbidden", "Fulfillment staff access required", 403)
    return user


CurrentStaff = Annotated[User, Depends(fulfillment_staff)]


async def optional_user(
    request: Request,
    session: Session,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User | None:
    if credentials is None and request.headers.get("authorization"):
        raise AppError("unauthorized", "Invalid authorization header", 401)
    return await current_user(request, session, credentials) if credentials else None


OptionalUser = Annotated[User | None, Depends(optional_user)]


def auth_service(request: Request, session: Session, settings: Config) -> AuthService:
    return AuthService(
        session, settings, request.app.state.dummy_hash, request.app.state.password_limiter
    )


Auth = Annotated[AuthService, Depends(auth_service)]


def submission_service(request: Request, session: Session, settings: Config) -> SubmissionService:
    return SubmissionService(
        session,
        request.app.state.provider,
        Limits(request.app.state.redis, settings),
        settings,
        request.app.state.redis,
    )


Submissions = Annotated[SubmissionService, Depends(submission_service)]
