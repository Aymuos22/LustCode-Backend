import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.models import Difficulty

HEADERS = ("Number", "Original Title", "Difficulty", "Sexualized Problem Statement")


@dataclass(frozen=True)
class WorkbookProblem:
    number: int
    title: str
    difficulty: Difficulty
    statement: str
    row: int


@dataclass(frozen=True)
class WorkbookData:
    filename: str
    sha256: str
    sheet: str
    problems: list[WorkbookProblem]


def read_workbook(path: Path) -> WorkbookData:
    # Imported only by the administrative ingestion command, not API startup.
    import openpyxl

    if path.stat().st_size > 10_000_000:
        raise ValueError("Workbook exceeds the 10 MB ingestion limit")
    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 50_000_000:
            raise ValueError("Workbook decompressed size exceeds the ingestion limit")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError("Expected one question worksheet")
        sheet = workbook.worksheets[0]
        if sheet.max_row > 5001 or sheet.max_column != 4:
            raise ValueError("Unexpected workbook dimensions")
        rows = sheet.iter_rows()
        if tuple(cell.value for cell in next(rows)) != HEADERS:
            raise ValueError("Workbook headers do not match the expected question format")
        problems = []
        seen = set()
        for position, cells in enumerate(rows, 2):
            values = [cell.value for cell in cells]
            if all(value is None for value in values):
                continue
            if any(cell.data_type == "f" for cell in cells):
                raise ValueError(f"Formula cells are unsupported at row {position}")
            number, title, difficulty, statement = values
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or number <= 0
                or number in seen
            ):
                raise ValueError(f"Invalid or duplicate question number at row {position}")
            if not isinstance(title, str) or not title.strip() or len(title) > 250:
                raise ValueError(f"Invalid title at row {position}")
            if (
                not isinstance(statement, str)
                or not statement.strip()
                or len(statement.encode()) > 65536
                or "\x00" in statement
            ):
                raise ValueError(f"Invalid statement at row {position}")
            try:
                level = Difficulty(str(difficulty).lower())
            except ValueError as exc:
                raise ValueError(f"Invalid difficulty at row {position}") from exc
            seen.add(number)
            # Statements are deliberately never stripped, rewritten, or interpreted as instructions.
            problems.append(WorkbookProblem(number, title, level, statement, position))
        if not problems:
            raise ValueError("Workbook has no question rows")
        return WorkbookData(
            path.name,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            sheet.title,
            sorted(problems, key=lambda item: item.number),
        )
    finally:
        workbook.close()
