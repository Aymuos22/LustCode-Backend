from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.judge0 import ExecutionProvider
from app.models import Language, User, WorkspaceDraft, utcnow
from app.repositories import QuestionRepository
from app.schemas import DraftView, DraftWrite, EditorPreferences, PreferencesPatch


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def workspace(self, value: str) -> tuple[str, UUID | None]:
        if value == "playground":
            return value, None
        try:
            question_id = UUID(value)
        except ValueError:
            raise AppError(
                "invalid_workspace", "Workspace must be playground or a question UUID", 422
            ) from None
        await QuestionRepository(self.session).published(question_id)
        return str(question_id), question_id

    async def draft(self, user_id: UUID, workspace: str, language: Language) -> DraftView:
        key, question_id = await self.workspace(workspace)
        row = await self.session.scalar(
            select(WorkspaceDraft).where(
                WorkspaceDraft.user_id == user_id,
                WorkspaceDraft.workspace == key,
                WorkspaceDraft.language == language,
            )
        )
        return self.view(row, key, question_id, language)

    @staticmethod
    def view(
        row: WorkspaceDraft | None, key: str, question_id: UUID | None, language: Language
    ) -> DraftView:
        if row is None:
            return DraftView(workspace=key, question_id=question_id, language=language)
        return DraftView(
            workspace=key,
            question_id=question_id,
            language=language,
            source_code=row.source_code,
            stdin=row.stdin,
            revision=row.revision,
            updated_at=row.updated_at,
            exists=not row.deleted,
        )

    async def write(
        self,
        user_id: UUID,
        workspace: str,
        language: Language,
        revision: int,
        payload: DraftWrite | None,
    ) -> DraftView:
        key, question_id = await self.workspace(workspace)
        if question_id is not None and payload and payload.stdin is not None:
            raise AppError("invalid_draft", "stdin is supported only for Playground drafts", 422)
        # Serializes absent-row creation as well as edits/deletion; tombstones prevent ABA resets.
        await self.session.scalar(select(User.id).where(User.id == user_id).with_for_update())
        row = await self.session.scalar(
            select(WorkspaceDraft)
            .where(
                WorkspaceDraft.user_id == user_id,
                WorkspaceDraft.workspace == key,
                WorkspaceDraft.language == language,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current = row.revision if row else 0
        if current != revision:
            raise AppError(
                "draft_conflict",
                "Draft changed on another device; read it before saving",
                409,
                current_revision=current,
            )
        if row is None:
            row = WorkspaceDraft(
                user_id=user_id, workspace=key, question_id=question_id, language=language
            )
            self.session.add(row)
        row.revision = current + 1
        row.updated_at = utcnow()
        row.deleted = payload is None
        row.source_code = payload.source_code if payload else None
        row.stdin = payload.stdin if payload else None
        await self.session.commit()
        return self.view(row, key, question_id, language)

    async def preferences(
        self, user: User, payload: PreferencesPatch | None, provider: ExecutionProvider
    ) -> EditorPreferences:
        if payload is None:
            return EditorPreferences.model_validate(user.preferences)
        locked = await self.session.scalar(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert locked is not None
        updates = payload.model_dump(exclude_unset=True)
        if "preferred_language" in updates and "preferred_runtime_id" not in updates:
            if updates["preferred_language"] != locked.preferences.get(
                "preferred_language", "python"
            ):
                updates["preferred_runtime_id"] = None
        merged = EditorPreferences.model_validate({**locked.preferences, **updates})
        if merged.preferred_runtime_id is not None and (
            "preferred_runtime_id" in updates or "preferred_language" in updates
        ):
            if not any(
                r.id == merged.preferred_runtime_id and r.language == merged.preferred_language
                for r in await provider.languages()
            ):
                raise AppError(
                    "language_unavailable",
                    "Preferred runtime is not available for this language",
                    422,
                )
        locked.preferences = merged.model_dump(mode="json")
        await self.session.commit()
        return merged
