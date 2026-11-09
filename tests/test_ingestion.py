import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import openpyxl
import pytest
from pydantic import ValidationError

from app.ingestion.catalog import CatalogBundle, build_bundle, question_id
from app.ingestion.leetcode import (
    LeetCodePublicClient,
    PublicProblem,
    public_examples_and_constraints,
    public_interface,
)
from app.ingestion.workbook import HEADERS, WorkbookData, WorkbookProblem, read_workbook
from app.models import Difficulty


def make_workbook(path: Path, rows: list[tuple], headers: tuple = HEADERS) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Provided questions"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def public_problem(
    number: int, *, premium: bool = False, title: str = "Official title"
) -> PublicProblem:
    return PublicProblem(
        questionFrontendId=str(number),
        title=title,
        titleSlug=f"problem-{number}",
        difficulty="Medium",
        isPaidOnly=premium,
        topicTags=[{"slug": "array", "name": "Array"}],
    )


def fixture_bundle(numbers: tuple[int, ...] = (1, 2)) -> CatalogBundle:
    workbook = WorkbookData(
        "provided.xlsx",
        "a" * 64,
        "Provided questions",
        [
            WorkbookProblem(
                number,
                f"Workbook title {number}",
                Difficulty.EASY,
                f"User-provided body {number}.\n  Exact whitespace retained.\n",
                index + 2,
            )
            for index, number in enumerate(numbers)
        ],
    )
    return build_bundle(
        workbook,
        {n: public_problem(n) for n in numbers},
        {
            n: {
                "status": "public",
                "examples": [{"input": "nums = [1,2]", "output": "3"}],
                "constraints": ["1 <= nums.length <= 100"],
                "supported_languages": ["python", "java", "cpp"],
            }
            for n in numbers
        },
    )


def test_workbook_preserves_original_body_exactly(tmp_path) -> None:
    body = "  User-authored body.\nSpecial characters: λ < > &\n"
    path = make_workbook(tmp_path / "source.xlsx", [(1, "Original", "Easy", body)])
    value = read_workbook(path)
    assert value.problems[0].statement == body
    assert value.problems[0].row == 2
    assert value.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "rows",
    [
        [(1, "Title", "Easy", "Body"), (1, "Duplicate", "Hard", "Other")],
        [(True, "Title", "Easy", "Body")],
        [(0, "Title", "Easy", "Body")],
        [(1, "", "Easy", "Body")],
        [(1, "Title", "Impossible", "Body")],
        [(1, "Title", "Easy", " ")],
        [(1, "Title", "Easy", "=1+1")],
    ],
)
def test_invalid_or_formula_workbook_rows_are_rejected(tmp_path, rows) -> None:
    path = make_workbook(tmp_path / "source.xlsx", rows)
    with pytest.raises(ValueError):
        read_workbook(path)


def test_unexpected_headers_and_empty_workbook_are_rejected(tmp_path) -> None:
    path = make_workbook(tmp_path / "source.xlsx", [], ("ID", "Title", "Difficulty", "Body"))
    with pytest.raises(ValueError, match="headers"):
        read_workbook(path)
    path = make_workbook(tmp_path / "empty.xlsx", [])
    with pytest.raises(ValueError, match="no question"):
        read_workbook(path)


def test_metadata_never_replaces_workbook_statement() -> None:
    bundle = fixture_bundle()
    item = bundle.questions[0]
    assert item.statement == "User-provided body 1.\n  Exact whitespace retained.\n"
    assert item.title == "Official title" and item.difficulty == Difficulty.MEDIUM
    assert item.provenance.workbook_title == "Workbook title 1"
    assert item.provenance.workbook_difficulty == Difficulty.EASY
    assert item.id == question_id(1)
    assert "ingestion" in item.content()
    assert item.content()["starter_code"] == {}


def test_premium_uses_only_public_catalog_metadata() -> None:
    data = WorkbookData(
        "source.xlsx",
        "b" * 64,
        "Sheet",
        [
            WorkbookProblem(
                2,
                "Provided title",
                Difficulty.HARD,
                "Supplied main body",
                2,
            )
        ],
    )
    record = build_bundle(data, {2: public_problem(2, premium=True)}, {}).questions[0]
    assert record.statement == "Supplied main body"
    assert record.source.premium and record.source.details_status == "premium"
    assert record.supported_languages is None and record.examples == []


def test_bundle_rejects_body_tampering_wrong_identity_and_duplicate_ids() -> None:
    value = fixture_bundle().model_dump(mode="json")
    value["questions"][0]["statement"] = "Replaced by external description"
    with pytest.raises(ValidationError, match="preserved workbook"):
        CatalogBundle.model_validate(value)
    value = fixture_bundle().model_dump(mode="json")
    value["questions"][0]["id"] = str(question_id(999))
    with pytest.raises(ValidationError, match="identity"):
        CatalogBundle.model_validate(value)
    value = fixture_bundle().model_dump(mode="json")
    value["questions"].append(value["questions"][0])
    with pytest.raises(ValidationError, match="Duplicate"):
        CatalogBundle.model_validate(value)


def test_public_html_retains_only_factual_examples_and_constraints() -> None:
    html = """<p>Official description must not become the main body.</p>
        <script>do not retain me</script><p><strong>Example 1:</strong></p>
        <pre><b>Input:</b> nums = [1,2]\n<b>Output:</b> 3\n<b>Explanation:</b> prose omitted</pre>
        <p><strong>Constraints:</strong></p>
        <ul><li>1 &lt;= nums.length &lt;= 10<sup>4</sup></li></ul>
        <p><b>Follow-up:</b> do not retain this paragraph</p>"""
    examples, constraints = public_examples_and_constraints(html)
    assert [item.model_dump() for item in examples] == [{"input": "nums = [1,2]", "output": "3"}]
    assert constraints == ["1 <= nums.length <= 10^(4)"]
    assert "prose" not in str(examples) and "script" not in str(constraints)


def test_design_example_labels_without_colons() -> None:
    html = (
        '<p>Example 1:</p><pre><strong>Input</strong>\n["Cache","get"]\n[[2],[1]]\n'
        "<strong>Output</strong>\n[null,-1]\n"
        "<strong>Explanation</strong>\nExplanation omitted</pre>"
    )
    examples, _ = public_examples_and_constraints(html)
    assert len(examples) == 1 and examples[0].output == "[null,-1]"


def test_design_metadata_includes_class_constructor_and_methods() -> None:
    interface = public_interface(
        json.dumps(
            {
                "classname": "Cache",
                "constructor": {"params": [{"name": "capacity", "type": "integer"}]},
                "methods": [
                    {
                        "name": "get",
                        "params": [{"name": "key", "type": "integer"}],
                        "return": {"type": "integer"},
                    },
                ],
            }
        ),
        ["python3"],
    )
    assert interface.kind == "design" and interface.class_name == "Cache"
    assert interface.constructor.name == "Cache"
    assert interface.constructor.parameters[0].name == "capacity"
    assert interface.methods[0].return_type == "integer"
    assert public_interface(None, ["mysql"]).kind == "sql"
    assert public_interface(None, ["bash"]).kind == "shell"
    assert public_interface('{"name":"CustomIterator","manual":true}', ["python3"]).kind == "design"


async def test_details_never_request_premium_content() -> None:
    def handler(request):
        query = json.loads(request.content)["query"]
        assert "problem-2" not in query and "problem-1" in query
        return httpx.Response(
            200,
            json={
                "data": {
                    "q1": {
                        "questionFrontendId": "1",
                        "content": "<p>Constraints:</p><li>n &gt; 0</li>",
                        "metaData": '{"name":"solve","params":[],"return":{"type":"integer"}}',
                        "codeSnippets": [{"langSlug": "python3"}, {"langSlug": "ruby"}],
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await LeetCodePublicClient(http, pause_seconds=0).details(
            [
                public_problem(1),
                public_problem(2, premium=True),
            ]
        )
    assert set(result) == {1}
    assert result[1]["supported_languages"] == ["python"]
    assert "content" not in result[1]


async def test_capped_catalog_pagination_matches_ids() -> None:
    offsets = []

    def handler(request):
        skip = json.loads(request.content)["variables"]["skip"]
        offsets.append(skip)
        payload = [public_problem(skip + 1).model_dump()] if skip < 2 else []
        return httpx.Response(200, json={"data": {"questionList": {"data": payload}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await LeetCodePublicClient(http, pause_seconds=0).catalog({1, 2})
    assert set(result) == {1, 2} and offsets == [0, 1]


@pytest.mark.parametrize("status", [401, 403])
async def test_access_denial_does_not_bypass_or_retry(status) -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError, match="access denied"):
            await LeetCodePublicClient(http).query("query {}")
    assert len(calls) == 1


async def test_rate_limit_respects_cooldown(monkeypatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr("app.ingestion.leetcode.asyncio.sleep", sleep)
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "3"})
            if len(calls) == 1
            else httpx.Response(200, json={"data": {"ok": True}})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await LeetCodePublicClient(http).query("query {}") == {"ok": True}
    sleep.assert_awaited_once_with(3)


async def test_invalid_graphql_or_wrong_detail_id_rejected() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"errors": [{"message": "private"}]})
        )
    ) as http:
        with pytest.raises(ValueError, match="invalid public"):
            await LeetCodePublicClient(http).query("query {}")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": {"q1": {"questionFrontendId": "99"}}})
        )
    ) as http:
        with pytest.raises(ValueError, match="ID mismatch"):
            await LeetCodePublicClient(http, pause_seconds=0).details([public_problem(1)])
