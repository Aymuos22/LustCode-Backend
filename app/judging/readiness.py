import hashlib

from pydantic import ValidationError

from app.judging.contracts import JudgeProfile
from app.models import Language, Question


def readiness(question: Question, test_count: int, max_cases: int) -> tuple[str, list[Language]]:
    if question.content.get("supported_languages") == []:
        return "unsupported", []
    raw = question.content.get("judging")
    # Imported function/design entries require an explicit trusted driver contract.
    if raw is None and question.content.get("source", {}).get("provider") == "leetcode":
        return "not_configured", []
    if not 0 < test_count <= max_cases:
        return "not_configured" if not test_count else "invalid_suite", []
    if raw is not None:
        try:
            profile = JudgeProfile.model_validate(raw)
        except (ValidationError, ValueError, TypeError):
            return "invalid_suite", []
        if test_count != profile.test_count:
            return "invalid_suite", []
        if (
            not profile.suite_sha256
            or profile.statement_sha256 != hashlib.sha256(question.statement.encode()).hexdigest()
        ):
            return "invalid_suite", []
        return "ready", profile.languages
    # Existing independently ingested stdin/stdout questions remain supported.
    return "ready", list(Language)
