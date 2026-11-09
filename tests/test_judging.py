import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.ingestion.catalog import CatalogBundle
from app.judging.compare import compare_output
from app.judging.contracts import JudgeProfile, arguments
from app.judging.drivers import build_source
from app.judging.suites import build_suites, parse_value
from app.judging.wire import INVALID_RESULT
from app.models import Language
from app.schemas import FunctionParameter, FunctionSignature
from tests.judging_reference_solutions import python_solution


@pytest.fixture(scope="module")
def suites():
    bundle = CatalogBundle.model_validate_json(
        Path("data/questions/leetcode_001_300.json").read_text()
    )
    return build_suites(bundle)


def test_all_suites_crosscheck_public_examples_and_have_private_boundaries(suites):
    assert len(suites) == 283
    for suite in suites.values():
        profile = suite["profile"]
        assert profile.test_count == len(suite["cases"])
        assert any(not c["hidden"] for c in suite["cases"])
        assert sum(c["hidden"] for c in suite["cases"]) >= 2
        assert len({c["stdin"] for c in suite["cases"]}) == len(suite["cases"])
        for case in suite["cases"]:
            assert compare_output(
                case["expected_output"], case["expected_output"], case["stdin"], profile
            )
            assert not compare_output("null", case["expected_output"], case["stdin"], profile)
            for language in Language:
                source = build_source(
                    suite["starter_code"][language.value], language, case["stdin"], profile
                )
                assert profile.signature.name in source
                if language == Language.PYTHON:
                    compile(source, "<trusted-driver-validation>", "exec")


@pytest.mark.parametrize(
    "actual,accepted",
    [
        ("[1,0]", True),
        ("[0,1]", True),
        ("[0,0]", False),
        ("[true,0]", False),
        ("[0,2]", False),
        ("[1.0,0]", False),
        ("[0,-1]", False),
        ("null", False),
        ("[0,1] extra output", False),
    ],
)
def test_two_sum_accepts_either_order_but_checks_indices(suites, actual, accepted):
    profile = suites[1]["profile"]
    assert compare_output(actual, "[0,1]", "[[2,7,11],9]", profile) is accepted


def test_order_rules_preserve_multiplicity_and_type(suites):
    profile = suites[15]["profile"]
    assert compare_output("[[1,-1,0]]", "[[-1,0,1]]", "[[-1,0,1]]", profile)
    assert not compare_output("[[1,-1,0],[1,-1,0]]", "[[-1,0,1]]", "[[-1,0,1]]", profile)
    assert not compare_output("[[true,-1,0]]", "[[-1,0,1]]", "[[-1,0,1]]", profile)
    assert not compare_output("[true]", "[1]", "[[1,2],0]", suites[1]["profile"])


def test_alternative_optima_float_precision_and_topological_order(suites):
    assert compare_output('"aba"', '"bab"', '["babad"]', suites[5]["profile"])
    assert not compare_output('"a"', '"bab"', '["babad"]', suites[5]["profile"])
    assert compare_output("1.50000001", "1.5", "[[1],[2]]", suites[4]["profile"])
    for value in ["NaN", "Infinity", "1e999", "null", "true"]:
        assert not compare_output(value, "1.5", "[[1],[2]]", suites[4]["profile"])
    assert compare_output(
        "[0,2,1,3]", "[0,1,2,3]", "[4,[[1,0],[2,0],[3,1],[3,2]]]", suites[210]["profile"]
    )
    assert not compare_output(
        "[3,2,1,0]", "[0,1,2,3]", "[4,[[1,0],[2,0],[3,1],[3,2]]]", suites[210]["profile"]
    )


def test_prefix_checks_length_and_remaining_elements(suites):
    profile = suites[27]["profile"]
    assert compare_output(
        '{"length":2,"values":[4,2]}', '{"length":2,"values":[2,4]}', "[[3,2,4,3],3]", profile
    )
    assert not compare_output(
        '{"length":2,"values":[2,2]}', '{"length":2,"values":[2,4]}', "[[3,2,4,3],3]", profile
    )


def test_untrusted_input_cannot_be_executed_by_contract_or_example_parser(suites):
    profile = suites[1]["profile"]
    for value in ["[[],true]", "[[],1,2]", '{"nums":[]}', "[[],NaN]"]:
        with pytest.raises(ValueError):
            arguments(value, profile)
    with pytest.raises(ValueError):
        parse_value("__import__('os').system('false')")
    assert parse_value('["null",null,true,false]') == ["null", None, True, False]
    bad = profile.model_dump()
    bad["signature"]["name"] = "f();system(1)"
    with pytest.raises(ValidationError):
        JudgeProfile.model_validate(bad)


def test_hidden_expected_answers_are_absent_from_generated_source(suites):
    profile = suites[3]["profile"]
    for language in Language:
        source = build_source(
            suites[3]["starter_code"][language.value], language, '["abc"]', profile
        )
        assert "expected_output" not in source
        assert "123456789" not in source


def test_string_literal_injection_is_quoted_for_each_language():
    profile = JudgeProfile(
        signature=FunctionSignature(
            name="solve",
            parameters=[FunctionParameter(name="s", type="string")],
            return_type="string",
        ),
        suite_version="test",
        test_count=2,
    )
    value = '"; throw new Error(); //\n\\u0022\x00é'
    for language in Language:
        source = build_source("", language, json.dumps([value]), profile)
        assert source
        if language == Language.PYTHON:
            compile(source, "<trusted-driver>", "exec")


def test_every_python_driver_executes_trusted_reference_programs_against_entire_suite(suites):
    for number, suite in suites.items():
        for case in suite["cases"]:
            source = build_source(
                python_solution(number, suite["profile"]),
                Language.PYTHON,
                case["stdin"],
                suite["profile"],
            )
            output = io.StringIO()
            # These programs are repository-authored test fixtures. Submitted user
            # source is executed only remotely, inside Judge0's sandbox.
            with contextlib.redirect_stdout(output), patch("sys.stdin", io.StringIO(case["stdin"])):
                exec(compile(source, "<trusted-reference-driver>", "exec"), {})
            assert compare_output(
                output.getvalue(), case["expected_output"], case["stdin"], suite["profile"]
            ), number


def test_large_inputs_travel_through_stdin_without_expanding_source(suites):
    profile = suites[238]["profile"]
    small = "[[1,2,3]]"
    large = json.dumps([[1] * 9000])
    for language in Language:
        starter = suites[238]["starter_code"][language.value]
        assert build_source(starter, language, small, profile) == build_source(
            starter, language, large, profile
        )


@pytest.mark.parametrize(
    "number,source,stdin",
    [
        (133, "class Solution:\n    def cloneGraph(self,node): return node\n", "[[[2],[1]]]"),
        (138, "class Solution:\n    def copyRandomList(self,head): return head\n", "[[1],[0]]"),
        (
            24,
            "class Solution:\n    def swapPairs(self,head): "
            "head.val,head.next.val=head.next.val,head.val;return head\n",
            "[[1,2]]",
        ),
    ],
)
def test_aliases_and_value_rewrites_are_rejected_by_special_drivers(suites, number, source, stdin):
    output = io.StringIO()
    with (
        contextlib.redirect_stdout(output),
        patch("sys.stdin", io.StringIO(stdin)),
    ):
        exec(
            compile(
                build_source(source, Language.PYTHON, stdin, suites[number]["profile"]),
                "<trusted-bad-fixture>",
                "exec",
            ),
            {},
        )
    assert output.getvalue().strip() == INVALID_RESULT


def test_full_output_is_preserved_for_comparison_before_diagnostic_truncation():
    import base64

    from app.integrations.judge0 import decode_text

    value = "[" + ",".join(["1"] * 9000) + "]"
    encoded = base64.b64encode(value.encode()).decode()
    assert len(decode_text(encoded)) == 16384
    assert decode_text(encoded, limit=None) == value


def test_debug_prints_do_not_override_returned_function_results(suites):
    source = (
        "class Solution:\n    def twoSum(self,nums,target):\n"
        '        print("debug: not an answer")\n        return [1,0]\n'
    )
    output = io.StringIO()
    diagnostics = io.StringIO()
    with (
        contextlib.redirect_stdout(output),
        contextlib.redirect_stderr(diagnostics),
        patch("sys.stdin", io.StringIO("[[2,7],9]")),
    ):
        exec(
            compile(
                build_source(source, Language.PYTHON, "[[2,7],9]", suites[1]["profile"]),
                "<trusted-debug-fixture>",
                "exec",
            ),
            {},
        )
    assert compare_output(output.getvalue(), "[0,1]", "[[2,7],9]", suites[1]["profile"])
    assert "debug" in diagnostics.getvalue() and "debug" not in output.getvalue()


@pytest.mark.parametrize(
    "number,args",
    [
        (8, ["\t42"]),
        (10, ["", "a*"]),
        (15, [[1, 2]]),
        (17, [""]),
        (27, [[-1], 1]),
        (39, [[1, 2], 3]),
        (50, [4.0, 8]),
        (50, [0.0, 0]),
        (65, ["1_0"]),
        (101, [[]]),
        (147, [[]]),
        (173, [["BSTIterator", "hasNext"], [[[]], []]]),
        (188, [0, [1, 3]]),
        (190, [1]),
        (191, [0]),
        (216, [1, 9]),
        (234, [[-1]]),
        (242, ["", "a"]),
        (257, [[]]),
        (284, [["PeekingIterator", "hasNext"], [[[]], []]]),
        (295, [["MedianFinder", "addNum", "findMedian"], [[], [2147483647], []]]),
        (225, [["MyStack", "push"], [[], [0]]]),
        (232, [["MyQueue", "push"], [[], [0]]]),
    ],
)
def test_test_fixtures_cannot_exceed_the_public_problem_domain(suites, number, args):
    from app.judging.domains import validate_public_domain

    source = CatalogBundle.model_validate_json(
        Path("data/questions/leetcode_001_300.json").read_text()
    ).questions[number - 1]
    with pytest.raises(ValueError):
        validate_public_domain(number, args, suites[number]["profile"], source.constraints)


def test_public_bound_parser_never_executes_document_instructions():
    from app.judging.domains import _number

    with pytest.raises(ValueError):
        _number("__import__('os').system('false')")


def test_tree_codec_expected_values_use_canonical_tree_serialization():
    from app.judging.special import reference

    assert reference(297, [[1, None, None]]) == [1]
