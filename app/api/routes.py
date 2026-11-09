from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.dependencies import Auth, Config, CurrentUser, Session, Submissions
from app.languages import language_metadata
from app.models import Difficulty
from app.repositories import QuestionRepository, SubmissionRepository
from app.schemas import (
    Credentials,
    Data,
    LanguageView,
    LeaderboardEntry,
    MeView,
    Page,
    ProfileUpdate,
    ProgressView,
    QuestionSummary,
    QuestionView,
    RefreshRequest,
    Register,
    RunRequest,
    SampleRunRequest,
    Statistics,
    SubmissionSummary,
    SubmissionView,
    SubmitRequest,
    Tokens,
    UserView,
)
from app.services.profiles import ProfileService
from app.services.questions import QuestionService

router = APIRouter(prefix="/api/v1")
PageNumber = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("/auth/register", response_model=Data[Tokens], status_code=201, tags=["auth"])
async def register(payload: Register, service: Auth) -> Data[Tokens]:
    return Data(data=await service.register(payload))


@router.post("/auth/login", response_model=Data[Tokens], tags=["auth"])
async def login(payload: Credentials, service: Auth) -> Data[Tokens]:
    return Data(data=await service.login(payload))


@router.post("/auth/refresh", response_model=Data[Tokens], tags=["auth"])
async def refresh(payload: RefreshRequest, service: Auth) -> Data[Tokens]:
    return Data(data=await service.refresh(payload.refresh_token.get_secret_value()))


@router.post("/auth/logout", status_code=204, tags=["auth"])
async def logout(payload: RefreshRequest, service: Auth) -> Response:
    await service.logout(payload.refresh_token.get_secret_value())
    return Response(status_code=204)


@router.get("/users/me", response_model=Data[MeView], tags=["users"])
async def me(user: CurrentUser) -> Data[MeView]:
    return Data(data=MeView.model_validate(user))


@router.patch("/users/me", response_model=Data[MeView], tags=["users"])
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: Session
) -> Data[MeView]:
    updated = await ProfileService(session).update(user, payload.bio)
    return Data(data=MeView.model_validate(updated))


@router.get("/users/me/progress", response_model=Page[ProgressView], tags=["users"])
async def progress(
    user: CurrentUser,
    session: Session,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[ProgressView]:
    return await ProfileService(session).progress(user.id, page, page_size)


@router.get("/users/me/statistics", response_model=Data[Statistics], tags=["users"])
async def statistics(user: CurrentUser, session: Session) -> Data[Statistics]:
    return Data(data=await ProfileService(session).stats(user.id))


@router.get("/users/{username}", response_model=Data[UserView], tags=["users"])
async def public_profile(username: str, session: Session) -> Data[UserView]:
    return Data(data=await ProfileService(session).public(username))


@router.get("/questions", response_model=Page[QuestionSummary], tags=["questions"])
async def questions(
    session: Session,
    settings: Config,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    difficulty: Difficulty | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    topic: Annotated[
        str | None, Query(max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    ] = None,
) -> Page[QuestionSummary]:
    return await QuestionService(QuestionRepository(session), settings).list(
        page,
        page_size,
        difficulty,
        search,
        topic,
    )


@router.get("/questions/{question_id}", response_model=Data[QuestionView], tags=["questions"])
async def question(question_id: UUID, session: Session, settings: Config) -> Data[QuestionView]:
    return Data(
        data=await QuestionService(QuestionRepository(session), settings).detail(question_id)
    )


@router.get("/languages", response_model=Data[list[LanguageView]], tags=["execution"])
async def languages(service: Submissions) -> Data[list[LanguageView]]:
    return Data(data=[language_metadata(r) for r in await service.provider.languages()])


@router.post(
    "/submissions", response_model=Data[SubmissionSummary], status_code=202, tags=["execution"]
)
async def submit(
    payload: SubmitRequest, user: CurrentUser, service: Submissions
) -> Data[SubmissionSummary]:
    row = await service.create(user.id, payload)
    return Data(data=SubmissionSummary.model_validate(row))


@router.post("/runs", response_model=Data[SubmissionSummary], status_code=202, tags=["execution"])
async def run(
    payload: RunRequest, user: CurrentUser, service: Submissions
) -> Data[SubmissionSummary]:
    row = await service.create(user.id, payload)
    return Data(data=SubmissionSummary.model_validate(row))


@router.post(
    "/questions/{question_id}/runs",
    response_model=Data[SubmissionSummary],
    status_code=202,
    tags=["execution"],
    summary="Run question samples or custom cases without awarding graded credit",
)
async def run_question_samples(
    question_id: UUID, payload: SampleRunRequest, user: CurrentUser, service: Submissions
) -> Data[SubmissionSummary]:
    row = await service.run_samples(user.id, question_id, payload)
    return Data(data=SubmissionSummary.model_validate(row))


@router.get("/submissions", response_model=Page[SubmissionSummary], tags=["execution"])
async def submission_list(
    user: CurrentUser,
    session: Session,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    question_id: UUID | None = None,
) -> Page[SubmissionSummary]:
    rows, total = await SubmissionRepository(session).list_submissions(
        user.id, page, page_size, question_id
    )
    return Page(
        data=[SubmissionSummary.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/submissions/{submission_id}", response_model=Data[SubmissionView], tags=["execution"])
async def submission_detail(
    submission_id: UUID,
    user: CurrentUser,
    service: Submissions,
) -> Data[SubmissionView]:
    return Data(data=await service.detail(submission_id, user.id))


@router.get("/leaderboard", response_model=Page[LeaderboardEntry], tags=["users"])
async def leaderboard(
    session: Session,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> Page[LeaderboardEntry]:
    return await ProfileService(session).leaderboard(page, page_size)
