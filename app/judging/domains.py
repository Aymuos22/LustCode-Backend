"""Validate supported public numeric, length and node bounds without executing source text."""

import ast
import math
import re
from collections import Counter
from typing import Any, cast

from app.judging.contracts import JudgeProfile


def _number(expression: str) -> float:
    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return cast(int | float, node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Pow)
        ):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if abs(right) > 64:
                raise ValueError("Unsupported bound")
            return left**right
        raise ValueError("Unsupported bound expression")

    return visit(ast.parse(expression.strip().rstrip(".").replace("^", "**"), mode="eval").body)


def _values(subject: str, context: dict[str, Any], nodes: list[int]) -> list[Any] | None:
    subject = subject.strip()
    if subject.endswith(".val"):
        return nodes or None
    if subject in context:
        value = context[subject]
        return [value] if type(value) in (int, float) else None
    length = subject.endswith(".length")
    base = subject[:-7] if length else subject
    name = base.split("[")[0]
    if name not in context:
        return None
    values = [context[name]]
    for _ in range(base.count("[")):
        if not all(isinstance(v, list) for v in values):
            return None
        values = [item for value in values for item in value]
    if length:
        return (
            [len(value) for value in values]
            if all(isinstance(v, (list, str)) for v in values)
            else None
        )
    return values if all(type(value) in (int, float) for value in values) else None


def _validate_context(
    number: int, constraints: list[str], params: list[Any], args: list[Any]
) -> None:
    context = {p.name: v for p, v in zip(params, args, strict=True)}
    nodes = []
    node_lengths = []
    for p, value in zip(params, args, strict=True):
        if p.type in {"TreeNode", "ListNode"}:
            entries = [v for v in value if v is not None]
            nodes.extend(entries)
            node_lengths.append(len(entries))
        if p.type == "Iterator":
            context["nums"] = value
    for line in constraints:
        alias = re.fullmatch(r"\s*([a-zA-Z_]\w*)\s*==\s*(.+?)\s*", line)
        if alias:
            value = _values(alias[2], context, nodes)
            if value and len(set(value)) == 1:
                context.setdefault(alias[1], value[0])
    for line in constraints:
        if line.startswith("The number of nodes") and "range" in line:
            match = re.search(r"\[([^,]+),([^\]]+)\]", line)
            if match:
                try:
                    low, high = _number(match[1]), _number(match[2])
                except (ValueError, SyntaxError):
                    continue
                if any(not low <= n <= high for n in node_lengths):
                    raise ValueError(f"Question {number}: node count violates public constraints")
        match = re.fullmatch(r"\s*(.+?)\s*(<=|<)\s*([^<>]+?)\s*(<=|<)\s*(.+?)\s*", line)
        if not match:
            continue
        try:
            low, high = _number(match[1]), _number(match[5])
        except (ValueError, SyntaxError, OverflowError):
            continue
        for subject in match[3].split(","):
            values = _values(subject, context, nodes)
            if values is None:
                continue
            for value in values:
                if not (
                    (low <= value if match[2] == "<=" else low < value)
                    and (value <= high if match[4] == "<=" else value < high)
                ):
                    raise ValueError(
                        f"Question {number}: {subject.strip()} violates public constraints"
                    )


def validate_public_domain(
    number: int, args: list[Any], profile: JudgeProfile, constraints: list[str]
) -> None:
    if profile.origin == "lustcode":
        return
    if profile.protocol == "design":
        assert profile.design and profile.design.constructor
        methods = {m.name: m for m in profile.design.methods}
        for i, (name, values) in enumerate(zip(args[0], args[1], strict=True)):
            method = profile.design.constructor if i == 0 else methods[name]
            _validate_context(number, constraints, method.parameters, values)
        return
    _validate_context(number, constraints, profile.signature.parameters, args)
    if number == 8 and any(
        not (c.isascii() and (c.isalpha() or c.isdigit() or c in " +-.")) for c in args[0]
    ):
        raise ValueError("Question 8: character outside public alphabet")
    if number == 65 and any(
        not (c.isascii() and (c.isalpha() or c.isdigit() or c in "+-.")) for c in args[0]
    ):
        raise ValueError("Question 65: character outside public alphabet")
    if number == 50 and args[0] == 0 and args[1] <= 0:
        raise ValueError("Question 50: zero base requires a positive exponent")
    if number == 50 and (not math.isfinite(args[0] ** args[1]) or abs(args[0] ** args[1]) > 10000):
        raise ValueError("Question 50: result outside promised numeric range")
    if number == 190 and args[0] % 2:
        raise ValueError("Question 190: public contract requires an even integer")
    if number == 76:
        text, wanted = args[0], Counter(args[1])
        windows = []
        for i in range(len(text)):
            for j in range(i + 1, len(text) + 1):
                if not wanted - Counter(text[i:j]):
                    windows.append(text[i:j])
        if windows:
            length = min(map(len, windows))
            if len({w for w in windows if len(w) == length}) > 1:
                raise ValueError("Question 76: public contract promises a unique answer")
