import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.db import create_engine
from app.ingestion.catalog import CatalogBundle, build_bundle, onboard
from app.ingestion.leetcode import LeetCodePublicClient
from app.ingestion.workbook import read_workbook


def write_bundle(path: Path, bundle: CatalogBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.model_dump_json(indent=2) + "\n")


async def run(workbook: Path | None, bundle_path: Path, apply: bool) -> None:
    if workbook:
        data = await asyncio.to_thread(read_workbook, workbook)
        async with httpx.AsyncClient(timeout=25, trust_env=False, follow_redirects=False) as http:
            client = LeetCodePublicClient(http)
            catalog = await client.catalog({row.number for row in data.problems})
            details = await client.details(list(catalog.values()))
        bundle = build_bundle(data, catalog, details)
        await asyncio.to_thread(write_bundle, bundle_path, bundle)
    else:
        value = await asyncio.to_thread(bundle_path.read_text)
        bundle = CatalogBundle.model_validate_json(value)
    summary = {
        "questions": len(bundle.questions),
        "difficulty": dict(Counter(item.difficulty.value for item in bundle.questions)),
        "details": dict(Counter(item.source.details_status for item in bundle.questions)),
        "examples": sum(len(item.examples) for item in bundle.questions),
        "main_statements": "verbatim workbook content",
        "judge_test_cases_created": 0,
    }
    if apply:
        engine = create_engine(Settings())
        try:
            summary["database"] = await onboard(
                async_sessionmaker(engine, expire_on_commit=False), bundle
            )
        finally:
            await engine.dispose()
    print(json.dumps(summary, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import supplied workbook text with public LeetCode metadata"
    )
    parser.add_argument(
        "--workbook", type=Path, help="Prepare a bundle from this workbook and public metadata"
    )
    parser.add_argument("--bundle", type=Path, default=Path("data/questions/leetcode_001_300.json"))
    parser.add_argument(
        "--apply", action="store_true", help="Apply the validated bundle to the configured database"
    )
    args = parser.parse_args()
    asyncio.run(run(args.workbook, args.bundle, args.apply))


if __name__ == "__main__":
    main()
