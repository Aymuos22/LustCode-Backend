"""Opt-in real sample runs using the retained ordinary test account."""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

from app.diagnostics.judging import CASES
from app.ingestion.catalog import question_id

NAMES = {
    "python_correct",
    "java_correct",
    "cpp_correct",
    "wrong_answer",
    "compilation_error",
    "java_in_place",
    "python_tree",
    "lustcode_unicode_codec",
    "cpp_tree_codec",
}


async def verify(account_file: Path, output: Path, budget_seconds: float) -> bool:
    credentials = await asyncio.to_thread(dotenv_values, account_file)
    base = credentials.get("TEST_API_BASE_URL") or "http://127.0.0.1:8000"
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "checks": {},
        "runs": [],
    }

    async def save() -> None:
        await asyncio.to_thread(output.write_text, json.dumps(report, indent=2) + "\n")

    await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
    refresh = None
    headers: dict[str, str] = {}
    started = time.monotonic()
    async with httpx.AsyncClient(base_url=base + "/api/v1", timeout=30, trust_env=False) as api:

        async def request(method: str, path: str, expected: int = 200, **kwargs: Any) -> Any:
            nonlocal refresh
            response = await api.request(method, path, headers=headers, **kwargs)
            if response.status_code == 401 and refresh:
                rotated = await api.post("/auth/refresh", json={"refresh_token": refresh})
                if rotated.status_code == 200:
                    tokens = rotated.json()["data"]
                    refresh = tokens["refresh_token"]
                    headers["Authorization"] = "Bearer " + tokens["access_token"]
                    response = await api.request(method, path, headers=headers, **kwargs)
            if response.status_code != expected:
                raise RuntimeError(
                    f"{method} {path}: HTTP {response.status_code}, expected {expected}"
                )
            return response.json() if response.content else None

        async def account_snapshot() -> list[Any]:
            progress = []
            page = 1
            while True:
                response = await request(
                    "GET", "/users/me/progress", params={"page": page, "page_size": 100}
                )
                progress.extend(response["data"])
                if len(progress) >= response["total"]:
                    break
                page += 1
            return [progress, (await request("GET", "/users/me/statistics"))["data"]]

        async def completed(summary: dict[str, Any], scenario: str, expected: str) -> None:
            entry = {
                "case": scenario,
                "id": summary["id"],
                "question_id": summary["question_id"],
                "language": summary["language"],
                "version": summary["language_version"],
                "mode": summary["mode"],
                "total_tests": summary["total_tests"],
                "expected": expected,
                "status": summary["status"],
            }
            report["runs"].append(entry)
            await save()
            while True:
                detail = (await request("GET", "/submissions/" + summary["id"]))["data"]
                entry["status"] = detail["status"]
                entry["passed_tests"] = detail["passed_tests"]
                if detail["status"] not in {"queued", "running"}:
                    assert detail["status"] == expected
                    if expected == "accepted":
                        assert detail["passed_tests"] == detail["total_tests"]
                    assert all(
                        r["stdin"] is None
                        and r["expected_output"] is None
                        and r["stdout"] is None
                        and r["stderr"] is None
                        and r["compile_output"] is None
                        for r in detail["results"]
                        if r["hidden"]
                    )
                    if summary["mode"] == "run":
                        assert detail["results"] and all(
                            not r["hidden"]
                            and r["stdin"] is not None
                            and r["expected_output"] is not None
                            for r in detail["results"]
                        )
                    entry["passed"] = True
                    await save()
                    print(
                        json.dumps({"case": scenario, "status": detail["status"], "passed": True}),
                        flush=True,
                    )
                    return
                if time.monotonic() - started >= budget_seconds:
                    raise RuntimeError("Sample run verification deadline reached")
                await asyncio.sleep(3)

        try:
            tokens = (
                await request(
                    "POST",
                    "/auth/login",
                    json={
                        "email": credentials.get("TEST_ACCOUNT_EMAIL"),
                        "password": credentials.get("TEST_ACCOUNT_PASSWORD"),
                    },
                )
            )["data"]
            refresh = tokens["refresh_token"]
            headers["Authorization"] = "Bearer " + tokens["access_token"]
            baseline = await account_snapshot()
            selected = [c for c in CASES if c["case"] in NAMES]
            assert len(selected) == len(NAMES)
            for case in selected:
                question = (await request("GET", f"/questions/{question_id(case['question'])}"))[
                    "data"
                ]
                assert question["is_judgeable"] and question["samples"]
                report["suite_version"] = question["evaluation_contract"]["suite_version"]
                summary = (
                    await request(
                        "POST",
                        f"/questions/{question['id']}/runs",
                        expected=202,
                        json={"language": case["language"], "source_code": case["source"]},
                    )
                )["data"]
                assert summary["mode"] == "run" and summary["total_tests"] == len(
                    question["samples"]
                )
                await completed(summary, case["case"], case["expected"])
            question = (await request("GET", f"/questions/{question_id(1)}"))["data"]
            answers = {
                json.dumps(json.loads(c["stdin"]), separators=(",", ":")): json.loads(
                    c["expected_output"]
                )
                for c in question["samples"]
            }
            source = (
                "import json\nclass Solution:\n    def twoSum(self,nums,target):\n        "
                + "return "
                + repr(answers)
                + ".get(json.dumps([nums,target],separators=(',',':')),[0,0])\n"
            )
            payload = {"language": "python", "source_code": source}
            summary = (
                await request(
                    "POST", f"/questions/{question['id']}/runs", expected=202, json=payload
                )
            )["data"]
            await completed(summary, "sample_only_solution", "accepted")
            assert await account_snapshot() == baseline
            report["checks"]["samples_do_not_change_progress_or_statistics"] = "passed"
            summary = (
                await request(
                    "POST",
                    "/submissions",
                    expected=202,
                    json={**payload, "question_id": question["id"]},
                )
            )["data"]
            await completed(summary, "sample_only_solution_full_submission", "wrong_answer")
            after = await account_snapshot()
            assert after[1]["solved_questions"] == baseline[1]["solved_questions"]
            report["checks"]["passing_samples_does_not_guarantee_full_acceptance"] = "passed"
            report["checks"]["private_fields_redacted"] = "passed"
            report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["error_type"] = type(exc).__name__
            report["error"] = (
                str(exc) if isinstance(exc, RuntimeError) else "Verification assertion failed"
            )
        finally:
            if refresh:
                await api.post("/auth/logout", json={"refresh_token": refresh})
            report["elapsed_seconds"] = round(time.monotonic() - started, 2)
            report["finished_at"] = datetime.now(UTC).isoformat()
            await save()
    print(json.dumps({"status": report["status"], "report": str(output)}), flush=True)
    return report["status"] == "passed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-file", type=Path, default=Path(".env.test-account"))
    parser.add_argument("--output", type=Path, default=Path("audit/sample_runs_live.json"))
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(verify(args.account_file, args.output, args.timeout)) else 1)


if __name__ == "__main__":
    main()
