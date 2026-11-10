import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.errors import LeaseLost
from app.integrations.judge0 import ExecutionResult
from app.models import (
    CoinTransaction,
    DailyChallenge,
    Difficulty,
    Language,
    Question,
    Submission,
    SubmissionMode,
    SubmissionTestResult,
    UserProgress,
    Verdict,
)
from app.models import TestCase as Case
from app.repositories import SubmissionRepository
from app.services.coins import CoinService
from app.services.daily import DailyProblemService
from app.services.profiles import longest_streak
from app.worker import EvaluationWorker
from tests.test_integration import auth, register, submit
from tests.test_integration import question_id as question_id
from tests.test_sample_runs import sample_question as sample_question

pytestmark = pytest.mark.integration


async def balance(api, headers):
    response = await api.get("/api/v1/users/me/coins", headers=headers)
    assert response.status_code == 200
    return response.json()["data"]["balance"]


async def test_existing_statistics_and_dedicated_empty_streak(api):
    headers = auth(await register(api))
    stats = (await api.get("/api/v1/users/me/statistics", headers=headers)).json()["data"]
    streak = (await api.get("/api/v1/users/me/streak", headers=headers)).json()["data"]
    assert streak["current_streak"] == stats["current_streak"] == 0
    assert streak["longest_streak"] == 0
    assert streak["basis"] == "graded_submission_activity" and streak["timezone"] == "UTC"
    assert not streak["active_today"] and streak["last_activity_date"] is None
    assert streak["daily_activity"] == {}


async def test_checkin_is_idempotent_owned_and_survives_redis_reset(api, redis):
    owner = auth(await register(api))
    other = auth(await register(api, "other"))
    assert await balance(api, owner) == await balance(api, other) == 0
    response = await api.post("/api/v1/users/me/coins/check-in", headers=owner)
    assert response.status_code == 200
    first = response.json()["data"]
    assert first["awarded"] and first["credited_amount"] == 5
    assert first["wallet"]["balance"] == 5 and first["wallet"]["check_in_claimed_today"]
    repeated = (await api.post("/api/v1/users/me/coins/check-in", headers=owner, json={})).json()[
        "data"
    ]
    assert not repeated["awarded"] and repeated["credited_amount"] == 0
    assert repeated["transaction"]["id"] == first["transaction"]["id"]
    await redis.flushall()
    assert await balance(api, owner) == 5 and await balance(api, other) == 0
    history = (await api.get("/api/v1/users/me/coins/transactions", headers=owner)).json()
    assert history["total"] == 1 and history["data"][0]["reason"] == "daily_check_in"
    assert "event_key" not in history["data"][0]
    assert (await api.get("/api/v1/users/me/coins/transactions", headers=other)).json()[
        "total"
    ] == 0


async def test_parallel_checkins_grant_one_credit(api, sessions):
    headers = auth(await register(api))
    responses = await asyncio.gather(
        *[api.post("/api/v1/users/me/coins/check-in", headers=headers) for _ in range(12)]
    )
    assert all(r.status_code == 200 for r in responses)
    assert sum(r.json()["data"]["credited_amount"] for r in responses) == 5
    assert len({r.json()["data"]["transaction"]["id"] for r in responses}) == 1
    assert await balance(api, headers) == 5
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CoinTransaction)) == 1


@pytest.mark.parametrize(
    "payload", [{"amount": 50000}, {"date": "2000-01-01"}, {"user_id": "other"}]
)
async def test_client_cannot_set_coin_amount_date_or_owner(api, payload):
    headers = auth(await register(api))
    response = await api.post("/api/v1/users/me/coins/check-in", headers=headers, json=payload)
    assert response.status_code == 422 and await balance(api, headers) == 0


async def test_checkin_changes_at_utc_midnight(api, monkeypatch):
    class Clock(datetime):
        value = datetime(2026, 11, 10, 23, 59, 59, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.value.astimezone(tz) if tz else cls.value.replace(tzinfo=None)

    monkeypatch.setattr("app.services.coins.datetime", Clock)
    headers = auth(await register(api))
    first = (await api.post("/api/v1/users/me/coins/check-in", headers=headers)).json()["data"]
    assert first["transaction"]["reward_date"] == "2026-11-10"
    assert first["wallet"]["next_reset_at"].startswith("2026-11-11T00:00:00")
    Clock.value += timedelta(seconds=1)
    second = (await api.post("/api/v1/users/me/coins/check-in", headers=headers)).json()["data"]
    assert second["transaction"]["reward_date"] == "2026-11-11"
    assert second["credited_amount"] == 5 and second["wallet"]["balance"] == 10


async def test_daily_problem_is_public_persisted_and_shared(api, sessions, question_id):
    responses = await asyncio.gather(*[api.get("/api/v1/questions/daily") for _ in range(8)])
    assert all(r.status_code == 200 for r in responses)
    values = [r.json()["data"] for r in responses]
    assert all(v["question"]["id"] == str(question_id) for v in values)
    assert all(v["question"]["is_judgeable"] and v["completed"] is None for v in values)
    assert all(v["reward_coins"] == 20 and v["timezone"] == "UTC" for v in values)
    assert "statement" not in values[0]["question"]
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(DailyChallenge)) == 1
        q = Question(
            slug="later",
            title="Later",
            statement="Fixture",
            difficulty=Difficulty.HARD,
            published=True,
        )
        session.add(q)
        await session.flush()
        session.add(
            Case(question_id=q.id, position=0, stdin="", expected_output="ok", hidden=False)
        )
        await session.commit()
    assert (await api.get("/api/v1/questions/daily")).json()["data"]["question"]["id"] == str(
        question_id
    )


async def test_daily_problem_empty_or_unsupported_catalog(api, sessions):
    assert (await api.get("/api/v1/questions/daily")).status_code == 404
    async with sessions() as session:
        q = Question(
            slug="sql",
            title="SQL fixture",
            statement="Fixture",
            difficulty=Difficulty.EASY,
            published=True,
            content={"supported_languages": []},
        )
        session.add(q)
        await session.flush()
        session.add(
            Case(question_id=q.id, position=0, stdin="", expected_output="ok", hidden=False)
        )
        await session.commit()
    assert (await api.get("/api/v1/questions/daily")).status_code == 404


async def test_daily_rotation_rolls_to_a_different_problem(sessions, settings, question_id):
    async with sessions() as session:
        q = Question(
            slug="second",
            title="Second",
            statement="Fixture",
            difficulty=Difficulty.EASY,
            published=True,
        )
        session.add(q)
        await session.flush()
        session.add(
            Case(question_id=q.id, position=0, stdin="", expected_output="ok", hidden=False)
        )
        await session.commit()
        service = DailyProblemService(session, settings)
        first = await service.ensure(date(2026, 11, 10))
        second = await service.ensure(date(2026, 11, 11))
        assert first.question_id != second.question_id
        await session.commit()


async def test_accepted_potd_awards_once_across_languages(
    api, sessions, provider, settings, question_id
):
    headers = auth(await register(api))
    assert not (await api.get("/api/v1/questions/daily", headers=headers)).json()["data"][
        "completed"
    ]
    for language in ["python", "java", "cpp"]:
        response = await api.post(
            "/api/v1/submissions",
            headers=headers,
            json={"question_id": str(question_id), "language": language, "source_code": "fixture"},
        )
        assert response.status_code == 202
        assert await EvaluationWorker(sessions, provider, settings).once()
        assert await balance(api, headers) == 20
    daily = (await api.get("/api/v1/questions/daily", headers=headers)).json()["data"]
    assert daily["completed"] and daily["reward_claimed"]
    history = (await api.get("/api/v1/users/me/coins/transactions", headers=headers)).json()
    assert history["total"] == 1 and history["data"][0]["question_id"] == str(question_id)
    await api.post("/api/v1/users/me/coins/check-in", headers=headers)
    assert await balance(api, headers) == 25


@pytest.mark.parametrize(
    "status",
    [
        Verdict.WRONG_ANSWER,
        Verdict.COMPILATION_ERROR,
        Verdict.RUNTIME_ERROR,
        Verdict.PROVIDER_ERROR,
    ],
)
async def test_failed_submissions_never_earn_potd(
    api, sessions, provider, settings, question_id, status
):
    headers = auth(await register(api))
    await submit(
        api, {"access_token": headers["Authorization"].removeprefix("Bearer ")}, question_id
    )
    provider.results = [ExecutionResult(status=status)] * 2
    assert await EvaluationWorker(sessions, provider, settings).once()
    assert await balance(api, headers) == 0


async def test_runs_and_non_daily_solves_do_not_earn_coins(
    api, sessions, provider, settings, question_id
):
    headers = auth(await register(api))
    await api.get("/api/v1/questions/daily")
    r = await api.post(
        f"/api/v1/questions/{question_id}/runs",
        headers=headers,
        json={"language": "python", "source_code": "fixture"},
    )
    assert r.status_code == 202 and await EvaluationWorker(sessions, provider, settings).once()
    assert await balance(api, headers) == 0
    async with sessions() as session:
        other = Question(
            slug="other",
            title="Other",
            statement="Fixture",
            difficulty=Difficulty.EASY,
            published=True,
        )
        session.add(other)
        await session.flush()
        session.add(
            Case(question_id=other.id, position=0, stdin="", expected_output="ok", hidden=False)
        )
        await session.commit()
    r = await api.post(
        "/api/v1/submissions",
        headers=headers,
        json={"question_id": str(other.id), "language": "python", "source_code": "fixture"},
    )
    assert r.status_code == 202 and await EvaluationWorker(sessions, provider, settings).once()
    assert await balance(api, headers) == 0


async def test_midnight_queue_delay_uses_submission_day(
    api, sessions, provider, settings, question_id
):
    headers = auth(await register(api))
    response = await api.post(
        "/api/v1/submissions",
        headers=headers,
        json={"question_id": str(question_id), "language": "python", "source_code": "fixture"},
    )
    identifier = UUID(response.json()["data"]["id"])
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    async with sessions() as session:
        await DailyProblemService(session, settings).ensure(yesterday)
        row = await session.get(Submission, identifier)
        row.created_at = datetime.combine(yesterday, datetime.min.time(), tzinfo=UTC) + timedelta(
            hours=23, minutes=59
        )
        row.daily_challenge_date = yesterday
        await session.commit()
    assert await EvaluationWorker(sessions, provider, settings).once()
    history = (await api.get("/api/v1/users/me/coins/transactions", headers=headers)).json()
    assert history["total"] == 1 and history["data"][0]["reward_date"] == yesterday.isoformat()
    assert await balance(api, headers) == 20


async def test_parallel_finish_and_retry_cannot_duplicate_potd_credit(
    api, sessions, provider, settings, question_id
):
    headers = auth(await register(api))
    for _ in range(2):
        await api.post(
            "/api/v1/submissions",
            headers=headers,
            json={"question_id": str(question_id), "language": "python", "source_code": "fixture"},
        )
    claimed = []
    for _ in range(2):
        async with sessions() as session:
            claimed.append(await SubmissionRepository(session).claim(settings))
    async with sessions() as session:
        await session.execute(update(SubmissionTestResult).values(status=Verdict.ACCEPTED))
        await session.commit()
    worker = EvaluationWorker(sessions, provider, settings)
    await asyncio.wait_for(
        asyncio.gather(*[worker.finish(row.id, row.lease_id) for row in claimed]), timeout=5
    )
    assert await balance(api, headers) == 20
    with pytest.raises(LeaseLost):
        await worker.finish(claimed[0].id, claimed[0].lease_id)
    assert (await api.get("/api/v1/users/me/coins/transactions", headers=headers)).json()[
        "total"
    ] == 1


async def test_credit_and_solve_roll_back_together_on_worker_failure(
    api, sessions, provider, settings, question_id, monkeypatch
):
    headers = auth(await register(api))
    response = await api.post(
        "/api/v1/submissions",
        headers=headers,
        json={"question_id": str(question_id), "language": "python", "source_code": "fixture"},
    )
    identifier = UUID(response.json()["data"]["id"])
    original = CoinService.award_daily_problem

    async def fail_after_credit(self, row):
        await original(self, row)
        raise RuntimeError("synthetic crash before commit")

    worker = EvaluationWorker(sessions, provider, settings)
    with monkeypatch.context() as patch:
        patch.setattr(CoinService, "award_daily_problem", fail_after_credit)
        with pytest.raises(RuntimeError):
            await worker.once()
    assert await balance(api, headers) == 0
    async with sessions() as session:
        row = await session.get(Submission, identifier)
        assert row.status == Verdict.RUNNING
        assert await session.scalar(select(UserProgress.solved_at)) is None
        lease = row.lease_id
    await worker.finish(identifier, lease)
    assert await balance(api, headers) == 20


async def test_reward_catalog_prices_and_insufficient_balance_preserve_coins(api):
    catalog = (await api.get("/api/v1/coins/rewards")).json()["data"]
    assert catalog["redemption_enabled"] and len(catalog["rewards"]) == 4
    assert [r["coin_cost"] for r in catalog["rewards"]] == [500, 1000, 2000, 4000]
    assert all(not r["is_placeholder"] and r["redeemable"] for r in catalog["rewards"])
    headers = auth(await register(api))
    await api.post("/api/v1/users/me/coins/check-in", headers=headers)
    for reward in catalog["rewards"]:
        response = await api.post(
            "/api/v1/coins/redeem",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "reward_id": reward["id"],
                "size": "M" if reward["available_sizes"] else None,
                "shipping_address": {
                    "full_name": "Test Recipient",
                    "phone": "9000000000",
                    "address_line1": "123 Test Street",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "postal_code": "560001",
                    "country_code": "IN",
                },
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_coins"
    assert await balance(api, headers) == 5
    assert (await api.get("/api/v1/users/me/coins/transactions", headers=headers)).json()[
        "total"
    ] == 1


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/users/me/streak"),
        ("GET", "/users/me/coins"),
        ("GET", "/users/me/coins/transactions"),
        ("POST", "/users/me/coins/check-in"),
        ("POST", "/coins/redeem"),
    ],
)
async def test_private_engagement_routes_require_auth(api, method, path):
    assert (await api.request(method, "/api/v1" + path)).status_code == 401


def test_longest_streak_handles_historical_gaps():
    today = date(2026, 11, 10)
    assert longest_streak(set()) == 0
    assert longest_streak({today - timedelta(days=n) for n in [0, 1, 8, 9, 10]}) == 3


async def test_potd_already_solved_before_today_can_earn_daily_reward(
    api, sessions, provider, settings, question_id
):
    headers = auth(await register(api))
    user_id = UUID((await api.get("/api/v1/users/me", headers=headers)).json()["data"]["id"])
    old_solved = datetime.now(UTC) - timedelta(days=3)
    async with sessions() as session:
        session.add(
            UserProgress(user_id=user_id, question_id=question_id, attempts=1, solved_at=old_solved)
        )
        await session.commit()
    await api.post(
        "/api/v1/submissions",
        headers=headers,
        json={"question_id": str(question_id), "language": "python", "source_code": "fixture"},
    )
    assert await EvaluationWorker(sessions, provider, settings).once()
    assert await balance(api, headers) == 20
    async with sessions() as session:
        assert await session.scalar(select(UserProgress.solved_at)) == old_solved


async def test_daily_problem_with_tampered_suite_is_never_selected(api, sessions, sample_question):
    async with sessions() as session:
        case = await session.scalar(select(Case).where(Case.question_id == sample_question["id"]))
        case.expected_output = "tampered"
        await session.commit()
    assert (await api.get("/api/v1/questions/daily")).status_code == 404


async def test_unpublished_daily_problem_does_not_change_midday(api, sessions, question_id):
    assert (await api.get("/api/v1/questions/daily")).status_code == 200
    async with sessions() as session:
        row = await session.get(Question, question_id)
        row.published = False
        await session.commit()
    result = await api.get("/api/v1/questions/daily")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "daily_problem_unavailable"


async def test_streak_is_graded_activity_and_checkins_do_not_extend_it(api, sessions, question_id):
    headers = auth(await register(api))
    user_id = UUID((await api.get("/api/v1/users/me", headers=headers)).json()["data"]["id"])
    now = datetime.now(UTC)
    async with sessions() as session:
        for gap in [1, 2, 8, 9, 10]:
            session.add(
                Submission(
                    user_id=user_id,
                    question_id=question_id,
                    language=Language.PYTHON,
                    language_id=71,
                    language_version="Fixture",
                    source_code="fixture",
                    mode=SubmissionMode.SUBMIT,
                    status=Verdict.WRONG_ANSWER,
                    cpu_seconds=1,
                    memory_kb=65536,
                    total_tests=1,
                    created_at=now - timedelta(days=gap),
                )
            )
        session.add(
            Submission(
                user_id=user_id,
                language=Language.PYTHON,
                language_id=71,
                language_version="Fixture",
                source_code="fixture",
                mode=SubmissionMode.RUN,
                status=Verdict.ACCEPTED,
                cpu_seconds=1,
                memory_kb=65536,
                total_tests=1,
                created_at=now,
            )
        )
        await session.commit()
    await api.post("/api/v1/users/me/coins/check-in", headers=headers)
    result = (await api.get("/api/v1/users/me/streak", headers=headers)).json()["data"]
    assert result["current_streak"] == 2 and result["longest_streak"] == 3
    assert not result["active_today"]
    assert result["last_activity_date"] == (now.date() - timedelta(days=1)).isoformat()
