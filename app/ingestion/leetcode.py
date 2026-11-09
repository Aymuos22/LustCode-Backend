import asyncio
import json
import re
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.models import Difficulty, Language
from app.schemas import FunctionParameter, FunctionSignature, QuestionExample, QuestionInterface

ENDPOINT = "https://leetcode.com/graphql/"
LANGUAGES = {"python3": Language.PYTHON, "java": Language.JAVA, "cpp": Language.CPP}


class PublicProblem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questionFrontendId: str
    title: str = Field(min_length=1, max_length=250)
    titleSlug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=130)
    difficulty: str
    isPaidOnly: bool
    topicTags: list[dict[str, str]]

    @property
    def number(self) -> int:
        return int(self.questionFrontendId)

    @property
    def level(self) -> Difficulty:
        return Difficulty(self.difficulty.lower())


class PlainHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.ignored += 1
        elif not self.ignored:
            if tag in ("p", "pre", "li", "div", "br", "tr", "h1", "h2", "h3"):
                self.parts.append("\n")
            elif tag == "sup":
                self.parts.append("^(")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.ignored = max(0, self.ignored - 1)
        elif not self.ignored:
            if tag in ("p", "pre", "li", "div", "tr", "h1", "h2", "h3"):
                self.parts.append("\n")
            elif tag == "sup":
                self.parts.append(")")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\n\s*\n", "\n", "".join(self.parts).replace("\xa0", " ")).strip()


def public_examples_and_constraints(html: str) -> tuple[list[QuestionExample], list[str]]:
    parser = PlainHTML()
    parser.feed(html)
    value = parser.text()
    examples = []
    pattern = (
        r"(?:^|\n)Input\s*:?\s*(.*?)\s*(?:^|\n)Output\s*:?\s*(.*?)"
        r"(?=\s*\b(?:Explanation\b|Example\s+\d+\s*:|Constraints:|Follow.up:)|\Z)"
    )
    for match in re.finditer(pattern, value, re.S | re.I):
        sample_input, output = (item.strip() for item in match.groups())
        if sample_input and output and len(sample_input) <= 16384 and len(output) <= 16384:
            examples.append(QuestionExample(input=sample_input, output=output))
    constraints = []
    section = re.search(r"\bConstraints:\s*(.*?)(?=\bFollow.up:|\Z)", value, re.S | re.I)
    if section:
        constraints = [line.strip() for line in section[1].splitlines() if line.strip()]
    # These are factual restrictions and example input/output only. Description prose,
    # explanations, editorials, images, scripts, and solutions are never retained.
    return examples[:20], constraints[:30]


def function_signature(value: dict[str, Any]) -> FunctionSignature | None:
    if not isinstance(value.get("name"), str):
        return None
    return FunctionSignature(
        name=value["name"],
        parameters=[
            FunctionParameter(name=param["name"], type=param["type"])
            for param in value.get("params", [])
            if isinstance(param, dict)
            and isinstance(param.get("name"), str)
            and isinstance(param.get("type"), str)
        ],
        return_type=(value.get("return") or {}).get("type"),
    )


def public_interface(metadata: str | None, languages: list[str]) -> QuestionInterface | None:
    if any(lang in languages for lang in ("mysql", "mssql", "oraclesql", "postgresql")):
        return QuestionInterface(kind="sql")
    if "bash" in languages:
        return QuestionInterface(kind="shell")
    if not metadata:
        return None
    value = json.loads(metadata)
    if not isinstance(value, dict):
        raise ValueError("Invalid public function metadata")
    if "methods" in value:
        methods = [method for item in value["methods"] if (method := function_signature(item))]
        class_name = value.get("classname") or value.get("name")
        constructor = function_signature({**(value.get("constructor") or {}), "name": class_name})
        return QuestionInterface(
            kind="design", class_name=class_name, constructor=constructor, methods=methods
        )
    name = value.get("name", "")
    if value.get("manual") and name and name[0].isupper():
        return QuestionInterface(kind="design", class_name=name)
    signature = function_signature(value)
    return (
        QuestionInterface(kind="function", class_name="Solution", function=signature)
        if signature
        else None
    )


class LeetCodePublicClient:
    def __init__(self, http: httpx.AsyncClient, *, pause_seconds: float = 0.5) -> None:
        self.http = http
        self.pause_seconds = pause_seconds

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(3):
            try:
                async with asyncio.timeout(30):
                    response = await self.http.post(
                        ENDPOINT,
                        json={"query": query, "variables": variables or {}},
                        headers={
                            "Referer": "https://leetcode.com/problemset/",
                            "User-Agent": "LustCode public metadata importer",
                        },
                    )
                if response.status_code == 429:
                    try:
                        wait = min(max(int(response.headers.get("Retry-After", "60")), 1), 300)
                    except ValueError:
                        wait = 60
                    if attempt == 2:
                        raise ValueError("LeetCode rate limited the public metadata import")
                    await asyncio.sleep(wait)
                    continue
                if response.status_code in (401, 403):
                    raise ValueError(
                        "Public metadata access denied; protected-content fallback is disabled"
                    )
                response.raise_for_status()
                value = response.json()
                if value.get("errors") or not isinstance(value.get("data"), dict):
                    raise ValueError("LeetCode returned invalid public GraphQL data")
                return value["data"]
            except (httpx.HTTPError, TimeoutError):
                if attempt == 2:
                    raise ValueError("Public LeetCode metadata request failed") from None
                await asyncio.sleep(2**attempt)
        raise ValueError("Public LeetCode metadata request failed")

    async def catalog(self, numbers: set[int]) -> dict[int, PublicProblem]:
        query = """query Catalog($skip:Int!) {
          questionList(categorySlug:"",limit:100,skip:$skip,
            filters:{orderBy:FRONTEND_ID,sortOrder:ASCENDING}) {
            data { questionFrontendId title titleSlug difficulty isPaidOnly topicTags {name slug} }
          }
        }"""
        found: dict[int, PublicProblem] = {}
        skip = 0
        while not numbers.issubset(found):
            items = (await self.query(query, {"skip": skip}))["questionList"]["data"]
            if not items:
                break
            for item in items:
                problem = PublicProblem.model_validate(item)
                if problem.number in numbers:
                    found[problem.number] = problem
            skip += len(items)
            if skip > 10000:
                break
            await asyncio.sleep(self.pause_seconds)
        if missing := numbers - found.keys():
            raise ValueError(f"Official catalog is missing question IDs: {sorted(missing)}")
        return found

    async def details(self, problems: list[PublicProblem]) -> dict[int, dict[str, Any]]:
        # Paid entries receive only public catalog metadata. Never ask for locked content.
        free = [problem for problem in problems if not problem.isPaidOnly]
        found: dict[int, dict[str, Any]] = {}
        fields = "questionFrontendId content metaData codeSnippets { langSlug }"
        for offset in range(0, len(free), 5):
            batch = free[offset : offset + 5]
            query = (
                "query PublicDetails {"
                + " ".join(
                    f"q{item.number}:question(titleSlug:{json.dumps(item.titleSlug)}){{{fields}}}"
                    for item in batch
                )
                + "}"
            )
            response = await self.query(query)
            for item in batch:
                value = response.get(f"q{item.number}")
                if not isinstance(value, dict) or str(value.get("questionFrontendId")) != str(
                    item.number
                ):
                    raise ValueError(f"Official detail ID mismatch for question {item.number}")
                html = value.get("content")
                languages = [entry["langSlug"] for entry in value.get("codeSnippets") or []]
                examples, constraints = public_examples_and_constraints(html) if html else ([], [])
                interface = public_interface(value.get("metaData"), languages)
                found[item.number] = {
                    "status": "public" if html else "unavailable",
                    "examples": [example.model_dump() for example in examples],
                    "constraints": constraints,
                    "supported_languages": [
                        language.value for slug, language in LANGUAGES.items() if slug in languages
                    ],
                    "interface": interface.model_dump() if interface else None,
                }
            print(f"Public metadata fetched: {min(offset + 5, len(free))}/{len(free)}", flush=True)
            await asyncio.sleep(self.pause_seconds)
        return found
