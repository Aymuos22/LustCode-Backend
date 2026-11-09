from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.dependencies import Config, CurrentUser, OptionalUser, Session
from app.models import Difficulty, Language
from app.schemas import (
    CollectionDetail,
    CollectionView,
    Data,
    DraftView,
    DraftWrite,
    EditorPreferences,
    FeaturedQuestions,
    MeView,
    Page,
    PreferencesPatch,
    QuestionNavigation,
    QuestionSummary,
    TopicView,
)
from app.services.avatars import AvatarService
from app.services.catalog import CatalogService
from app.services.workspaces import WorkspaceService

router = APIRouter(prefix="/api/v1")
PageNumber = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Topic = Annotated[str | None, Query(max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
Search = Annotated[str | None, Query(max_length=100)]


@router.get("/topics", response_model=Data[list[TopicView]], tags=["questions"])
async def topics(session: Session, settings: Config) -> Data[list[TopicView]]:
    return Data(data=await CatalogService(session, settings).topics())


@router.get("/questions/featured", response_model=Data[FeaturedQuestions], tags=["questions"])
async def featured(
    session: Session, settings: Config, limit: Annotated[int, Query(ge=1, le=20)] = 6
) -> Data[FeaturedQuestions]:
    return Data(data=await CatalogService(session, settings).featured(limit))


@router.get("/questions/random", response_model=Data[QuestionSummary], tags=["questions"])
async def random_question(
    session: Session,
    settings: Config,
    difficulty: Difficulty | None = None,
    search: Search = None,
    topic: Topic = None,
) -> Data[QuestionSummary]:
    return Data(data=await CatalogService(session, settings).random(difficulty, search, topic))


@router.get(
    "/questions/{question_id}/navigation",
    response_model=Data[QuestionNavigation],
    tags=["questions"],
)
async def navigation(
    question_id: UUID,
    session: Session,
    settings: Config,
    difficulty: Difficulty | None = None,
    search: Search = None,
    topic: Topic = None,
) -> Data[QuestionNavigation]:
    return Data(
        data=await CatalogService(session, settings).navigation(
            question_id, difficulty, search, topic
        )
    )


@router.get("/collections", response_model=Page[CollectionView], tags=["collections"])
async def collections(
    session: Session,
    settings: Config,
    user: OptionalUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[CollectionView]:
    return await CatalogService(session, settings).collections(
        user.id if user else None, page, page_size
    )


@router.get(
    "/collections/{collection_id}", response_model=Data[CollectionDetail], tags=["collections"]
)
async def collection(
    collection_id: UUID,
    session: Session,
    settings: Config,
    user: OptionalUser,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    topic: Topic = None,
    search: Search = None,
) -> Data[CollectionDetail]:
    return Data(
        data=await CatalogService(session, settings).collection(
            collection_id, user.id if user else None, page, page_size, topic, search
        )
    )


@router.get(
    "/users/me/drafts/{workspace}/{language}", response_model=Data[DraftView], tags=["drafts"]
)
async def draft(
    workspace: str, language: Language, user: CurrentUser, session: Session
) -> Data[DraftView]:
    return Data(data=await WorkspaceService(session).draft(user.id, workspace, language))


@router.put(
    "/users/me/drafts/{workspace}/{language}", response_model=Data[DraftView], tags=["drafts"]
)
async def write_draft(
    workspace: str, language: Language, payload: DraftWrite, user: CurrentUser, session: Session
) -> Data[DraftView]:
    return Data(
        data=await WorkspaceService(session).write(
            user.id, workspace, language, payload.revision, payload
        )
    )


@router.delete(
    "/users/me/drafts/{workspace}/{language}", response_model=Data[DraftView], tags=["drafts"]
)
async def delete_draft(
    workspace: str,
    language: Language,
    user: CurrentUser,
    session: Session,
    revision: Annotated[int, Query(ge=0, le=2147483646)],
) -> Data[DraftView]:
    return Data(
        data=await WorkspaceService(session).write(user.id, workspace, language, revision, None)
    )


@router.get("/users/me/preferences", response_model=Data[EditorPreferences], tags=["preferences"])
async def preferences(
    request: Request, user: CurrentUser, session: Session
) -> Data[EditorPreferences]:
    return Data(
        data=await WorkspaceService(session).preferences(user, None, request.app.state.provider)
    )


@router.patch("/users/me/preferences", response_model=Data[EditorPreferences], tags=["preferences"])
async def update_preferences(
    payload: PreferencesPatch, request: Request, user: CurrentUser, session: Session
) -> Data[EditorPreferences]:
    return Data(
        data=await WorkspaceService(session).preferences(user, payload, request.app.state.provider)
    )


@router.put(
    "/users/me/avatar",
    response_model=Data[MeView],
    tags=["avatars"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                kind: {"schema": {"type": "string", "format": "binary"}}
                for kind in ["image/png", "image/jpeg", "image/webp"]
            },
        }
    },
)
async def upload_avatar(
    request: Request, user: CurrentUser, session: Session, settings: Config
) -> Data[MeView]:
    updated = await AvatarService(session, settings, request.app.state.avatar_limiter).update(
        user.id,
        await request.body(),
        request.headers.get("content-type", "").split(";")[0].strip().lower(),
    )
    return Data(data=MeView.model_validate(updated))


@router.delete("/users/me/avatar", response_model=Data[MeView], tags=["avatars"])
async def delete_avatar(user: CurrentUser, session: Session, settings: Config) -> Data[MeView]:
    return Data(
        data=MeView.model_validate(await AvatarService(session, settings).update(user.id, None))
    )


@router.get(
    "/avatars/{key}",
    tags=["avatars"],
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def avatar(key: str, session: Session, settings: Config) -> Response:
    return Response(await AvatarService(session, settings).read(key), media_type="image/png")
