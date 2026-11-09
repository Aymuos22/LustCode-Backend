from uuid import UUID

from pydantic import ValidationError

from app.core.config import Settings
from app.judging.contracts import JudgeProfile, suite_hash
from app.judging.readiness import readiness
from app.models import Difficulty, Language, Question
from app.repositories import QuestionRepository
from app.schemas import (
    EvaluationContract,
    FunctionParameter,
    FunctionSignature,
    Page,
    QuestionInterface,
    QuestionSummary,
    QuestionView,
    Sample,
)


class QuestionService:
    def __init__(self, repo: QuestionRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def summary(self, question: Question, test_count: int) -> QuestionSummary:
        status, languages = readiness(question, test_count, self.settings.max_test_cases)
        return QuestionSummary(
            id=question.id,
            slug=question.slug,
            title=question.title,
            difficulty=question.difficulty,
            tags=question.tags,
            source=question.content.get("source"),
            supported_languages=languages
            if status == "ready"
            else question.content.get("supported_languages", list(Language)),
            is_judgeable=status == "ready",
            judgeable_languages=languages,
            judging_status=status,
        )

    async def list(
        self,
        page: int,
        size: int,
        difficulty: Difficulty | None,
        search: str | None,
        topic: str | None = None,
    ) -> Page[QuestionSummary]:
        questions, total = await self.repo.list_questions(page, size, difficulty, search, topic)
        counts = await self.repo.test_counts([q.id for q in questions])
        return Page(
            data=[self.summary(q, counts.get(q.id, 0)) for q in questions],
            total=total,
            page=page,
            page_size=size,
        )

    async def detail(self, question_id: UUID) -> QuestionView:
        question = await self.repo.published(question_id)
        all_tests = await self.repo.tests(question_id)
        tests = [case for case in all_tests if not case.hidden]
        # Never serialize arbitrary ingestion JSON: allowlist the supported public fields.
        content = question.content
        contract = None
        profile = None
        interface = content.get("interface")
        try:
            profile = JudgeProfile.model_validate(content.get("judging"))
            contract = EvaluationContract(
                fixture_signature=profile.signature if profile.protocol == "function" else None,
                **profile.model_dump(
                    include={
                        "origin",
                        "signature",
                        "description",
                        "comparison",
                        "result",
                        "suite_version",
                        "protocol",
                        "design",
                    }
                ),
            )
            if profile.native_signature:
                contract.signature = profile.native_signature
            if profile.design:
                interface = profile.design
            else:
                interface = QuestionInterface(
                    kind="function", class_name="Solution", function=contract.signature
                )
            if profile.adapter == "codec":
                interface = QuestionInterface(
                    kind="design",
                    class_name="Codec",
                    constructor=FunctionSignature(name="Codec"),
                    methods=[
                        FunctionSignature(
                            name="serialize",
                            parameters=[FunctionParameter(name="root", type="TreeNode")],
                            return_type="string",
                        ),
                        FunctionSignature(
                            name="deserialize",
                            parameters=[FunctionParameter(name="data", type="string")],
                            return_type="TreeNode",
                        ),
                    ],
                )
                contract.protocol = "codec"
                contract.design = interface
        except (ValidationError, ValueError, TypeError):
            pass
        summary = self.summary(question, len(all_tests))
        if (
            profile
            and suite_hash(
                [
                    {"stdin": c.stdin, "expected_output": c.expected_output, "hidden": c.hidden}
                    for c in all_tests
                ]
            )
            != profile.suite_sha256
        ):
            summary.is_judgeable = False
            summary.judging_status = "invalid_suite"
            summary.judgeable_languages = []
        return QuestionView(
            **summary.model_dump(),
            statement=question.statement,
            hints=content.get("hints", []),
            explanation=content.get("explanation"),
            starter_code=content.get("starter_code", {}),
            constraints=content.get("constraints", []),
            samples=[Sample(stdin=t.stdin, expected_output=t.expected_output) for t in tests],
            cpu_seconds=min(question.cpu_seconds, self.settings.max_cpu_seconds),
            memory_kb=min(question.memory_kb, self.settings.max_memory_kb),
            examples=content.get("examples", []),
            interface=interface,
            evaluation_contract=contract,
        )
