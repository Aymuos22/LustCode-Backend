"""Independent list, tree, grid and dynamic-programming reference oracles."""

import itertools
from collections import Counter, deque
from functools import lru_cache
from typing import Any


def tree(values: list) -> Any:
    if not values or values[0] is None:
        return None
    root = [values[0], None, None]
    queue = deque([root])
    i = 1
    while queue:
        node = queue.popleft()
        for side in (1, 2):
            if i < len(values) and values[i] is not None:
                node[side] = [values[i], None, None]
                queue.append(node[side])
            i += 1
    return root


def serialize(root: Any) -> list:
    queue = deque([root])
    values = []
    while queue:
        node = queue.popleft()
        values.append(node[0] if node else None)
        if node:
            queue.extend(node[1:])
    while values and values[-1] is None:
        values.pop()
    return values


def traversal(root: Any, order: int = 1) -> list:
    if root is None:
        return []
    left, right = (traversal(root[1], order), traversal(root[2], order))
    return (
        [root[0]] + left + right
        if order == 0
        else left + [root[0]] + right
        if order == 1
        else left + right + [root[0]]
    )


def lists(number: int, args: list[Any]) -> Any:
    a = args[0]
    if number == 2:
        value = sum((x * 10**i for i, x in enumerate(a))) + sum(
            (x * 10**i for i, x in enumerate(args[1]))
        )
        return list(map(int, str(value)[::-1]))
    if number == 19:
        i = len(a) - args[1]
        return a[:i] + a[i + 1 :]
    if number == 21:
        return sorted(a + args[1])
    if number == 23:
        return sorted(x for values in a for x in values)
    if number == 24:
        return [x for i in range(0, len(a), 2) for x in a[i : i + 2][::-1]]
    if number == 25:
        k = args[1]
        return [
            x
            for i in range(0, len(a), k)
            for x in (a[i : i + k][::-1] if i + k <= len(a) else a[i : i + k])
        ]
    if number == 61:
        k = args[1] % len(a) if a else 0
        return a[-k:] + a[:-k] if k else a[:]
    if number == 82:
        return [x for x in a if a.count(x) == 1]
    if number == 83:
        return list(dict.fromkeys(a))
    if number == 86:
        return [x for x in a if x < args[1]] + [x for x in a if x >= args[1]]
    if number == 92:
        i, j = (args[1] - 1, args[2])
        return a[:i] + a[i:j][::-1] + a[j:]
    if number == 143:
        out = []
        i, j = (0, len(a) - 1)
        while i <= j:
            out.append(a[i])
            if i != j:
                out.append(a[j])
            i += 1
            j -= 1
        return out
    if number in {147, 148}:
        return sorted(a)
    if number == 203:
        return [x for x in a if x != args[1]]
    if number == 206:
        return a[::-1]
    if number == 234:
        return a == a[::-1]
    raise ValueError("Unsupported list reference")


def trees(number: int, args: list[Any]) -> Any:
    a = tree(args[0])

    def height(node: Any) -> int:
        return 1 + max(height(node[1]), height(node[2])) if node else 0

    def leaves(node: Any, path: list[int]) -> list[list[int]]:
        if node is None:
            return []
        path = path + [node[0]]
        if not node[1] and (not node[2]):
            return [path]
        return leaves(node[1], path) + leaves(node[2], path)

    if number in {94, 144, 145}:
        return traversal(a, {94: 1, 144: 0, 145: 2}[number])
    if number == 98:
        values = traversal(a)
        return all((x < y for x, y in zip(values, values[1:], strict=False)))
    if number == 99:
        ordered_values = iter(sorted(traversal(a)))

        def fix(node: Any) -> None:
            if node:
                fix(node[1])
                node[0] = next(ordered_values)
                fix(node[2])

        fix(a)
        return serialize(a)
    if number == 100:
        return a == tree(args[1])
    if number == 101:

        def mirror(node: Any) -> Any:
            return [node[0], mirror(node[2]), mirror(node[1])] if node else None

        return a == mirror(a)
    if number in {102, 103, 107, 199}:
        rows = []
        queue = [a] if a else []
        while queue:
            rows.append([n[0] for n in queue])
            queue = [child for n in queue for child in n[1:] if child]
        if number == 103:
            return [row[::-1] if i % 2 else row for i, row in enumerate(rows)]
        return rows[::-1] if number == 107 else [r[-1] for r in rows] if number == 199 else rows
    if number == 104:
        return height(a)
    if number == 110:

        def balanced(node: Any) -> bool:
            return not node or (
                abs(height(node[1]) - height(node[2])) <= 1
                and balanced(node[1])
                and balanced(node[2])
            )

        return balanced(a)
    if number == 111:
        return min((len(p) for p in leaves(a, [])), default=0)
    if number in {112, 113}:
        paths = [p for p in leaves(a, []) if sum(p) == args[1]]
        return bool(paths) if number == 112 else paths
    if number == 114:
        values = traversal(a, 0)
        return [x for v in values for x in [v, None]][:-1]
    if number == 124:
        best = -(10**9)

        def gain(node: Any) -> int:
            nonlocal best
            if not node:
                return 0
            left = max(0, gain(node[1]))
            right = max(0, gain(node[2]))
            best = max(best, node[0] + left + right)
            return node[0] + max(left, right)

        gain(a)
        return best
    if number == 129:
        return sum(int("".join(map(str, p))) for p in leaves(a, []))
    if number == 222:
        return len(traversal(a))
    if number == 226:

        def invert(node: Any) -> Any:
            return [node[0], invert(node[2]), invert(node[1])] if node else None

        return serialize(invert(a))
    if number == 230:
        return traversal(a)[args[1] - 1]
    if number == 257:
        return ["->".join(map(str, p)) for p in leaves(a, [])]
    raise ValueError("Unsupported tree reference")


def reconstruct(number: int, args: list[Any]) -> Any:

    def build(first: list, second: list) -> Any:
        if not first:
            return None
        value = first[0] if number == 105 else second[-1]
        i = second.index(value) if number == 105 else first.index(value)
        return (
            [value, build(first[1 : i + 1], second[:i]), build(first[i + 1 :], second[i + 1 :])]
            if number == 105
            else [value, build(first[:i], second[:i]), build(first[i + 1 :], second[i:-1])]
        )

    return serialize(build(*args))


REFERENCES = {
    number: lists
    for number in [2, 19, 21, 23, 24, 25, 61, 82, 83, 86, 92, 143, 147, 148, 203, 206, 234]
}
REFERENCES.update(
    {
        number: trees
        for number in [
            94,
            98,
            99,
            100,
            101,
            102,
            103,
            104,
            107,
            110,
            111,
            112,
            113,
            114,
            124,
            129,
            144,
            145,
            199,
            222,
            226,
            230,
            257,
        ]
    }
)
REFERENCES.update({105: reconstruct, 106: reconstruct})


def _extra_36(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    groups = (
        [row for row in a]
        + [list(row) for row in zip(*a, strict=True)]
        + [
            [a[r + i][c + j] for i in range(3) for j in range(3)]
            for r in (0, 3, 6)
            for c in (0, 3, 6)
        ]
    )
    return all(len([x for x in g if x != "."]) == len({x for x in g if x != "."}) for g in groups)


def _extra_51(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    result = []
    for permutation in itertools.permutations(range(a)):
        if (
            len({r - c for r, c in enumerate(permutation)}) == a
            and len({r + c for r, c in enumerate(permutation)}) == a
        ):
            result.append(["." * c + "Q" + "." * (a - c - 1) for c in permutation])
    return len(result) if number == 52 else result


def _extra_68(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    result = []
    i = 0
    while i < len(a):
        j = i + 1
        while j < len(a) and sum(map(len, a[i : j + 1])) + j - i <= b:
            j += 1
        words = a[i:j]
        spaces = b - sum(map(len, words))
        if j == len(a) or len(words) == 1:
            line = " ".join(words).ljust(b)
        else:
            width, extra_spaces = divmod(spaces, len(words) - 1)
            line = "".join(
                (
                    w + (" " * (width + (k < extra_spaces)) if k < len(words) - 1 else "")
                    for k, w in enumerate(words)
                )
            )
        result.append(line)
        i = j
    return result


def _extra_76(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    wanted = Counter(b)
    return min(
        (
            a[i:j]
            for i in range(len(a))
            for j in range(i + 1, len(a) + 1)
            if not wanted - Counter(a[i:j])
        ),
        key=len,
        default="",
    )


def _extra_85(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    best = 0
    for r in range(len(a)):
        for c in range(len(a[0])):
            for rr in range(r, len(a)):
                for cc in range(c, len(a[0])):
                    area = (rr - r + 1) * (cc - c + 1)
                    if (number != 221 or rr - r == cc - c) and all(
                        a[i][j] == "1" for i in range(r, rr + 1) for j in range(c, cc + 1)
                    ):
                        best = max(best, area)
    return best


def _extra_87(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def scramble(left: str, right: str) -> bool:
        if left == right:
            return True
        if Counter(left) != Counter(right):
            return False
        return any(
            scramble(left[:i], right[:i])
            and scramble(left[i:], right[i:])
            or (scramble(left[:i], right[-i:]) and scramble(left[i:], right[:-i]))
            for i in range(1, len(left))
        )

    return scramble(a, b)


def _extra_93(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return [
        ".".join(parts)
        for i, j, k in itertools.combinations(range(1, len(a)), 3)
        for parts in [[a[:i], a[i:j], a[j:k], a[k:]]]
        if all(len(p) == 1 or p[0] != "0" for p in parts) and all(int(p) <= 255 for p in parts)
    ]


def _extra_123(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    k, prices = (2, a) if number == 123 else (a, b)

    @lru_cache(None)
    def profit(day: int, left: int, holding: bool) -> int:
        if day == len(prices):
            return -(10**9) if holding else 0
        skip = profit(day + 1, left, holding)
        if holding and left:
            return max(skip, prices[day] + profit(day + 1, left - 1, False))
        if not holding and left:
            return max(skip, -prices[day] + profit(day + 1, left, True))
        return skip

    return profit(0, k, False)


def _extra_126(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    end = args[1]
    words = set(args[2])
    queue = deque([(a, [a])])
    shortest = None
    paths = []
    while queue:
        word, path = queue.popleft()
        if shortest and len(path) > shortest:
            continue
        if word == end:
            shortest = len(path)
            paths.append(path)
            continue
        for neighbor in words - set(path):
            if sum((x != y for x, y in zip(word, neighbor, strict=True))) == 1:
                queue.append((neighbor, path + [neighbor]))
    return (len(paths[0]) if paths else 0) if number == 127 else paths


def _extra_130(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    seen = set()
    islands = 0
    out = [row[:] for row in a]
    for r in range(len(a)):
        for c in range(len(a[0])):
            target = "O" if number == 130 else "1"
            if a[r][c] != target or (r, c) in seen:
                continue
            region = {(r, c)}
            queue = [(r, c)]
            seen.add((r, c))
            for i, j in queue:
                for x, y in [(i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)]:
                    if (
                        0 <= x < len(a)
                        and 0 <= y < len(a[0])
                        and ((x, y) not in seen)
                        and (a[x][y] == target)
                    ):
                        seen.add((x, y))
                        region.add((x, y))
                        queue.append((x, y))
            islands += 1
            if number == 130 and all(
                (0 < i < len(a) - 1 and 0 < j < len(a[0]) - 1 for i, j in region)
            ):
                for i, j in region:
                    out[i][j] = "X"
    return out if number == 130 else islands


def _extra_131(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    @lru_cache(None)
    def partitions(text: str) -> list[list[str]]:
        if not text:
            return [[]]
        return [
            [text[:i], *tail]
            for i in range(1, len(text) + 1)
            if text[:i] == text[:i][::-1]
            for tail in partitions(text[i:])
        ]

    parts = partitions(a)
    return parts if number == 131 else min(map(len, parts)) - 1


def _extra_135(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    candies = [1] * len(a)
    for _ in range(len(a)):
        for i in range(len(a)):
            candies[i] = max(
                [candies[i]]
                + [candies[j] + 1 for j in (i - 1, i + 1) if 0 <= j < len(a) and a[i] > a[j]]
            )
    return sum(candies)


def _extra_149(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    if len(a) < 3:
        return len(a)
    return max(
        (
            sum(((y2 - y1) * (x - x1) == (y - y1) * (x2 - x1) for x, y in a))
            for (x1, y1), (x2, y2) in itertools.combinations(a, 2)
        )
    )


def _extra_166(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    if a == 0:
        return "0"
    sign = "-" if (a < 0) != (b < 0) else ""
    a, b = (abs(a), abs(b))
    whole, remainder = divmod(a, b)
    if not remainder:
        return sign + str(whole)
    digits: list[str] = []
    seen = {}
    while remainder and remainder not in seen:
        seen[remainder] = len(digits)
        digit, remainder = divmod(remainder * 10, b)
        digits.append(str(digit))
    if remainder:
        digits.insert(seen[remainder], "(")
        digits.append(")")
    return sign + str(whole) + "." + "".join(digits)


def _extra_174(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    @lru_cache(None)
    def need(r: int, c: int) -> int:
        if r == len(a) - 1 and c == len(a[0]) - 1:
            return max(1, 1 - a[r][c])
        return max(
            1,
            min([need(x, y) for x, y in [(r + 1, c), (r, c + 1)] if x < len(a) and y < len(a[0])])
            - a[r][c],
        )

    return need(0, 0)


def _extra_187(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return [s for s, n in Counter(a[i : i + 10] for i in range(len(a) - 9)).items() if n > 1]


def _extra_201(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    return sum(1 << bit for bit in range(31) if a >> bit == b >> bit and a >> bit & 1)


def _extra_207(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    edges: dict[int, set[int]] = {i: set() for i in range(a)}
    for after, before in b:
        edges[after].add(before)
    result: list[int] = []
    while len(result) < a:
        free = next((i for i in edges if i not in result and (not edges[i] - set(result))), None)
        if free is None:
            return False if number == 207 else []
        result.append(free)
    return True if number == 207 else result


def _extra_212(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    from app.judging.references import reference

    return [word for word in b if reference(79, [a, word])]


def _extra_214(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return next(a[i:][::-1] + a for i in range(len(a), -1, -1) if a[:i] == a[:i][::-1])


def _extra_218(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    result: list[list[int]] = []
    for x in sorted({v for left, right, _ in a for v in [left, right]}):
        height = max([0] + [h for left, right, h in a if left <= x < right])
        if not result or height != result[-1][1]:
            result.append([x, height])
    return result


def _extra_241(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    @lru_cache(None)
    def calculate(text: str) -> list[int]:
        result = []
        for i, c in enumerate(text):
            if c in "+-*":
                for left in calculate(text[:i]):
                    for right in calculate(text[i + 1 :]):
                        result.append(
                            left + right if c == "+" else left - right if c == "-" else left * right
                        )
        return result or [int(text)]

    return calculate(a)


REFERENCES.update(
    {
        36: _extra_36,
        51: _extra_51,
        52: _extra_51,
        68: _extra_68,
        76: _extra_76,
        85: _extra_85,
        221: _extra_85,
        87: _extra_87,
        93: _extra_93,
        123: _extra_123,
        188: _extra_123,
        126: _extra_126,
        127: _extra_126,
        130: _extra_130,
        200: _extra_130,
        131: _extra_131,
        132: _extra_131,
        135: _extra_135,
        149: _extra_149,
        166: _extra_166,
        174: _extra_174,
        187: _extra_187,
        201: _extra_201,
        207: _extra_207,
        210: _extra_207,
        212: _extra_212,
        214: _extra_214,
        218: _extra_218,
        241: _extra_241,
    }
)
