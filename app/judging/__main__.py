"""Administrative suite install: python -m app.judging [--apply]."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.db import create_engine
from app.ingestion.catalog import CatalogBundle
from app.judging.suites import build_suites, install_suites


async def run(bundle_path: Path, apply: bool) -> None:
    bundle = CatalogBundle.model_validate_json(await asyncio.to_thread(bundle_path.read_text))
    suites = await asyncio.to_thread(build_suites, bundle)
    report = {
        "questions_with_suites": len(suites),
        "test_cases": sum(len(s["cases"]) for s in suites.values()),
        "hidden_cases": sum(c["hidden"] for s in suites.values() for c in s["cases"]),
        "remaining_questions": [
            {
                "id": q.source.frontend_id,
                "title": q.title,
                "reason": "unsupported_language"
                if q.supported_languages == []
                else "requires_verified_contract_and_suite",
            }
            for q in bundle.questions
            if q.source.frontend_id not in suites
        ],
    }
    if apply:
        engine = create_engine(Settings())
        try:
            report["database"] = await install_suites(
                async_sessionmaker(engine, expire_on_commit=False), suites
            )
        finally:
            await engine.dispose()
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("data/questions/leetcode_001_300.json"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.bundle, args.apply))


if __name__ == "__main__":
    main()
