"""Build and atomically install independently checked private evaluation suites."""

import ast
import hashlib
import io
import json
import tokenize
from copy import deepcopy
from typing import Any, cast

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.catalog import CatalogBundle
from app.judging.cases import CASES
from app.judging.compare import compare_output
from app.judging.contracts import JudgeProfile, arguments, suite_hash
from app.judging.design import (
    CASES as DESIGN_CASES,
)
from app.judging.design import (
    PEEKING,
)
from app.judging.design import (
    reference as design_reference,
)
from app.judging.design import (
    starter as design_starter,
)
from app.judging.domains import validate_public_domain
from app.judging.drivers import type_name
from app.judging.generated_cases import generated_cases
from app.judging.independent import (
    CONTRACTS,
)
from app.judging.independent import (
    reference as independent_reference,
)
from app.judging.independent import (
    signature as independent_signature,
)
from app.judging.independent_cases import CASES as INDEPENDENT_CASES
from app.judging.references import reference
from app.judging.special import ADAPTERS, DESCRIPTIONS, FIXTURES, NATIVE
from app.judging.special import CASES as SPECIAL_CASES
from app.judging.special import reference as special_reference
from app.models import Language, Question, TestCase
from app.schemas import FunctionSignature

VERSION = "authored-v3-visible-samples"
PREFIX = {26, 27, 80}
MUTATING = {31, 48, 73, 75, 88, 189, 283, 289, 99, 114, 130, 143, 186, 280, 286, 37, 237}
UNORDERED = {17, 22, 30, 46, 47, 51, 93, 113, 126, 131, 140, 187, 212, 229, 241, 257, 260}
NESTED_UNORDERED = {15, 18, 39, 40, 77, 78, 90, 216}


def parse_value(text_value: str) -> Any:
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(text_value).readline):
        if token.type == tokenize.NAME and token.string in {"null", "true", "false"}:
            token = token._replace(
                string={"null": "None", "true": "True", "false": "False"}[token.string]
            )
        tokens.append(token)
    return ast.literal_eval(tokenize.untokenize(tokens))


def example_args(text_value: str, names: list[str]) -> list[Any]:
    expression = ast.parse("f(" + text_value + ")", mode="eval").body
    if not isinstance(expression, ast.Call) or expression.args:
        raise ValueError("Unrecognized example input")
    values = {kw.arg: parse_value(ast.unparse(kw.value)) for kw in expression.keywords}
    if set(values) != set(names):
        raise ValueError("Example names do not match the function contract")
    return [values[name] for name in names]


def starter_code(profile: JudgeProfile) -> dict[str, str]:
    if profile.protocol == "design":
        return design_starter(profile)
    if profile.adapter == "codec":
        return {
            ("python"): (
                "class Codec:\n    def serialize(self, root):\n        raise "
                "NotImplementedError\n\n    def deserialize(self, data):\n        raise "
                "NotImplementedError\n"
            ),
            ("cpp"): (
                "class Codec { public:\n    string serialize(TreeNode* root) { throw "
                'runtime_error("Implement"); }\n    TreeNode* deserialize(string data) '
                '{ throw runtime_error("Implement"); }\n};\n'
            ),
            ("java"): (
                "class Codec {\n    public String serialize(TreeNode root) { throw new "
                "UnsupportedOperationException(); }\n    public TreeNode "
                "deserialize(String data) { throw new UnsupportedOperationException(); "
                "}\n}\n"
            ),
        }
    signature = profile.native_signature or profile.signature
    python = (
        f"class Solution:\n    def {signature.name}(self"
        + "".join(f", {p.name}" for p in signature.parameters)
        + "):\n        raise NotImplementedError\n"
    )
    cpp_params = ", ".join(
        type_name(p.type, Language.CPP)
        + (
            "& "
            if p.type.endswith("[]") or p.type.startswith("list<") or p.type == "string"
            else " "
        )
        + p.name
        for p in signature.parameters
    )
    cpp = (
        "class Solution {\npublic:\n    "
        f"{type_name(signature.return_type or 'void', Language.CPP)} "
        f"{signature.name}({cpp_params}) {{\n"
        '        throw runtime_error("Implement your solution");\n    }\n};\n'
    )
    java_params = ", ".join(
        type_name(p.type, Language.JAVA) + " " + p.name for p in signature.parameters
    )
    java = (
        "class Solution {\n    public "
        f"{type_name(signature.return_type or 'void', Language.JAVA)} "
        f"{signature.name}({java_params}) {{\n"
        '        throw new UnsupportedOperationException("Implement your solution");\n    }\n}\n'
    )
    if profile.adapter == "bad_version":
        java = java.replace("class Solution {", "class Solution extends VersionControl {")
    return {"python": python, "cpp": cpp, "java": java}


def build_suites(bundle: CatalogBundle) -> dict[int, dict[str, Any]]:
    suites = {}
    for question in bundle.questions:
        number = question.source.frontend_id
        authored = INDEPENDENT_CASES.get(
            number, DESIGN_CASES.get(number, SPECIAL_CASES.get(number, CASES.get(number)))
        )
        if authored is None:
            continue
        independent = number in CONTRACTS
        design = (
            PEEKING if number == 284 else question.interface if number in DESIGN_CASES else None
        )
        if (
            not independent
            and not design
            and (not question.interface or not question.interface.function)
        ):
            raise ValueError(f"Missing independent contract for {number}")
        if independent:
            function = independent_signature(number)
        elif design:
            function = FunctionSignature(name=design.class_name, return_type="void")
        else:
            assert question.interface and question.interface.function
            function = FIXTURES.get(number, question.interface.function)
        oracle = (
            independent_reference
            if independent
            else design_reference
            if design
            else special_reference
            if number in SPECIAL_CASES
            else reference
        )
        comparison = {
            1: "two_sum",
            4: "float",
            5: "palindrome",
            27: "remove_element",
            49: "groups",
            50: "float",
            162: "peak",
            210: "topological",
        }.get(
            number,
            "unordered"
            if number in UNORDERED
            else "nested_unordered"
            if number in NESTED_UNORDERED
            else "exact",
        )
        comparison = {
            249: "groups",
            247: "unordered",
            254: "nested_unordered",
            267: "unordered",
            269: "alien",
            272: "unordered",
            280: "wiggle",
            293: "unordered",
            89: "gray",
            95: "unordered",
            108: "balanced_bst",
            109: "balanced_bst",
            282: "unordered",
            295: "float",
        }.get(number, comparison)
        profile = JudgeProfile(
            protocol="design" if design else "function",
            design=design,
            signature=function,
            native_signature=NATIVE.get(number),
            adapter=ADAPTERS.get(number, "normal"),
            origin="lustcode" if independent else "leetcode_public",
            description=(
                "Implement the class shown in the starter code. Fixtures contain "
                "operation names and argument arrays. Return values are checked after "
                "every operation; constructors and void methods produce null. Each "
                "fixture uses a fresh instance."
            )
            if design
            else CONTRACTS[number][3]
            if independent
            else DESCRIPTIONS.get(
                number,
                (
                    "Implement the supplied Solution method. Inputs and outputs follow "
                    "the public function signature. Array/list results use JSON; "
                    "linked lists use value arrays and trees use level-order arrays."
                ),
            ),
            comparison=comparison,
            result="prefix"
            if number in PREFIX
            else "mutated_first"
            if number in MUTATING
            else "return",
            suite_version=VERSION,
            test_count=2,
        )
        cases: list[dict[str, Any]] = []
        seen = set()
        for sample in question.examples:
            try:
                if design:
                    expressions = ast.parse(sample.input).body
                    if len(expressions) != 2 or not all(
                        isinstance(e, ast.Expr) for e in expressions
                    ):
                        raise ValueError("Invalid public operation example")
                    args = [parse_value(ast.unparse(cast(ast.Expr, e).value)) for e in expressions]
                else:
                    args = example_args(
                        sample.input, [p.name for p in profile.signature.parameters]
                    )
                expected = parse_value(sample.output)
            except (ValueError, SyntaxError, tokenize.TokenError):
                continue
            stdin = json.dumps(args, separators=(",", ":"), allow_nan=False)
            arguments(stdin, profile)
            validate_public_domain(number, args, profile, question.constraints)
            actual = oracle(number, deepcopy(args))
            if not compare_output(json.dumps(actual), json.dumps(expected), stdin, profile):
                raise ValueError(f"Independent oracle disagrees with public example for {number}")
            cases.append(
                {
                    "stdin": stdin,
                    "expected_output": json.dumps(expected, separators=(",", ":")),
                    "hidden": False,
                }
            )
            seen.add(stdin)
        for args in [*authored, *generated_cases(number)]:
            stdin = json.dumps(args, separators=(",", ":"), allow_nan=False)
            arguments(stdin, profile)
            validate_public_domain(number, args, profile, question.constraints)
            if stdin in seen:
                continue
            expected = oracle(number, deepcopy(args))
            cases.append(
                {
                    "stdin": stdin,
                    "expected_output": json.dumps(expected, separators=(",", ":"), allow_nan=False),
                    "hidden": True,
                }
            )
            seen.add(stdin)
        # Some reference examples do not match the fixture protocol (e.g. in-place
        # results), and independent contracts have no source examples. Publish one
        # independently validated authored fixture so every enabled question can run.
        if cases and not any(not case["hidden"] for case in cases):
            cases[0]["hidden"] = False
        if sum(case["hidden"] for case in cases) < 2:
            raise ValueError(f"Question {number} needs at least two independent private cases")
        profile = profile.model_copy(
            update={
                "test_count": len(cases),
                "suite_sha256": suite_hash(cases),
                "statement_sha256": question.provenance.statement_sha256,
            }
        )
        suites[number] = {
            "id": question.id,
            "profile": profile,
            "cases": cases,
            "starter_code": starter_code(profile),
            "statement_sha256": question.provenance.statement_sha256,
        }
    return suites


async def install_suites(
    sessions: async_sessionmaker[AsyncSession], suites: dict[int, dict[str, Any]]
) -> dict[str, int]:
    created = updated = unchanged = 0
    async with sessions() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 846219340152})
        ids = [suite["id"] for suite in suites.values()]
        questions = {
            q.id: q
            for q in await session.scalars(
                select(Question).where(Question.id.in_(ids)).with_for_update()
            )
        }
        existing: dict[Any, list[TestCase]] = {}
        for case in await session.scalars(
            select(TestCase)
            .where(TestCase.question_id.in_(ids))
            .order_by(TestCase.question_id, TestCase.position)
            .with_for_update()
        ):
            existing.setdefault(case.question_id, []).append(case)
        replacements = []
        pending: list[TestCase] = []
        for number, suite in suites.items():
            question = questions.get(suite["id"])
            if (
                question is None
                or hashlib.sha256(question.statement.encode()).hexdigest()
                != suite["statement_sha256"]
            ):
                raise ValueError(f"Question {number} is missing or has a different main statement")
            cases = existing.get(question.id, [])
            profile = suite["profile"].model_dump(mode="json")
            saved = [
                {"stdin": c.stdin, "expected_output": c.expected_output, "hidden": c.hidden}
                for c in cases
            ]
            same = saved == suite["cases"] and [c.position for c in cases] == list(
                range(len(cases))
            )
            if (
                same
                and question.content.get("judging") == profile
                and question.content.get("starter_code") == suite["starter_code"]
            ):
                unchanged += 1
                continue
            previous = question.content.get("judging") or {}
            if not isinstance(previous, dict):
                raise ValueError(f"Question {number} has an invalid stored contract")
            if cases and not previous:
                raise ValueError(
                    f"Question {number} has manually managed cases; refusing replacement"
                )
            if cases and suite_hash(saved) != previous.get("suite_sha256"):
                raise ValueError(f"Question {number} has manual test-case edits; import aborted")
            if cases:
                if not same:
                    replacements.append(question.id)
                updated += 1
            else:
                created += 1
            if not same:
                pending.extend(
                    TestCase(question_id=question.id, position=i, **case)
                    for i, case in enumerate(suite["cases"])
                )
            question.content = {
                **question.content,
                "judging": profile,
                "starter_code": suite["starter_code"],
            }
        if replacements:
            await session.execute(delete(TestCase).where(TestCase.question_id.in_(replacements)))
            await session.flush()
        session.add_all(pending)
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "questions": len(suites),
        "test_cases": sum(len(s["cases"]) for s in suites.values()),
    }
