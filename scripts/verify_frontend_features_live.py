"""Opt-in live frontend API verification against the existing ordinary test account.

Run from the backend root: PYTHONPATH=. python scripts/verify_frontend_features_live.py
No synthetic questions or test suites are inserted. Live execution history is retained.
"""

import asyncio
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values
from PIL import Image

from app.diagnostics.judging import CASES
from app.ingestion.catalog import question_id


async def main():
    credentials = await asyncio.to_thread(dotenv_values, ".env.test-account")
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "checks": {},
        "executions": [],
    }
    output = Path("audit/frontend_features_live.json")
    refresh = None
    headers = {}
    original_font = None
    draft_path = "/users/me/drafts/playground/cpp"
    draft_revision = None
    uploaded_url = None
    start = time.monotonic()

    async def save():
        await asyncio.to_thread(output.write_text, json.dumps(report, indent=2) + "\n")

    async with httpx.AsyncClient(
        base_url=(credentials.get("TEST_API_BASE_URL") or "http://127.0.0.1:8000") + "/api/v1",
        timeout=30,
        trust_env=False,
    ) as api:

        async def request(method, path, status=200, authenticated=True, **kwargs):
            nonlocal refresh
            response = await api.request(
                method,
                path,
                headers={**(headers if authenticated else {}), **kwargs.pop("headers", {})},
                **kwargs,
            )
            if response.status_code == 401 and authenticated and refresh:
                rotated = await api.post("/auth/refresh", json={"refresh_token": refresh})
                if rotated.status_code == 200:
                    tokens = rotated.json()["data"]
                    refresh = tokens["refresh_token"]
                    headers["Authorization"] = "Bearer " + tokens["access_token"]
                    response = await api.request(method, path, headers=headers, **kwargs)
            if response.status_code != status:
                raise RuntimeError(
                    f"{method} {path}: HTTP {response.status_code}, expected {status}"
                )
            return (
                response.json()
                if response.content
                and "application/json" in response.headers.get("content-type", "")
                else response.content
            )

        async def snapshot():
            stats = (await request("GET", "/users/me/statistics"))["data"]
            progress = []
            page = 1
            while True:
                p = await request(
                    "GET", "/users/me/progress", params={"page": page, "page_size": 100}
                )
                progress += p["data"]
                if len(progress) >= p["total"]:
                    break
                page += 1
            return stats, progress

        async def execute(path, payload, name, scope, expected_output=None):
            summary = (await request("POST", path, status=202, json=payload))["data"]
            assert summary["evaluation_scope"] == scope
            entry = {
                k: summary[k]
                for k in [
                    "id",
                    "language",
                    "language_version",
                    "evaluation_scope",
                    "total_tests",
                    "status",
                ]
            }
            entry["case"] = name
            report["executions"].append(entry)
            await save()
            while True:
                detail = (await request("GET", "/submissions/" + summary["id"]))["data"]
                if detail["status"] not in ["queued", "running"]:
                    entry["status"] = detail["status"]
                    assert detail["status"] == "accepted"
                    assert all(not row["hidden"] for row in detail["results"])
                    if scope == "custom":
                        assert all(row["expected_output"] is None for row in detail["results"])
                    if expected_output is not None:
                        assert detail["results"][0]["stdout"] == expected_output
                    entry["passed"] = True
                    await save()
                    print(
                        json.dumps({"case": name, "passed": True, "status": detail["status"]}),
                        flush=True,
                    )
                    break
                if time.monotonic() - start > 900:
                    raise RuntimeError("Live verification deadline reached")
                await asyncio.sleep(3)

        try:
            tokens = (
                await request(
                    "POST",
                    "/auth/login",
                    authenticated=False,
                    json={
                        "email": credentials.get("TEST_ACCOUNT_EMAIL"),
                        "password": credentials.get("TEST_ACCOUNT_PASSWORD"),
                    },
                )
            )["data"]
            refresh = tokens["refresh_token"]
            headers["Authorization"] = "Bearer " + tokens["access_token"]
            await request("GET", "/health/ready")
            await request("GET", "/health/live")
            before = await snapshot()
            topics = (await request("GET", "/topics", authenticated=False))["data"]
            assert topics
            filtered = await request(
                "GET",
                "/questions",
                params={"topic": "array", "difficulty": "easy", "search": "Two Sum"},
            )
            assert filtered["total"] >= 1
            first = filtered["data"][0]
            picked = (
                await request(
                    "GET",
                    "/questions/random",
                    params={"topic": "array", "difficulty": "easy", "search": "Two Sum"},
                )
            )["data"]
            assert picked["difficulty"] == "easy" and "array" in picked["tags"]
            nav = (
                await request(
                    "GET",
                    f"/questions/{first['id']}/navigation",
                    params={"topic": "array", "difficulty": "easy", "search": "Two Sum"},
                )
            )["data"]
            assert (
                nav["position"] == 1
                and nav["previous_id"] is None
                and nav["total"] == filtered["total"]
            )
            featured = (await request("GET", "/questions/featured", params={"limit": 2}))["data"]
            assert len(featured["questions"]) == 2
            guest = await request("GET", "/collections", authenticated=False)
            own = await request("GET", "/collections")
            assert guest["total"] == own["total"] == 3
            assert all(c["solved_count"] is None for c in guest["data"])
            assert all(c["solved_count"] is not None for c in own["data"])
            await request("GET", "/collections/" + own["data"][0]["id"], params={"topic": "array"})
            report["checks"]["catalog_topics_collections_random_featured_navigation"] = "passed"
            existing = (await request("GET", draft_path))["data"]
            if not existing["exists"]:
                saved = (
                    await request(
                        "PUT",
                        draft_path,
                        json={
                            "revision": existing["revision"],
                            "source_code": "// live verification",
                            "stdin": "input",
                        },
                    )
                )["data"]
                draft_revision = saved["revision"]
                conflict = await request(
                    "PUT",
                    draft_path,
                    status=409,
                    json={"revision": existing["revision"], "source_code": "stale"},
                )
                assert conflict["error"]["current_revision"] == draft_revision
                deleted = (
                    await request("DELETE", draft_path, params={"revision": draft_revision})
                )["data"]
                draft_revision = None
                assert not deleted["exists"]
                report["checks"]["draft_conflict_and_reset"] = "passed"
            else:
                report["checks"]["draft_conflict_and_reset"] = "skipped_existing_draft_preserved"
            prefs = (await request("GET", "/users/me/preferences"))["data"]
            original_font = prefs["font_size"]
            changed = (
                await request(
                    "PATCH",
                    "/users/me/preferences",
                    json={"font_size": 18 if original_font != 18 else 19},
                )
            )["data"]
            assert changed["font_size"] != original_font
            await request("PATCH", "/users/me/preferences", json={"font_size": original_font})
            original_font = None
            report["checks"]["preferences"] = "passed"
            me = (await request("GET", "/users/me"))["data"]
            if me["avatar_url"] is None:
                picture = io.BytesIO()
                Image.new("RGB", (16, 16), (250, 150, 0)).save(picture, format="PNG")
                updated = (
                    await request(
                        "PUT",
                        "/users/me/avatar",
                        headers={"Content-Type": "image/png"},
                        content=picture.getvalue(),
                    )
                )["data"]
                uploaded_url = updated["avatar_url"]
                assert uploaded_url
                content = await request(
                    "GET", uploaded_url.removeprefix("/api/v1"), authenticated=False
                )
                assert content.startswith(b"\x89PNG")
                public = (await request("GET", "/users/" + me["username"], authenticated=False))[
                    "data"
                ]
                assert public["avatar_url"] == uploaded_url and "email" not in public
                await request("DELETE", "/users/me/avatar")
                uploaded_url = None
                report["checks"]["avatar_upload_public_read_and_removal"] = "passed"
            else:
                report["checks"]["avatar_upload_public_read_and_removal"] = (
                    "skipped_existing_avatar_preserved"
                )
            runtimes = (await request("GET", "/languages"))["data"]
            assert all(
                r["display_name"] and r["capabilities"] and r["playground_starter_code"]
                for r in runtimes
            )
            for language in ["python", "java", "cpp"]:
                case = next(c for c in CASES if c["case"] == language + "_correct")
                await execute(
                    f"/questions/{question_id(1)}/runs",
                    {
                        "language": language,
                        "source_code": case["source"],
                        "test_cases": [{"stdin": "[[8,2,11],10]"}],
                    },
                    "custom_" + language,
                    "custom",
                )
            source = """class MinStack:
    def __init__(self): self.values=[]
    def push(self,val): self.values.append(val)
    def pop(self): self.values.pop()
    def top(self): return self.values[-1]
    def getMin(self): return min(self.values)
"""
            await execute(
                f"/questions/{question_id(155)}/runs",
                {
                    "language": "python",
                    "source_code": source,
                    "test_cases": [
                        {"stdin": '[["MinStack","push","push","getMin"],[[],[5],[2],[]]]'}
                    ],
                },
                "custom_design",
                "custom",
                "[null,null,null,2]\n",
            )
            for language in ["python", "java", "cpp"]:
                runtime = max(
                    (r for r in runtimes if r["language"] == language), key=lambda r: r["id"]
                )
                await execute(
                    "/runs",
                    {
                        "language": language,
                        "language_id": runtime["id"],
                        "source_code": runtime["playground_starter_code"],
                        "stdin": "hello\n",
                    },
                    "playground_starter_" + language,
                    "playground",
                    "hello\n",
                )
            case = next(c for c in CASES if c["case"] == "python_correct")
            await execute(
                f"/questions/{question_id(1)}/runs",
                {"language": "python", "source_code": case["source"]},
                "existing_samples",
                "samples",
            )
            assert await snapshot() == before
            report["checks"][
                "runs_drafts_preferences_avatars_do_not_change_graded_statistics_or_progress"
            ] = "passed"
            report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["error_type"] = type(exc).__name__
            report["error"] = (
                str(exc) if isinstance(exc, RuntimeError) else "Live verification assertion failed"
            )
        finally:
            if original_font is not None:
                await request("PATCH", "/users/me/preferences", json={"font_size": original_font})
            if draft_revision is not None:
                await request("DELETE", draft_path, params={"revision": draft_revision}, status=200)
            if uploaded_url is not None:
                await request("DELETE", "/users/me/avatar")
            if refresh:
                await api.post("/auth/logout", json={"refresh_token": refresh})
            report["finished_at"] = datetime.now(UTC).isoformat()
            report["elapsed_seconds"] = round(time.monotonic() - start, 2)
            await save()
    print(json.dumps({"status": report["status"], "report": str(output)}), flush=True)
    return report["status"] == "passed"


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
