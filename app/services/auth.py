from datetime import UTC, datetime, timedelta
from uuid import UUID

from anyio import CapacityLimiter, to_thread
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import access_token, new_refresh_token, password_hasher, token_hash
from app.models import RefreshToken, User
from app.repositories import AuthRepository
from app.schemas import Credentials, Register, Tokens


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        dummy_hash: str,
        limiter: CapacityLimiter | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.repo = AuthRepository(session)
        self.dummy_hash = dummy_hash
        self.limiter = limiter

    def issue(self, user_id: UUID, family_id: UUID | None = None) -> Tokens:
        raw = new_refresh_token()
        values = {
            "user_id": user_id,
            "token_hash": token_hash(raw),
            "expires_at": datetime.now(UTC) + timedelta(days=self.settings.refresh_token_days),
        }
        if family_id:
            values["family_id"] = family_id
        self.session.add(RefreshToken(**values))
        return Tokens(
            access_token=access_token(user_id, self.settings),
            refresh_token=raw,
            expires_in=self.settings.access_token_minutes * 60,
        )

    async def register(self, payload: Register) -> Tokens:
        digest = await to_thread.run_sync(
            password_hasher.hash, payload.password.get_secret_value(), limiter=self.limiter
        )
        user = User(email=str(payload.email), username=payload.username, password_hash=digest)
        self.session.add(user)
        try:
            await self.session.flush()
            result = self.issue(user.id)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "account_exists", "Email or username is already registered", 409
            ) from exc
        return result

    async def login(self, payload: Credentials) -> Tokens:
        user = await self.repo.user_by_email(str(payload.email))
        valid = await to_thread.run_sync(
            password_hasher.verify,
            payload.password.get_secret_value(),
            user.password_hash if user else self.dummy_hash,
            limiter=self.limiter,
        )
        if not valid or user is None or not user.is_active:
            raise AppError("unauthorized", "Invalid email or password", 401)
        result = self.issue(user.id)
        await self.session.commit()
        return result

    async def refresh(self, raw: str) -> Tokens:
        row = await self.repo.refresh_for_update(token_hash(raw))
        if row is None:
            raise AppError("unauthorized", "Invalid refresh token", 401)
        if row.revoked_at is not None:
            await self.repo.revoke_family(row.family_id)
            await self.session.commit()
            raise AppError("refresh_reuse", "Refresh token was reused; log in again", 401)
        user = await self.session.get(User, row.user_id)
        if row.expires_at <= datetime.now(UTC) or user is None or not user.is_active:
            raise AppError("unauthorized", "Expired or invalid refresh token", 401)
        row.revoked_at = datetime.now(UTC)
        result = self.issue(row.user_id, row.family_id)
        await self.session.commit()
        return result

    async def logout(self, raw: str) -> None:
        row = await self.repo.refresh_for_update(token_hash(raw))
        if row:
            await self.repo.revoke_family(row.family_id)
            await self.session.commit()
