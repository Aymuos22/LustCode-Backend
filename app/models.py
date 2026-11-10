from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Language(StrEnum):
    PYTHON = "python"
    JAVA = "java"
    CPP = "cpp"


class Verdict(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    ACCEPTED = "accepted"
    WRONG_ANSWER = "wrong_answer"
    COMPILATION_ERROR = "compilation_error"
    RUNTIME_ERROR = "runtime_error"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    PROVIDER_ERROR = "provider_error"


class SubmissionMode(StrEnum):
    SUBMIT = "submit"
    RUN = "run"


class CoinReason(StrEnum):
    DAILY_CHECK_IN = "daily_check_in"
    DAILY_PROBLEM = "daily_problem"


def enum_type(enum: type[StrEnum]) -> Enum:
    return Enum(
        enum,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda cls: [item.value for item in cls],
    )


class Base(DeclarativeBase):
    pass


class IdentityMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(IdentityMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    bio: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_key: Mapped[str | None] = mapped_column(String(36))
    preferences: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, server_default=text("'{}'::jsonb")
    )

    @property
    def avatar_url(self) -> str | None:
        return f"/api/v1/avatars/{self.avatar_key}" if self.avatar_key else None


class QuestionCollection(IdentityMixin, Base):
    __tablename__ = "question_collections"
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[Difficulty] = mapped_column(enum_type(Difficulty))


class WorkspaceDraft(IdentityMixin, Base):
    __tablename__ = "workspace_drafts"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workspace: Mapped[str] = mapped_column(String(36))
    question_id: Mapped[UUID | None] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    language: Mapped[Language] = mapped_column(enum_type(Language))
    source_code: Mapped[str | None] = mapped_column(Text)
    stdin: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("user_id", "workspace", "language"),
        CheckConstraint("revision > 0"),
        CheckConstraint(
            "(workspace = 'playground' AND question_id IS NULL) OR "
            "(workspace <> 'playground' AND question_id IS NOT NULL)"
        ),
    )


class RefreshToken(IdentityMixin, Base):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=uuid4)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Question(IdentityMixin, Base):
    __tablename__ = "questions"
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    title: Mapped[str] = mapped_column(String(250))
    difficulty: Mapped[Difficulty] = mapped_column(enum_type(Difficulty), index=True)
    statement: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cpu_seconds: Mapped[float] = mapped_column(Float, default=2)
    memory_kb: Mapped[int] = mapped_column(Integer, default=131072)
    __table_args__ = (CheckConstraint("cpu_seconds > 0 AND memory_kb >= 16384"),)


class TestCase(IdentityMixin, Base):
    __tablename__ = "test_cases"
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    stdin: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("question_id", "position"),)


class Submission(IdentityMixin, Base):
    __tablename__ = "submissions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    daily_challenge_date: Mapped[date | None] = mapped_column(
        ForeignKey(
            "daily_challenges.day", ondelete="RESTRICT", name="fk_submissions_daily_challenge"
        )
    )
    language: Mapped[Language] = mapped_column(enum_type(Language))
    language_id: Mapped[int] = mapped_column(Integer)
    language_version: Mapped[str] = mapped_column(String(150))
    source_code: Mapped[str] = mapped_column(Text)
    evaluation: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    custom_input: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    mode: Mapped[SubmissionMode] = mapped_column(enum_type(SubmissionMode))
    status: Mapped[Verdict] = mapped_column(enum_type(Verdict), default=Verdict.QUEUED)
    cpu_seconds: Mapped[float] = mapped_column(Float)
    memory_kb: Mapped[int] = mapped_column(Integer)
    total_tests: Mapped[int] = mapped_column(Integer)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    execution_time: Mapped[float | None] = mapped_column(Float)
    memory_used_kb: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[UUID | None] = mapped_column(Uuid)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def evaluation_scope(self) -> str:
        if self.mode == SubmissionMode.SUBMIT:
            return "graded"
        if self.question_id is None:
            return "playground"
        return "custom" if self.custom_input else "samples"

    __table_args__ = (
        Index("ix_submission_user_created", "user_id", "created_at"),
        Index("ix_submission_claim", "status", "lease_until", "created_at"),
        CheckConstraint("total_tests > 0 AND passed_tests >= 0 AND passed_tests <= total_tests"),
        CheckConstraint("mode = 'run' OR question_id IS NOT NULL"),
    )


class SubmissionTestResult(IdentityMixin, Base):
    __tablename__ = "submission_test_results"
    submission_id: Mapped[UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    test_case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    hidden: Mapped[bool] = mapped_column(Boolean)
    stdin: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str | None] = mapped_column(Text)
    provider_token: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[Verdict] = mapped_column(enum_type(Verdict), default=Verdict.QUEUED)
    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)
    compile_output: Mapped[str | None] = mapped_column(Text)
    execution_time: Mapped[float | None] = mapped_column(Float)
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("submission_id", "position"),)


class UserProgress(IdentityMixin, Base):
    __tablename__ = "user_progress"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_submission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"), index=True
    )
    __table_args__ = (
        UniqueConstraint("user_id", "question_id"),
        Index("ix_progress_solved", "solved_at"),
    )


class DailyChallenge(Base):
    __tablename__ = "daily_challenges"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoinTransaction(IdentityMixin, Base):
    __tablename__ = "coin_transactions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[CoinReason] = mapped_column(enum_type(CoinReason))
    event_key: Mapped[str] = mapped_column(String(80))
    reward_date: Mapped[date] = mapped_column(Date)
    question_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT")
    )
    submission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL")
    )
    __table_args__ = (
        UniqueConstraint("user_id", "event_key"),
        CheckConstraint("amount > 0"),
        Index("ix_coin_transactions_user_created", "user_id", "created_at"),
    )
