import hashlib
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.leetcode import PublicProblem
from app.ingestion.titles import display_title
from app.ingestion.workbook import WorkbookData
from app.models import Difficulty, Language, Question
from app.schemas import QuestionExample, QuestionInterface, QuestionSource


def question_id(number: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://leetcode.com/problemset/quest/{number}")


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workbook: str
    workbook_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    worksheet: str
    row: int = Field(ge=2)
    workbook_title: str
    workbook_difficulty: Difficulty
    statement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CatalogQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    slug: str = Field(max_length=150, pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=250)
    difficulty: Difficulty
    statement: str = Field(min_length=1, max_length=65536)
    tags: list[str]
    source: QuestionSource
    provenance: Provenance
    supported_languages: list[Language] | None
    examples: list[QuestionExample] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    interface: QuestionInterface | None = None

    @model_validator(mode="after")
    def validate_identity_and_statement(self) -> "CatalogQuestion":
        if self.id != question_id(self.source.frontend_id):
            raise ValueError("Catalog identity does not match the source question")
        if hashlib.sha256(self.statement.encode()).hexdigest() != self.provenance.statement_sha256:
            raise ValueError("Statement does not match the preserved workbook cell")
        if not self.statement.strip() or "\x00" in self.statement:
            raise ValueError("Invalid question statement")
        if self.source.url != f"https://leetcode.com/problems/{self.source.slug}/":
            raise ValueError("Invalid official source URL")
        return self

    def content(self) -> dict[str, Any]:
        return {
            "source": self.source.model_dump(mode="json"),
            "ingestion": self.provenance.model_dump(mode="json"),
            "supported_languages": [item.value for item in self.supported_languages]
            if self.supported_languages is not None
            else None,
            "examples": [item.model_dump() for item in self.examples],
            "constraints": self.constraints,
            "interface": self.interface.model_dump() if self.interface else None,
            "hints": [],
            "explanation": None,
            "starter_code": {},
        }


class CatalogBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    fetched_at: datetime
    questions: list[CatalogQuestion] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_unique_sources(self) -> "CatalogBundle":
        if len({q.source.frontend_id for q in self.questions}) != len(self.questions):
            raise ValueError("Duplicate source IDs in catalog")
        if len({q.slug for q in self.questions}) != len(self.questions):
            raise ValueError("Duplicate slugs in catalog")
        return self


def build_bundle(
    workbook: WorkbookData,
    catalog: dict[int, PublicProblem],
    details: dict[int, dict[str, Any]],
) -> CatalogBundle:
    questions = []
    for row in workbook.problems:
        source = catalog[row.number]
        extra = details.get(row.number, {})
        status = "premium" if source.isPaidOnly else extra.get("status", "unavailable")
        questions.append(
            CatalogQuestion(
                id=question_id(row.number),
                slug=f"leetcode-{row.number:03d}-{source.titleSlug}",
                title=display_title(source.titleSlug, source.title),
                difficulty=source.level,
                statement=row.statement,
                tags=[tag["slug"] for tag in source.topicTags],
                source=QuestionSource(
                    provider="leetcode",
                    frontend_id=row.number,
                    title=source.title,
                    slug=source.titleSlug,
                    url=f"https://leetcode.com/problems/{source.titleSlug}/",
                    premium=source.isPaidOnly,
                    details_status=status,
                ),
                provenance=Provenance(
                    workbook=workbook.filename,
                    workbook_sha256=workbook.sha256,
                    worksheet=workbook.sheet,
                    row=row.row,
                    workbook_title=row.title,
                    workbook_difficulty=row.difficulty,
                    statement_sha256=hashlib.sha256(row.statement.encode()).hexdigest(),
                ),
                supported_languages=extra.get("supported_languages")
                if status == "public"
                else None,
                examples=extra.get("examples", []),
                constraints=extra.get("constraints", []),
                interface=extra.get("interface"),
            )
        )
    return CatalogBundle(fetched_at=datetime.now(UTC), questions=questions)


async def onboard(
    sessions: async_sessionmaker[AsyncSession],
    bundle: CatalogBundle,
) -> dict[str, int]:
    created = updated = unchanged = 0
    async with sessions() as session, session.begin():
        # Serialize ingestion without changing schema or affecting submission workers.
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 846219340152})
        records = list(
            await session.scalars(
                select(Question)
                .where(Question.id.in_([item.id for item in bundle.questions]))
                .with_for_update()
            )
        )
        existing = {row.id: row for row in records}
        for item in bundle.questions:
            row = existing.get(item.id)
            if row:
                saved = row.content.get("source", {})
                if (
                    saved.get("provider") != "leetcode"
                    or saved.get("frontend_id") != item.source.frontend_id
                ):
                    raise ValueError(f"Conflicting question identity {item.source.frontend_id}")
                saved_hash = row.content.get("ingestion", {}).get("statement_sha256")
                actual_hash = hashlib.sha256(row.statement.encode()).hexdigest()
                if actual_hash not in (saved_hash, item.provenance.statement_sha256):
                    raise ValueError(
                        f"Question {item.source.frontend_id} has manual edits; import aborted"
                    )
            content = item.content()
            if row and row.content.get("judging"):
                if any(
                    row.content.get(key) != content.get(key) for key in ("interface", "constraints")
                ):
                    raise ValueError(
                        f"Question {item.source.frontend_id} judging contract needs review"
                    )
                content["judging"] = row.content["judging"]
                content["starter_code"] = row.content.get("starter_code", {})
            values = dict(
                slug=item.slug,
                title=item.title,
                difficulty=item.difficulty,
                statement=item.statement,
                tags=item.tags,
                content=content,
                published=True,
            )
            if row is None:
                session.add(Question(id=item.id, cpu_seconds=2, memory_kb=131072, **values))
                created += 1
            elif all(getattr(row, key) == value for key, value in values.items()):
                unchanged += 1
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                updated += 1
        # No TestCase rows are fabricated from function examples. Existing cases are untouched.
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "total": len(bundle.questions),
    }
