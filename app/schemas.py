import re
import unicodedata
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
)

from app.models import CoinReason, Difficulty, Language, OrderStatus, SubmissionMode, Verdict


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Data[T](BaseModel):
    data: T


class Page[T](BaseModel):
    data: list[T]
    total: int
    page: int
    page_size: int


class ValidationIssue(BaseModel):
    location: list[str | int]
    message: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None
    details: list[ValidationIssue] | None = None
    current_revision: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Credentials(Schema):
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def valid_password_text(cls, value: SecretStr) -> SecretStr:
        try:
            value.get_secret_value().encode()
        except UnicodeEncodeError as exc:
            raise ValueError("Password must contain valid Unicode") from exc
        return value


class Register(Credentials):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class RefreshRequest(Schema):
    refresh_token: SecretStr = Field(min_length=40, max_length=200)


class Tokens(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserView(Schema):
    id: UUID
    username: str
    bio: str
    created_at: datetime
    avatar_url: str | None = None


class MeView(UserView):
    email: EmailStr
    is_staff: bool = False


class ProfileUpdate(Schema):
    bio: str = Field(max_length=500)

    @field_validator("bio")
    @classmethod
    def valid_bio_text(cls, value: str) -> str:
        try:
            value.encode()
        except UnicodeEncodeError as exc:
            raise ValueError("Bio must contain valid Unicode") from exc
        if "\x00" in value:
            raise ValueError("Bio cannot contain NUL")
        return value


class QuestionSource(Schema):
    provider: Literal["leetcode"]
    frontend_id: int = Field(gt=0)
    title: str
    slug: str
    url: str
    premium: bool
    details_status: Literal["public", "premium", "unavailable"]


class QuestionExample(Schema):
    input: str
    output: str


class FunctionParameter(Schema):
    name: str
    type: str


class FunctionSignature(Schema):
    name: str
    parameters: list[FunctionParameter] = Field(default_factory=list)
    return_type: str | None = None


class QuestionInterface(Schema):
    kind: Literal["function", "design", "sql", "shell"]
    function: FunctionSignature | None = None
    class_name: str | None = None
    constructor: FunctionSignature | None = None
    methods: list[FunctionSignature] = Field(default_factory=list)


class QuestionSummary(Schema):
    id: UUID
    slug: str
    title: str
    difficulty: Difficulty
    tags: list[str]
    source: QuestionSource | None = None
    supported_languages: list[Language] | None = None
    is_judgeable: bool = False
    judgeable_languages: list[Language] = Field(default_factory=list)
    judging_status: Literal["ready", "not_configured", "unsupported", "invalid_suite"] = (
        "not_configured"
    )


class Sample(Schema):
    stdin: str
    expected_output: str


class EvaluationContract(Schema):
    protocol: Literal["function", "design", "codec"] = "function"
    design: QuestionInterface | None = None
    origin: Literal["leetcode_public", "lustcode"]
    signature: FunctionSignature
    description: str
    comparison: str
    result: str
    suite_version: str
    fixture_signature: FunctionSignature | None = None
    custom_input_format: str = "JSON array of positional arguments; design: [operations, arguments]"


class QuestionView(QuestionSummary):
    statement: str
    hints: list[str]
    explanation: str | None
    starter_code: dict[str, str]
    constraints: list[str]
    samples: list[Sample]
    cpu_seconds: float
    memory_kb: int
    examples: list[QuestionExample] = Field(default_factory=list)
    interface: QuestionInterface | None = None
    evaluation_contract: EvaluationContract | None = None


class CodeRequest(Schema):
    language: Language
    language_id: int | None = Field(default=None, gt=0)
    source_code: str = Field(min_length=1, max_length=65536)

    @field_validator("source_code")
    @classmethod
    def source_size(cls, value: str) -> str:
        try:
            size = len(value.encode())
        except UnicodeEncodeError as exc:
            raise ValueError("Source must contain valid Unicode") from exc
        if size > 65536 or not value.strip() or "\x00" in value:
            raise ValueError("Source must be nonempty, at most 64 KiB, and contain no NUL")
        return value


class SubmitRequest(CodeRequest):
    question_id: UUID


class CustomRunCase(Schema):
    stdin: str = Field(min_length=1, max_length=16384)

    @field_validator("stdin")
    @classmethod
    def valid_input(cls, value: str) -> str:
        if len(value.encode()) > 16384 or "\x00" in value:
            raise ValueError("Custom input exceeds 16 KiB or contains NUL")
        return value


class SampleRunRequest(CodeRequest):
    """Omit test_cases for visible samples; custom cases execute without a correctness oracle."""

    test_cases: list[CustomRunCase] | None = Field(default=None, min_length=1, max_length=10)


class RunRequest(CodeRequest):
    stdin: str = Field(default="", max_length=16384)

    @field_validator("stdin")
    @classmethod
    def stdin_size(cls, value: str) -> str:
        try:
            size = len(value.encode())
        except UnicodeEncodeError as exc:
            raise ValueError("Input must contain valid Unicode") from exc
        if size > 16384 or "\x00" in value:
            raise ValueError("Input must be at most 16 KiB and contain no NUL")
        return value


class LanguageView(Schema):
    id: int
    language: Language
    name: str
    display_name: str = ""
    capabilities: list[str] = Field(default_factory=list)
    playground_starter_code: str = ""


class ResultView(Schema):
    position: int
    hidden: bool
    status: Verdict
    execution_time: float | None
    memory_kb: int | None
    stdin: str | None = None
    expected_output: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    compile_output: str | None = None


class SubmissionSummary(Schema):
    id: UUID
    question_id: UUID | None
    language: Language
    language_version: str
    mode: SubmissionMode
    evaluation_scope: Literal["graded", "samples", "custom", "playground"] = "playground"
    status: Verdict
    total_tests: int
    passed_tests: int
    execution_time: float | None
    memory_used_kb: int | None
    created_at: datetime
    completed_at: datetime | None


class SubmissionView(SubmissionSummary):
    source_code: str
    results: list[ResultView]


class ProgressView(Schema):
    question_id: UUID
    attempts: int
    solved_at: datetime | None
    last_submission_id: UUID | None


class Statistics(Schema):
    submissions: int
    accepted_submissions: int
    solved_questions: int
    by_difficulty: dict[str, int]
    by_language: dict[str, int]
    by_verdict: dict[str, int]
    daily_activity: dict[str, int]
    current_streak: int = 0
    longest_streak: int = 0
    acceptance_rate: float = 0
    evaluated_submissions: int = 0
    timezone: Literal["UTC"] = "UTC"


class StreakView(Schema):
    current_streak: int
    longest_streak: int
    active_today: bool
    last_activity_date: date | None
    daily_activity: dict[str, int]
    timezone: Literal["UTC"] = "UTC"
    basis: Literal["graded_submission_activity"] = "graded_submission_activity"
    next_reset_at: datetime


class DailyProblemView(Schema):
    date: date
    starts_at: datetime
    expires_at: datetime
    timezone: Literal["UTC"] = "UTC"
    question: QuestionSummary
    reward_coins: int
    completed: bool | None
    reward_claimed: bool | None


class CoinRules(Schema):
    currency: Literal["LustCoins"] = "LustCoins"
    daily_check_in: int
    daily_problem: int
    ordinary_solve: Literal[0] = 0
    sample_or_custom_run: Literal[0] = 0
    timezone: Literal["UTC"] = "UTC"
    redemption_enabled: Literal[True] = True


class CoinWallet(Schema):
    currency: Literal["LustCoins"] = "LustCoins"
    balance: int
    total_earned: int
    total_spent: int = Field(default=0, ge=0)
    total_refunded: int = Field(default=0, ge=0)
    check_in_claimed_today: bool
    next_reset_at: datetime
    rules: CoinRules
    redemption_enabled: Literal[True] = True


class CoinTransactionView(Schema):
    id: UUID
    amount: int
    reason: CoinReason
    reward_date: date
    question_id: UUID | None
    submission_id: UUID | None
    order_id: UUID | None = None
    created_at: datetime


class CheckInRequest(Schema):
    pass


class CheckInView(Schema):
    awarded: bool
    credited_amount: int
    transaction: CoinTransactionView
    wallet: CoinWallet


class RewardProductView(Schema):
    id: str
    name: str
    description: str
    coin_cost: int
    available_sizes: list[str]
    stock_quantity: int | None
    status: Literal["available", "out_of_stock", "unavailable"]
    is_placeholder: Literal[False] = False
    redeemable: bool


class RewardCatalog(Schema):
    currency: Literal["LustCoins"] = "LustCoins"
    redemption_enabled: Literal[True] = True
    fulfillment_mode: Literal["manual"] = "manual"
    shipping_countries: list[Literal["IN"]] = ["IN"]
    shipping_cost_coins: Literal[0] = 0
    rewards: list[RewardProductView]


class ShippingAddress(Schema):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=10, max_length=24)
    address_line1: str = Field(min_length=5, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(pattern=r"^[1-9][0-9]{5}$")
    country_code: Literal["IN"] = "IN"

    @field_validator("full_name", "address_line1", "address_line2", "city", "state", mode="before")
    @classmethod
    def clean_address_text(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Control characters are not allowed")
        return " ".join(unicodedata.normalize("NFC", value).split())

    @field_validator("phone", mode="before")
    @classmethod
    def indian_mobile(cls, value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[+0-9() -]{10,24}", value):
            raise ValueError("Use a valid Indian mobile number")
        digits = re.sub(r"[^0-9]", "", value)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if not re.fullmatch(r"[6-9][0-9]{9}", digits):
            raise ValueError("Use a valid Indian mobile number")
        return "+91" + digits


class RedeemRequest(Schema):
    reward_id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    shipping_address: ShippingAddress
    size: Literal["XS", "S", "M", "L", "XL", "XXL"] | None = None


class OrderSummary(Schema):
    id: UUID
    reward_id: str
    product_name: str
    coin_cost: int
    size: str | None
    status: OrderStatus
    quantity: Literal[1] = 1
    fulfillment_mode: Literal["manual"] = "manual"
    created_at: datetime
    updated_at: datetime
    shipped_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    courier: str | None
    tracking_number: str | None


class OrderDetail(OrderSummary):
    shipping_address: ShippingAddress


class OrderReceipt(Schema):
    order: OrderDetail
    wallet: CoinWallet
    replayed: bool
    coins_spent: int = 0
    coins_refunded: int = 0


class OrderStatusPatch(Schema):
    status: OrderStatus
    courier: str | None = Field(
        default=None, min_length=2, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$"
    )
    tracking_number: str | None = Field(
        default=None, min_length=3, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]*$"
    )


class ProductAvailabilityPatch(Schema):
    active: bool = True
    stock_quantity: int | None = Field(default=None, ge=0, le=1_000_000)


class LeaderboardEntry(Schema):
    rank: int
    user_id: UUID
    username: str
    solved_questions: int
    avatar_url: str | None = None


class TopicView(Schema):
    slug: str
    name: str
    question_count: int


class QuestionNavigation(Schema):
    question_id: UUID
    previous_id: UUID | None
    next_id: UUID | None
    position: int
    total: int


class FeaturedQuestions(Schema):
    selection_rule: Literal["first_in_catalog"] = "first_in_catalog"
    questions: list[QuestionSummary]


class CollectionView(Schema):
    id: UUID
    slug: str
    name: str
    description: str
    position: int
    difficulty: Difficulty
    selection_rule: Literal["difficulty"] = "difficulty"
    question_count: int
    solved_count: int | None = None
    completion_percentage: float | None = None


class CollectionDetail(Schema):
    collection: CollectionView
    questions: Page[QuestionSummary]


class DraftWrite(Schema):
    """Send the last-read revision (zero only for untouched workspaces). Stale writes return 409."""

    source_code: str = Field(max_length=65536)
    stdin: str | None = Field(default=None, max_length=16384)
    revision: int = Field(ge=0, le=2147483646, strict=True)

    @field_validator("source_code", "stdin")
    @classmethod
    def text_limits(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None:
            limit = 65536 if info.field_name == "source_code" else 16384
            if len(value.encode()) > limit or "\x00" in value:
                raise ValueError("Text exceeds byte limit or contains NUL")
        return value


class DraftView(Schema):
    """Deleted drafts retain a revision tombstone; a new save uses that revision."""

    workspace: str
    question_id: UUID | None
    language: Language
    source_code: str | None = None
    stdin: str | None = None
    revision: int = 0
    updated_at: datetime | None = None
    exists: bool = False


class EditorPreferences(Schema):
    """Per-account defaults. pane_split is a percentage; runtime IDs come from /languages."""

    font_size: int = Field(default=14, ge=10, le=32, strict=True)
    editor_mode: Literal["standard", "vim", "emacs"] = "standard"
    preferred_language: Language = Language.PYTHON
    preferred_runtime_id: int | None = Field(default=None, gt=0, strict=True)
    pane_split: float = Field(default=50, ge=20, le=80)


class PreferencesPatch(Schema):
    font_size: int | None = Field(default=None, ge=10, le=32, strict=True)
    editor_mode: Literal["standard", "vim", "emacs"] | None = None
    preferred_language: Language | None = None
    preferred_runtime_id: int | None = Field(default=None, gt=0, strict=True)
    pane_split: float | None = Field(default=None, ge=20, le=80)

    @field_validator("font_size", "editor_mode", "preferred_language", "pane_split")
    @classmethod
    def not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Preference cannot be null")
        return value
