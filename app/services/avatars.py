import asyncio
import io
import logging
import re
import warnings
from uuid import UUID, uuid4

from anyio import CapacityLimiter, to_thread
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models import User

logger = logging.getLogger(__name__)
FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}


def normalized_avatar(data: bytes, content_type: str) -> bytes:
    kind = FORMATS.get(content_type)
    if kind is None:
        raise AppError("unsupported_avatar_type", "Use a PNG, JPEG, or WebP image", 415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[kind]) as image:
                if image.width * image.height > 4_000_000 or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unsupported dimensions or animation")
                image.verify()
            with Image.open(io.BytesIO(data), formats=[kind]) as image:
                image.load()
                image.thumbnail((256, 256))
                # Fresh pixel image discards metadata, embedded profiles and trailing payloads.
                clean = Image.new("RGBA", image.size)
                clean.paste(image.convert("RGBA"))
                result = io.BytesIO()
                clean.save(result, format="PNG")
                return result.getvalue()
    except (
        ValueError,
        SyntaxError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise AppError(
            "invalid_avatar", "Image is invalid, animated, or exceeds 4 megapixels", 422
        ) from None


class AvatarService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        image_limiter: CapacityLimiter | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.image_limiter = image_limiter

    async def remove_file(self, key: str | None) -> None:
        if key:
            try:
                await asyncio.to_thread(
                    (self.settings.avatar_storage_dir / key).unlink, missing_ok=True
                )
            except OSError:
                logger.warning("Unused avatar cleanup failed")

    async def update(self, user_id: UUID, data: bytes | None, content_type: str = "") -> User:
        normalized = None
        if data is not None:
            if len(data) > self.settings.avatar_max_bytes:
                raise AppError("body_too_large", "Avatar exceeds the upload limit", 413)
            normalized = await to_thread.run_sync(
                normalized_avatar, data, content_type, limiter=self.image_limiter
            )
        user = await self.session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert user is not None
        old_key = user.avatar_key
        new_key = uuid4().hex + ".png" if normalized is not None else None
        if new_key and normalized is not None:

            def store() -> None:
                root = self.settings.avatar_storage_dir
                root.mkdir(parents=True, exist_ok=True)
                target = root / new_key
                temporary = root / (new_key + ".tmp")
                try:
                    temporary.write_bytes(normalized)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)

            await asyncio.to_thread(store)
        user.avatar_key = new_key
        try:
            await self.session.commit()
        except Exception:
            await self.remove_file(new_key)
            raise
        await self.remove_file(old_key)
        return user

    async def read(self, key: str) -> bytes:
        if not re.fullmatch(r"[a-f0-9]{32}\.png", key):
            raise AppError("not_found", "Avatar not found", 404)
        owner = await self.session.scalar(
            select(User.id).where(User.avatar_key == key, User.is_active.is_(True))
        )
        if owner is None:
            raise AppError("not_found", "Avatar not found", 404)
        try:
            return await asyncio.to_thread((self.settings.avatar_storage_dir / key).read_bytes)
        except FileNotFoundError:
            raise AppError("not_found", "Avatar not found", 404) from None
