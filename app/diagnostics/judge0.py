"""Explicit live check: python -m app.diagnostics.judge0 [--output audit/live_judge0.json].

Makes three real submissions; never invoked by normal unit tests or CI.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.core.errors import AppError
from app.integrations.judge0 import ExecutionProvider, Judge0, select_language
from app.models import Language, Verdict
from app.runtime import runtime_resources

STDIN = "LustCode\n"
EXPECTED = "foundation:LustCode\n"
SOURCES = {
    Language.PYTHON: 'print("foundation:" + input())\n',
    Language.JAVA: (
        "import java.util.Scanner; class Main { public static void main(String[] args) {"
        'System.out.println("foundation:" + new Scanner(System.in).nextLine()); }}'
    ),
    Language.CPP: (
        "#include <iostream>\n#include <string>\n"
        "int main(){std::string s; std::getline(std::cin,s); "
        'std::cout << "foundation:" << s << "\\n";}\n'
    ),
}


async def verify_languages(provider: ExecutionProvider) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for language, source in SOURCES.items():
        check: dict[str, object] = {"language": language.value}
        try:
            version = await select_language(provider, language, None)
            check.update(language_id=version.id, version=version.name)
            token = await provider.create(source, version.id, STDIN, EXPECTED, 2, 131072)
            check["submitted"] = True
            execution = await provider.poll(token)
            # Only the adapter's allowlisted result is recorded. Provider tokens stay private.
            check.update(execution.model_dump(mode="json"))
            check["passed"] = execution.status == Verdict.ACCEPTED and execution.stdout == EXPECTED
        except AppError as exc:
            check.update(passed=False, error=exc.code, message=exc.message)
        checks.append(check)
    return checks


def write_report(output: Path, rendered: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered)


async def run(output: Path | None) -> int:
    settings = Settings()
    async with runtime_resources(settings) as resources:
        # Bypass the optional Redis language cache so this verifies the live registry.
        checks = await verify_languages(Judge0(resources.http, settings))
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "endpoint": settings.judge0_url,
        "checks": checks,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if output:
        await asyncio.to_thread(write_report, output, rendered)
    print(rendered, end="")
    return 0 if all(check["passed"] for check in checks) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.output)))


if __name__ == "__main__":
    main()
