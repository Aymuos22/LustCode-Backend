"""Independently authored, bounded-input reference oracles for private suite construction.

Not imported by request handlers and never sent to submitted programs.
"""

import itertools
import math
import re
from collections import Counter
from functools import lru_cache
from typing import Any

from app.judging.extra_references import REFERENCES as EXTRA_REFERENCES


def _reference_1(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return next([i, j] for i in range(len(a)) for j in range(i + 1, len(a)) if a[i] + a[j] == b)


def _reference_3(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(
        (
            j - i
            for i in range(len(a) + 1)
            for j in range(i, len(a) + 1)
            if len(set(a[i:j])) == j - i
        ),
        default=0,
    )


def _reference_4(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    values = sorted(a + b)
    n = len(values)
    return (values[(n - 1) // 2] + values[n // 2]) / 2


def _reference_5(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(
        (a[i:j] for i in range(len(a)) for j in range(i + 1, len(a) + 1) if a[i:j] == a[i:j][::-1]),
        key=len,
        default="",
    )


def _reference_6(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    if b == 1:
        return a
    rows = [""] * b
    row = 0
    step = 1
    for char in a:
        rows[row] += char
        if row == 0:
            step = 1
        if row == b - 1:
            step = -1
        row += step
    return "".join(rows)


def _reference_7(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    result = int(str(abs(a))[::-1]) * (-1 if a < 0 else 1)
    return result if -(2**31) <= result < 2**31 else 0


def _reference_8(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    match = re.match(" *([+-]?\\d+)", a, flags=re.ASCII)
    return max(-(2**31), min(2**31 - 1, int(match[1]))) if match else 0


def _reference_9(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return a >= 0 and str(a) == str(a)[::-1]


def _reference_10(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return re.fullmatch(b, a) is not None


def _reference_11(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(min(a[i], a[j]) * (j - i) for i in range(len(a)) for j in range(i + 1, len(a)))


def _reference_12(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    text = ""
    for value, symbol in [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]:
        count, a = divmod(a, value)
        text += symbol * count
    return text


def _reference_13(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    values = dict(zip("IVXLCDM", [1, 5, 10, 50, 100, 500, 1000], strict=True))
    return sum(
        (
            -values[c] if i + 1 < len(a) and values[c] < values[a[i + 1]] else values[c]
            for i, c in enumerate(a)
        )
    )


def _reference_14(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    prefix = a[0]
    for word in a[1:]:
        while not word.startswith(prefix):
            prefix = prefix[:-1]
    return prefix


def _reference_15(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    target = 0 if number == 15 else b
    count = 3 if number == 15 else 4
    return [
        list(t)
        for t in sorted(
            {tuple(sorted(c)) for c in itertools.combinations(a, count) if sum(c) == target}
        )
    ]


def _reference_16(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return min((sum(c) for c in itertools.combinations(a, 3)), key=lambda x: abs(x - b))


def _reference_17(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    letters = dict(
        zip("23456789", ["abc", "def", "ghi", "jkl", "mno", "pqrs", "tuv", "wxyz"], strict=True)
    )
    return ["".join(x) for x in itertools.product(*(letters[c] for c in a))] if a else []


def _reference_20(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    stack = []
    for c in a:
        if c in "([{":
            stack.append(c)
        elif not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[c]:
            return False
    return not stack


def _reference_22(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    result = []

    def visit(s: str, opened: int, closed: int) -> None:
        if closed == a:
            result.append(s)
            return
        if opened < a:
            visit(s + "(", opened + 1, closed)
        if closed < opened:
            visit(s + ")", opened, closed + 1)

    visit("", 0, 0)
    return result


def _reference_26(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    values = []
    counts: Counter[int] = Counter()
    for x in a:
        if (
            number == 27
            and x != b
            or (number in {26, 80} and counts[x] < (1 if number == 26 else 2))
        ):
            values.append(x)
            counts[x] += 1
    return {"length": len(values), "values": values}


def _reference_28(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return a.find(b)


def _reference_29(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return min(2**31 - 1, abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1))


def _reference_30(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    length = len(b[0])
    width = length * len(b)
    return [
        i
        for i in range(len(a) - width + 1)
        if Counter(a[j : j + length] for j in range(i, i + width, length)) == Counter(b)
    ]


def _reference_31(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    values = a[:]
    i = len(values) - 2
    while i >= 0 and values[i] >= values[i + 1]:
        i -= 1
    if i >= 0:
        j = len(values) - 1
        while values[j] <= values[i]:
            j -= 1
        values[i], values[j] = (values[j], values[i])
    values[i + 1 :] = reversed(values[i + 1 :])
    return values


def _reference_32(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    longest = 0
    for i in range(len(a)):
        depth = 0
        for j in range(i, len(a)):
            depth += 1 if a[j] == "(" else -1
            if depth < 0:
                break
            if depth == 0:
                longest = max(longest, j - i + 1)
    return longest


def _reference_33(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return (a.index(b) if b in a else -1) if number == 33 else b in a


def _reference_34(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return [a.index(b), len(a) - 1 - a[::-1].index(b)] if b in a else [-1, -1]


def _reference_35(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return sum(x < b for x in a)


def _reference_38(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    text = "1"
    for _ in range(a - 1):
        text = "".join((str(len(list(g))) + c for c, g in itertools.groupby(text)))
    return text


def _reference_39(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    result = set()

    def combinations(start: int, left: int, path: tuple[int, ...]) -> None:
        if left == 0:
            result.add(tuple(sorted(path)))
            return
        for i in range(start, len(a)):
            if a[i] <= left:
                combinations(i if number == 39 else i + 1, left - a[i], (*path, a[i]))

    combinations(0, b, ())
    return [list(t) for t in sorted(result)]


def _reference_41(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return next(i for i in range(1, len(a) + 2) if i not in a)


def _reference_42(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return sum((max(0, min(max(a[: i + 1]), max(a[i:])) - height) for i, height in enumerate(a)))


def _reference_43(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return str(int(a) * int(b))


def _reference_44(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def match(i: int, j: int) -> bool:
        if j == len(b):
            return i == len(a)
        if b[j] == "*":
            return match(i, j + 1) or (i < len(a) and match(i + 1, j))
        return i < len(a) and (b[j] == "?" or b[j] == a[i]) and match(i + 1, j + 1)

    return match(0, 0)


def _reference_45(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    distance = [len(a) + 1] * len(a)
    distance[0] = 0
    for i, x in enumerate(a):
        for j in range(i + 1, min(len(a), i + x + 1)):
            distance[j] = min(distance[j], distance[i] + 1)
    return distance[-1] < len(a) + 1 if number == 55 else distance[-1]


def _reference_46(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [list(x) for x in sorted(set(itertools.permutations(a)))]


def _reference_48(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [list(row) for row in zip(*a[::-1], strict=True)]


def _reference_49(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    groups: dict[str, list[str]] = {}
    for s in a:
        groups.setdefault("".join(sorted(s)), []).append(s)
    return list(groups.values())


def _reference_50(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return float(a**b)


def _reference_53(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return (
        max(sum(a[i:j]) for i in range(len(a)) for j in range(i + 1, len(a) + 1))
        if number == 53
        else max([0] + [a[j] - a[i] for i in range(len(a)) for j in range(i + 1, len(a))])
    )


def _reference_54(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    matrix = [r[:] for r in a]
    result: list[int] = []
    while matrix:
        result += matrix.pop(0)
        matrix = [list(r) for r in zip(*matrix, strict=True)][::-1]
    return result


def _reference_56(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    result: list[list[int]] = []
    for start, end in sorted(a + ([b] if number == 57 else [])):
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return result


def _reference_58(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return len(a.split()[-1])


def _reference_59(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    matrix = [[0] * a for _ in range(a)]
    row = column = 0
    dr, dc = (0, 1)
    for n in range(1, a * a + 1):
        matrix[row][column] = n
        nr, nc = (row + dr, column + dc)
        if not (0 <= nr < a and 0 <= nc < a) or matrix[nr][nc]:
            dr, dc = (dc, -dr)
        row += dr
        column += dc
    return matrix


def _reference_60(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return "".join(
        map(str, next(itertools.islice(itertools.permutations(range(1, a + 1)), b - 1, b)))
    )


def _reference_62(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return math.comb(a + b - 2, a - 1)


def _reference_63(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None

    @lru_cache(None)
    def path(r: int, c: int) -> int:
        if r >= len(a) or c >= len(a[0]):
            return 0 if number == 63 else 10**9
        if number == 63 and a[r][c]:
            return 0
        if r == len(a) - 1 and c == len(a[0]) - 1:
            return 1 if number == 63 else a[r][c]
        return (
            path(r + 1, c) + path(r, c + 1)
            if number == 63
            else a[r][c] + min(path(r + 1, c), path(r, c + 1))
        )

    return path(0, 0)


def _reference_65(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return (
        re.fullmatch("[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?", a, flags=re.ASCII)
        is not None
    )


def _reference_66(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [int(c) for c in str(int("".join(map(str, a))) + 1)]


def _reference_67(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return bin(int(a, 2) + int(b, 2))[2:]


def _reference_69(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return math.isqrt(a)


def _reference_70(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    x, y = (1, 1)
    for _ in range(a):
        x, y = (y, x + y)
    return x


def _reference_71(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    stack: list[str] = []
    for part in a.split("/"):
        if part == "..":
            if stack:
                stack.pop()
        elif part not in {"", "."}:
            stack.append(part)
    return "/" + "/".join(stack)


def _reference_72(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def edit(i: int, j: int) -> int:
        if i == len(a):
            return len(b) - j
        if j == len(b):
            return len(a) - i
        if a[i] == b[j]:
            return edit(i + 1, j + 1)
        return 1 + min(edit(i + 1, j), edit(i, j + 1), edit(i + 1, j + 1))

    return edit(0, 0)


def _reference_73(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    rows = {i for i, row in enumerate(a) if 0 in row}
    cols = {j for row in a for j, x in enumerate(row) if x == 0}
    return [
        [0 if i in rows or j in cols else x for j, x in enumerate(row)] for i, row in enumerate(a)
    ]


def _reference_74(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return any(b in row for row in a)


def _reference_75(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return sorted(a)


def _reference_77(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return [list(c) for c in itertools.combinations(range(1, a + 1), b)]


def _reference_78(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [
        list(x)
        for x in sorted(
            {tuple(sorted(c)) for n in range(len(a) + 1) for c in itertools.combinations(a, n)}
        )
    ]


def _reference_79(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None

    def visit(r: int, c: int, i: int, seen: set) -> bool:
        if i == len(b):
            return True
        if not (0 <= r < len(a) and 0 <= c < len(a[0])) or (r, c) in seen or a[r][c] != b[i]:
            return False
        return any(
            (
                visit(r + dr, c + dc, i + 1, seen | {(r, c)})
                for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]
            )
        )

    return any(visit(r, c, 0, set()) for r in range(len(a)) for c in range(len(a[0])))


def _reference_84(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(
        [0] + [min(a[i:j]) * (j - i) for i in range(len(a)) for j in range(i + 1, len(a) + 1)]
    )


def _reference_88(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return sorted(a[:b] + args[2][: args[3]])


def _reference_91(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None

    @lru_cache(None)
    def decode(i: int) -> int:
        if i == len(a):
            return 1
        if a[i] == "0":
            return 0
        return decode(i + 1) + (decode(i + 2) if i + 1 < len(a) and int(a[i : i + 2]) <= 26 else 0)

    return decode(0)


def _reference_96(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return math.comb(2 * a, a) // (a + 1)


def _reference_97(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    c = args[2]

    @lru_cache(None)
    def interleave(i: int, j: int) -> bool:
        if i + j == len(c):
            return i == len(a) and j == len(b)
        return (
            i < len(a)
            and a[i] == c[i + j]
            and interleave(i + 1, j)
            or (j < len(b) and b[j] == c[i + j] and interleave(i, j + 1))
        )

    return len(a) + len(b) == len(c) and interleave(0, 0)


def _reference_115(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def subsequence(i: int, j: int) -> int:
        if j == len(b):
            return 1
        if i == len(a):
            return 0
        return subsequence(i + 1, j) + (subsequence(i + 1, j + 1) if a[i] == b[j] else 0)

    return subsequence(0, 0)


def _reference_118(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    rows = [[1]]
    for _ in range(a if number == 119 else a - 1):
        rows.append([1] + [x + y for x, y in zip(rows[-1], rows[-1][1:], strict=False)] + [1])
    return rows[-1] if number == 119 else rows


def _reference_120(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    values = a[-1][:]
    for row in reversed(a[:-1]):
        values = [x + min(values[i : i + 2]) for i, x in enumerate(row)]
    return values[0]


def _reference_122(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return sum((max(y - x, 0) for x, y in zip(a, a[1:], strict=False)))


def _reference_125(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    text = "".join(c.lower() for c in a if c.isascii() and c.isalnum())
    return text == text[::-1]


def _reference_128(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    values = set(a)
    return max(
        [0]
        + [
            next(i for i in range(1, len(a) + 2) if x + i not in values)
            for x in values
            if x - 1 not in values
        ]
    )


def _reference_134(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return next(
        (
            i
            for i in range(len(a))
            if all(
                (
                    sum((a[(i + k) % len(a)] - b[(i + k) % len(a)] for k in range(n))) >= 0
                    for n in range(1, len(a) + 1)
                )
            )
        ),
        -1,
    )


def _reference_136(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return next((x for x, n in Counter(a).items() if n == 1))


def _reference_139(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def split(i: int) -> bool:
        return i == len(a) or any(a.startswith(w, i) and split(i + len(w)) for w in b)

    return split(0)


def _reference_140(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def sentences(i: int) -> list[str]:
        if i == len(a):
            return [""]
        return [
            w + (" " + tail if tail else "")
            for w in b
            if a.startswith(w, i)
            for tail in sentences(i + len(w))
        ]

    return sentences(0)


def _reference_150(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    stack = []
    for token in a:
        if token not in {"+", "-", "*", "/"}:
            stack.append(int(token))
            continue
        right, left = (stack.pop(), stack.pop())
        stack.append(
            left + right
            if token == "+"
            else left - right
            if token == "-"
            else left * right
            if token == "*"
            else math.trunc(left / right)
        )
    return stack[0]


def _reference_151(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return " ".join(a.split()[::-1])


def _reference_152(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(math.prod(a[i:j]) for i in range(len(a)) for j in range(i + 1, len(a) + 1))


def _reference_153(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return min(a)


def _reference_162(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return next(
        (
            i
            for i, x in enumerate(a)
            if (i == 0 or x > a[i - 1]) and (i == len(a) - 1 or x > a[i + 1])
        )
    )


def _reference_164(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max([0] + [y - x for x, y in zip(sorted(a), sorted(a)[1:], strict=False)])


def _reference_165(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    left = list(map(int, a.split(".")))
    right = list(map(int, b.split(".")))
    left += [0] * (len(right) - len(left))
    right += [0] * (len(left) - len(right))
    return (left > right) - (left < right)


def _reference_167(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return next(
        [i + 1, j + 1] for i in range(len(a)) for j in range(i + 1, len(a)) if a[i] + a[j] == b
    )


def _reference_168(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    text = ""
    while a:
        a, r = divmod(a - 1, 26)
        text = chr(65 + r) + text
    return text


def _reference_169(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return Counter(a).most_common(1)[0][0]


def _reference_171(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    result = 0
    for c in a:
        result = result * 26 + ord(c) - 64
    return result


def _reference_172(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    result = 0
    while a:
        a //= 5
        result += a
    return result


def _reference_179(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max("".join(map(str, p)) for p in itertools.permutations(a)).lstrip("0") or "0"


def _reference_189(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return a[-(b % len(a)) :] + a[: -(b % len(a))] if b % len(a) else a[:]


def _reference_190(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return int(f"{a:032b}"[::-1], 2)


def _reference_191(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return a.bit_count()


def _reference_198(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(
        sum(a[i] for i in range(len(a)) if bits >> i & 1)
        for bits in range(1 << len(a))
        if all(not bits >> i & 3 == 3 for i in range(len(a) - 1))
        and (number != 213 or len(a) < 2 or (not (bits & 1 and bits >> len(a) - 1 & 1)))
    )


def _reference_202(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    seen = set()
    while a != 1 and a not in seen:
        seen.add(a)
        a = sum(int(c) ** 2 for c in str(a))
    return a == 1


def _reference_204(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return sum(all(i % d for d in range(2, math.isqrt(i) + 1)) for i in range(2, a))


def _reference_205(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return len(set(zip(a, b, strict=True))) == len(set(a)) == len(set(b))


def _reference_209(number: int, args: list[Any]) -> Any:
    target, values = args
    lengths = [
        j - i
        for i in range(len(values))
        for j in range(i + 1, len(values) + 1)
        if sum(values[i:j]) >= target
    ]
    return min(lengths, default=0)


def _reference_215(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return sorted(a, reverse=True)[b - 1]


def _reference_216(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return [list(c) for c in itertools.combinations(range(1, 10), a) if sum(c) == b]


def _reference_217(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return len(set(a)) != len(a)


def _reference_219(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return any(a[i] == a[j] and j - i <= b for i in range(len(a)) for j in range(i + 1, len(a)))


def _reference_220(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return any(
        abs(a[i] - a[j]) <= args[2] and j - i <= b
        for i in range(len(a))
        for j in range(i + 1, len(a))
    )


def _reference_223(number: int, args: list[Any]) -> Any:
    x1, y1, x2, y2, u1, v1, u2, v2 = args
    return (
        (x2 - x1) * (y2 - y1)
        + (u2 - u1) * (v2 - v1)
        - max(0, min(x2, u2) - max(x1, u1)) * max(0, min(y2, v2) - max(y1, v1))
    )


def _reference_228(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    groups: list[list[int]] = []
    for n in a:
        if groups and groups[-1][-1] + 1 == n:
            groups[-1].append(n)
        else:
            groups.append([n])
    return [str(g[0]) if len(g) == 1 else f"{g[0]}->{g[-1]}" for g in groups]


def _reference_229(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [x for x, n in Counter(a).items() if n > len(a) // 3]


def _reference_231(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return a > 0 and a & a - 1 == 0


def _reference_233(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return sum(str(i).count("1") for i in range(a + 1))


def _reference_238(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [math.prod(a[:i] + a[i + 1 :]) for i in range(len(a))]


def _reference_239(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return [max(a[i : i + b]) for i in range(len(a) - b + 1)]


def _reference_242(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    return Counter(a) == Counter(b)


def _reference_258(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return 0 if a == 0 else 1 + (a - 1) % 9


def _reference_260(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [x for x, n in Counter(a).items() if n == 1]


def _reference_263(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    if a <= 0:
        return False
    for d in [2, 3, 5]:
        while a % d == 0:
            a //= d
    return a == 1


def _reference_264(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    values = [1]
    i = j = k = 0
    while len(values) < a:
        n = min(2 * values[i], 3 * values[j], 5 * values[k])
        values.append(n)
        if n == 2 * values[i]:
            i += 1
        if n == 3 * values[j]:
            j += 1
        if n == 5 * values[k]:
            k += 1
    return values[-1]


def _reference_268(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return len(a) * (len(a) + 1) // 2 - sum(a)


def _reference_274(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max([0] + [h for h in range(1, len(a) + 1) if sum(x >= h for x in a) >= h])


def _reference_279(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    values = [0] + [a + 1] * a
    for i in range(1, a + 1):
        values[i] = 1 + min(values[i - j * j] for j in range(1, math.isqrt(i) + 1))
    return values[a]


def _reference_283(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [x for x in a if x] + [0] * a.count(0)


def _reference_287(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return next((x for x, n in Counter(a).items() if n > 1))


def _reference_289(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return [
        [
            int(
                sum(
                    a[r][c]
                    for r in range(max(0, i - 1), min(len(a), i + 2))
                    for c in range(max(0, j - 1), min(len(a[0]), j + 2))
                    if (r, c) != (i, j)
                )
                in ((2, 3) if a[i][j] else (3,))
            )
            for j in range(len(a[0]))
        ]
        for i in range(len(a))
    ]


def _reference_290(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    words = b.split()
    return len(a) == len(words) and len(set(zip(a, words, strict=False))) == len(set(a)) == len(
        set(words)
    )


def _reference_292(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return a % 4 != 0


def _reference_299(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    b: Any = args[1] if len(args) > 1 else None
    bulls = sum((x == y for x, y in zip(a, b, strict=True)))
    return f"{bulls}A{sum((Counter(a) & Counter(b)).values()) - bulls}B"


def _reference_300(number: int, args: list[Any]) -> Any:
    a: Any = args[0] if args else None
    return max(
        (
            len(c)
            for n in range(len(a) + 1)
            for c in itertools.combinations(a, n)
            if all((x < y for x, y in zip(c, c[1:], strict=False)))
        ),
        default=0,
    )


REFERENCES = {
    1: _reference_1,
    3: _reference_3,
    4: _reference_4,
    5: _reference_5,
    6: _reference_6,
    7: _reference_7,
    8: _reference_8,
    9: _reference_9,
    10: _reference_10,
    11: _reference_11,
    12: _reference_12,
    13: _reference_13,
    14: _reference_14,
    15: _reference_15,
    18: _reference_15,
    16: _reference_16,
    17: _reference_17,
    20: _reference_20,
    22: _reference_22,
    26: _reference_26,
    27: _reference_26,
    80: _reference_26,
    28: _reference_28,
    29: _reference_29,
    30: _reference_30,
    31: _reference_31,
    32: _reference_32,
    33: _reference_33,
    81: _reference_33,
    34: _reference_34,
    35: _reference_35,
    38: _reference_38,
    39: _reference_39,
    40: _reference_39,
    41: _reference_41,
    42: _reference_42,
    43: _reference_43,
    44: _reference_44,
    45: _reference_45,
    55: _reference_45,
    46: _reference_46,
    47: _reference_46,
    48: _reference_48,
    49: _reference_49,
    50: _reference_50,
    53: _reference_53,
    121: _reference_53,
    54: _reference_54,
    56: _reference_56,
    57: _reference_56,
    58: _reference_58,
    59: _reference_59,
    60: _reference_60,
    62: _reference_62,
    63: _reference_63,
    64: _reference_63,
    65: _reference_65,
    66: _reference_66,
    67: _reference_67,
    69: _reference_69,
    70: _reference_70,
    71: _reference_71,
    72: _reference_72,
    73: _reference_73,
    74: _reference_74,
    240: _reference_74,
    75: _reference_75,
    77: _reference_77,
    78: _reference_78,
    90: _reference_78,
    79: _reference_79,
    84: _reference_84,
    88: _reference_88,
    91: _reference_91,
    96: _reference_96,
    97: _reference_97,
    115: _reference_115,
    118: _reference_118,
    119: _reference_118,
    120: _reference_120,
    122: _reference_122,
    125: _reference_125,
    128: _reference_128,
    134: _reference_134,
    136: _reference_136,
    137: _reference_136,
    139: _reference_139,
    140: _reference_140,
    150: _reference_150,
    151: _reference_151,
    152: _reference_152,
    153: _reference_153,
    154: _reference_153,
    162: _reference_162,
    164: _reference_164,
    165: _reference_165,
    167: _reference_167,
    168: _reference_168,
    169: _reference_169,
    171: _reference_171,
    172: _reference_172,
    179: _reference_179,
    189: _reference_189,
    190: _reference_190,
    191: _reference_191,
    198: _reference_198,
    213: _reference_198,
    202: _reference_202,
    204: _reference_204,
    205: _reference_205,
    209: _reference_209,
    215: _reference_215,
    216: _reference_216,
    217: _reference_217,
    219: _reference_219,
    220: _reference_220,
    223: _reference_223,
    228: _reference_228,
    229: _reference_229,
    231: _reference_231,
    233: _reference_233,
    238: _reference_238,
    239: _reference_239,
    242: _reference_242,
    258: _reference_258,
    260: _reference_260,
    263: _reference_263,
    264: _reference_264,
    268: _reference_268,
    274: _reference_274,
    275: _reference_274,
    279: _reference_279,
    283: _reference_283,
    287: _reference_287,
    289: _reference_289,
    290: _reference_290,
    292: _reference_292,
    299: _reference_299,
    300: _reference_300,
}
REFERENCES.update(EXTRA_REFERENCES)


def reference(number: int, args: list[Any]) -> Any:
    try:
        oracle = REFERENCES[number]
    except KeyError:
        raise ValueError(f"No independent oracle for question {number}") from None
    return oracle(number, args)
