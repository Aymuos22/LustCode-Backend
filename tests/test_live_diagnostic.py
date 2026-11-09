from app.core.errors import ProviderError
from app.diagnostics.judge0 import EXPECTED, verify_languages
from app.integrations.judge0 import ExecutionResult
from app.models import Verdict


async def test_live_diagnostic_checks_three_languages_without_recording_tokens(provider) -> None:
    provider.results = [ExecutionResult(status=Verdict.ACCEPTED, stdout=EXPECTED) for _ in range(3)]
    checks = await verify_languages(provider)
    assert len(checks) == 3 and all(check["passed"] for check in checks)
    assert {check["language"] for check in checks} == {"python", "java", "cpp"}
    assert all("token" not in check for check in checks)


async def test_live_diagnostic_reports_actual_failures(provider) -> None:
    provider.error = ProviderError()
    checks = await verify_languages(provider)
    assert len(checks) == 3 and not any(check["passed"] for check in checks)
    assert all(check["error"] == "provider_unavailable" for check in checks)
