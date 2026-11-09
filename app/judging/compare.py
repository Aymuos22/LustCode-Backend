import json
import math
from typing import Any

from app.judging.contracts import JudgeProfile, arguments


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def _same(actual: Any, expected: Any, *, floating: bool = False) -> bool:
    if floating and type(actual) in (int, float) and type(expected) in (int, float):
        return math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-5)
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same(a, b, floating=floating) for a, b in zip(actual, expected, strict=True)
        )
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _same(actual[k], v, floating=floating) for k, v in expected.items()
        )
    return actual == expected


def compare_output(
    stdout: str | None, expected_output: str, stdin: str, profile: JudgeProfile
) -> bool:
    try:
        actual = json.loads(
            stdout or "", parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
        )
        expected = json.loads(expected_output)
        args = arguments(stdin, profile)
        rule = profile.comparison
        if rule == "gray":
            if (
                not isinstance(actual, list)
                or len(actual) != 1 << args[0]
                or not actual
                or actual[0] != 0
            ):
                return False
            return (
                all(type(x) is int and 0 <= x < 1 << args[0] for x in actual)
                and len(set(actual)) == len(actual)
                and all(
                    (x ^ y).bit_count() == 1
                    for x, y in zip(actual, actual[1:] + actual[:1], strict=True)
                )
            )
        if rule == "balanced_bst":
            if not isinstance(actual, list) or any(
                x is not None and type(x) is not int for x in actual
            ):
                return False
            if not actual:
                return args[0] == []
            if actual[0] is None:
                return False
            from app.judging.extra_references import serialize, traversal, tree

            root = tree(actual)
            trimmed = actual[:]
            while trimmed and trimmed[-1] is None:
                trimmed.pop()
            if serialize(root) != trimmed or traversal(root) != args[0]:
                return False

            def height(node: Any) -> int:
                if not node:
                    return 0
                left, right = height(node[1]), height(node[2])
                if left < 0 or right < 0 or abs(left - right) > 1:
                    return -1
                return 1 + max(left, right)

            return height(root) >= 0
        if rule == "alien":
            if expected == "":
                return actual == ""
            alphabet = {c for word in args[0] for c in word}
            if (
                not isinstance(actual, str)
                or len(actual) != len(alphabet)
                or set(actual) != alphabet
            ):
                return False
            positions = {c: i for i, c in enumerate(actual)}
            for left, right in zip(args[0], args[0][1:], strict=False):
                if len(left) > len(right) and left.startswith(right):
                    return False
                pair = next(((x, y) for x, y in zip(left, right, strict=False) if x != y), None)
                if pair and positions[pair[0]] >= positions[pair[1]]:
                    return False
            return True
        if rule == "wiggle":
            return (
                isinstance(actual, list)
                and all(type(x) is int for x in actual)
                and sorted(actual) == sorted(args[0])
                and all(
                    (x <= y if i % 2 == 0 else x >= y)
                    for i, (x, y) in enumerate(zip(actual, actual[1:], strict=False))
                )
            )
        if rule == "topological":
            if expected == []:
                return actual == []
            if not isinstance(actual, list) or len(actual) != args[0]:
                return False
            if any(type(v) is not int for v in actual) or set(actual) != set(range(args[0])):
                return False
            position = {v: i for i, v in enumerate(actual)}
            return all(position[before] < position[after] for after, before in args[1])
        if rule == "two_sum":
            return (
                isinstance(actual, list)
                and len(actual) == 2
                and all(type(x) is int and 0 <= x < len(args[0]) for x in actual)
                and actual[0] != actual[1]
                and args[0][actual[0]] + args[0][actual[1]] == args[1]
            )
        if rule == "palindrome":
            return (
                isinstance(actual, str)
                and actual in args[0]
                and actual == actual[::-1]
                and len(actual) == len(expected)
            )
        if rule == "peak":
            return (
                type(actual) is int
                and 0 <= actual < len(args[0])
                and (actual == 0 or args[0][actual] > args[0][actual - 1])
                and (actual == len(args[0]) - 1 or args[0][actual] > args[0][actual + 1])
            )
        if rule == "remove_element":
            if not isinstance(actual, dict) or type(actual.get("length")) is not int:
                return False
            return actual["length"] == expected["length"] and sorted(
                _json(x) for x in actual["values"]
            ) == sorted(_json(x) for x in expected["values"])
        if rule in {"unordered", "nested_unordered", "groups"}:
            if not isinstance(actual, list) or not isinstance(expected, list):
                return False
            if rule in {"nested_unordered", "groups"}:
                if not all(isinstance(x, list) for x in actual):
                    return False
                actual = [sorted(_json(v) for v in x) for x in actual]
                expected = [sorted(_json(v) for v in x) for x in expected]
            return sorted(_json(x) for x in actual) == sorted(_json(x) for x in expected)
        return _same(actual, expected, floating=rule == "float")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        return False
