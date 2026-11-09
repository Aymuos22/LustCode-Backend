"""User-authorized LustCode contracts, authored without protected provider content."""

import itertools
from collections import Counter, deque
from functools import lru_cache
from typing import Any

from app.judging.extra_references import serialize, traversal, tree
from app.schemas import FunctionParameter, FunctionSignature

CONTRACTS: dict[int, tuple[str, list[tuple[str, str]], str, str]] = {
    156: (
        "upsideDownBinaryTree",
        [("root", "TreeNode")],
        "TreeNode",
        (
            "Rotate the tree along its left spine. Every right child is a leaf with a "
            "left sibling. The old right child becomes the new left child; the old "
            "parent becomes the new right child."
        ),
    ),
    157: (
        "readN",
        [("text", "string"), ("n", "integer")],
        "string",
        "Return the first min(n, text length) characters. n is nonnegative; text uses ASCII.",
    ),
    158: (
        "readChunks",
        [("text", "string"), ("counts", "integer[]")],
        "string[]",
        (
            "Read consecutive ASCII chunks of the requested nonnegative sizes, "
            "retaining a cursor between requests. At EOF return empty chunks."
        ),
    ),
    159: (
        "lengthOfLongestSubstringTwoDistinct",
        [("s", "string")],
        "integer",
        (
            "Return the longest contiguous substring length containing at most two "
            "distinct ASCII characters. Empty input returns zero."
        ),
    ),
    161: (
        "isOneEditDistance",
        [("s", "string"), ("t", "string")],
        "boolean",
        (
            "Return whether exactly one insertion, deletion, or substitution changes s "
            "into t. Equal strings return false."
        ),
    ),
    163: (
        "findMissingRanges",
        [("nums", "integer[]"), ("lower", "integer"), ("upper", "integer")],
        "integer[][]",
        (
            "Return sorted inclusive [start,end] ranges missing from the sorted "
            "distinct nums within [lower,upper]."
        ),
    ),
    170: (
        "twoSumOperations",
        [("operations", "integer[][]")],
        "boolean[]",
        (
            "Process [0,value] to add a value and [1,target] to query whether two "
            "distinct stored occurrences sum to target. Return only query answers, in "
            "order."
        ),
    ),
    186: (
        "reverseWords",
        [("s", "character[]")],
        "void",
        (
            "Reverse the order of single-space-separated words in the character array "
            "in place. There are no leading, trailing, or repeated spaces."
        ),
    ),
    243: (
        "shortestDistance",
        [("words", "string[]"), ("word1", "string"), ("word2", "string")],
        "integer",
        (
            "Return minimum index distance between occurrences of the two distinct "
            "words, or -1 when an occurrence is absent."
        ),
    ),
    244: (
        "wordDistances",
        [("words", "string[]"), ("queries", "string[][]")],
        "integer[]",
        (
            "For each two-word query return minimum distance between distinct "
            "occurrences, including queries with equal words. Return -1 if no pair "
            "exists."
        ),
    ),
    245: (
        "shortestWordDistance",
        [("words", "string[]"), ("word1", "string"), ("word2", "string")],
        "integer",
        (
            "Return minimum index distance between distinct occurrences of the "
            "requested words; equal word arguments are allowed. Return -1 if no pair "
            "exists."
        ),
    ),
    246: (
        "isStrobogrammatic",
        [("num", "string")],
        "boolean",
        (
            "Return whether rotating the nonempty digit string 180 degrees yields the "
            "same string. Rotatable pairs are 00,11,69,88,96."
        ),
    ),
    247: (
        "findStrobogrammatic",
        [("n", "integer")],
        "string[]",
        (
            "Return all n-digit strobogrammatic numbers without leading zeros, except "
            "the single digit 0. n is positive. Order is irrelevant."
        ),
    ),
    248: (
        "strobogrammaticInRange",
        [("low", "string"), ("high", "string")],
        "integer",
        (
            "Count strobogrammatic integers in the inclusive nonnegative decimal "
            "range, using their canonical decimal representation."
        ),
    ),
    249: (
        "groupStrings",
        [("strings", "string[]")],
        "list<list<string>>",
        (
            "Group lowercase strings that differ by one uniform cyclic alphabet shift. "
            "Preserve every occurrence, including duplicates. Group and member order "
            "are irrelevant."
        ),
    ),
    250: (
        "countUnivalSubtrees",
        [("root", "TreeNode")],
        "integer",
        (
            "Count nonempty rooted subtrees whose nodes all have the same value. Empty "
            "trees return zero."
        ),
    ),
    251: (
        "flattenVector",
        [("values", "integer[][]")],
        "integer[]",
        "Return rows concatenated in order, skipping empty rows.",
    ),
    252: (
        "canAttendMeetings",
        [("intervals", "integer[][]")],
        "boolean",
        (
            "Return whether positive-length half-open meeting intervals [start,end) "
            "are pairwise nonoverlapping. Touching endpoints are allowed."
        ),
    ),
    253: (
        "minMeetingRooms",
        [("intervals", "integer[][]")],
        "integer",
        (
            "Return the maximum simultaneous occupancy of positive-length half-open "
            "meeting intervals. Empty input returns zero."
        ),
    ),
    254: (
        "getFactors",
        [("n", "integer")],
        "list<list<integer>>",
        (
            "Return unique multiplicative decompositions of n into at least two "
            "factors, each greater than one. Factor and result order are irrelevant."
        ),
    ),
    255: (
        "verifyPreorder",
        [("preorder", "integer[]")],
        "boolean",
        (
            "Return whether the distinct integers can be a preorder traversal of a "
            "strict binary search tree. Empty input is valid."
        ),
    ),
    256: (
        "minCost",
        [("costs", "integer[][]")],
        "integer",
        (
            "Paint each house one of three colors, with adjacent houses different. "
            "Return minimum total cost. Empty costs return zero."
        ),
    ),
    259: (
        "threeSumSmaller",
        [("nums", "integer[]"), ("target", "integer")],
        "integer",
        (
            "Count index triples i<j<k whose values sum strictly below target. Equal "
            "values at distinct indices count separately."
        ),
    ),
    261: (
        "validTree",
        [("n", "integer"), ("edges", "integer[][]")],
        "boolean",
        (
            "Return whether the undirected graph on vertices 0..n-1 is connected and "
            "acyclic. n is positive; edges have distinct endpoints and no duplicates."
        ),
    ),
    265: (
        "minCostII",
        [("costs", "integer[][]")],
        "integer",
        (
            "Return minimum paint cost with k colors and different adjacent colors. k "
            "is at least two for multiple houses. Empty costs return zero."
        ),
    ),
    266: (
        "canPermutePalindrome",
        [("s", "string")],
        "boolean",
        (
            "Return whether the ASCII characters can be rearranged into a palindrome, "
            "including the empty string."
        ),
    ),
    267: (
        "generatePalindromes",
        [("s", "string")],
        "string[]",
        (
            "Return every distinct palindromic permutation of the ASCII string. Order "
            "is irrelevant; the empty string has the single permutation empty string."
        ),
    ),
    269: (
        "alienOrder",
        [("words", "string[]")],
        "string",
        (
            "Return any order of all distinct lowercase characters consistent with the "
            "given lexicographically sorted words. Return empty string on a cycle or "
            "invalid prefix order."
        ),
    ),
    270: (
        "closestValue",
        [("root", "TreeNode"), ("target", "double")],
        "integer",
        (
            "Return the BST value nearest the target, choosing the smaller value on a "
            "tie. The tree is nonempty."
        ),
    ),
    271: (
        "transformStrings",
        [("mode", "integer"), ("strings", "string[]")],
        "string[]",
        (
            "Mode 0 encodes strings into one concatenation of decimal UTF-8 byte "
            "length, #, and string bytes, returning a one-element array. Mode 1 "
            "receives one valid encoded string and returns the decoded strings. Empty "
            "lists, empty strings, delimiters and Unicode must round-trip."
        ),
    ),
    272: (
        "closestKValues",
        [("root", "TreeNode"), ("target", "double"), ("k", "integer")],
        "integer[]",
        (
            "Return k BST values nearest the target; resolve equal distances by "
            "smaller value. Result order is irrelevant. 1 <= k <= node count."
        ),
    ),
    276: (
        "numWays",
        [("n", "integer"), ("k", "integer")],
        "integer",
        (
            "Count colorings of n fence posts with k colors such that no three "
            "adjacent posts share a color. n and k are positive; results fit signed "
            "32-bit integers."
        ),
    ),
    277: (
        "findCelebrity",
        [("knows", "integer[][]")],
        "integer",
        (
            "Given the square 0/1 acquaintance matrix, return a person known by every "
            "other person who knows no other person. Ignore the diagonal; return -1 if "
            "absent."
        ),
    ),
    280: (
        "wiggleSort",
        [("nums", "integer[]")],
        "void",
        (
            "Reorder nums in place into nums[0] <= nums[1] >= nums[2] <= nums[3] ... "
            "while preserving the input multiset. Any valid arrangement is accepted."
        ),
    ),
    281: (
        "zigzag",
        [("v1", "integer[]"), ("v2", "integer[]")],
        "integer[]",
        (
            "Alternate values from the two arrays, starting with v1, then append "
            "remaining values from the nonempty array."
        ),
    ),
    285: (
        "inorderSuccessor",
        [("root", "TreeNode"), ("p", "integer")],
        "integer[]",
        (
            "Return [successor value] for the least BST value strictly greater than p, "
            "or an empty array if absent. p is a value, not a node pointer."
        ),
    ),
    286: (
        "wallsAndGates",
        [("rooms", "integer[][]")],
        "void",
        (
            "Fill empty rooms (2147483647) in place with shortest four-neighbor "
            "distance to a gate (0). Walls are -1; unreachable rooms stay 2147483647."
        ),
    ),
    288: (
        "validWordAbbreviations",
        [("dictionary", "string[]"), ("queries", "string[]")],
        "boolean[]",
        (
            "For every query return whether its abbreviation is shared by no different "
            "dictionary word. Words of length <=2 abbreviate to themselves; others use "
            "first + omitted character count + last."
        ),
    ),
    291: (
        "wordPatternMatch",
        [("pattern", "string"), ("s", "string")],
        "boolean",
        (
            "Determine whether a bijection from pattern characters to nonempty ASCII "
            "substrings expands to s. Empty pattern matches only empty s."
        ),
    ),
    293: (
        "generatePossibleNextMoves",
        [("s", "string")],
        "string[]",
        (
            "Return all distinct strings obtainable by replacing one adjacent ++ with "
            "--. Input contains only + and -. Order is irrelevant."
        ),
    ),
    294: (
        "canWin",
        [("s", "string")],
        "boolean",
        (
            "Players alternate replacing ++ with --; the player with no move loses. "
            "Return whether the first player can force a win."
        ),
    ),
    296: (
        "minTotalDistance",
        [("grid", "integer[][]")],
        "integer",
        (
            "Return minimum total Manhattan distance from a meeting grid point to "
            "every cell containing 1. At least one home exists."
        ),
    ),
    298: (
        "longestConsecutive",
        [("root", "TreeNode")],
        "integer",
        (
            "Return the longest downward parent-to-child path whose values increase by "
            "one at every step. Empty trees return zero."
        ),
    ),
}


def signature(number: int) -> FunctionSignature:
    name, params, result, _ = CONTRACTS[number]
    return FunctionSignature(
        name=name,
        parameters=[FunctionParameter(name=n, type=t) for n, t in params],
        return_type=result,
    )


def _reference_156(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    root = tree(a)
    parent = right = None
    while root:
        left = root[1]
        root[1] = right
        right = root[2]
        root[2] = parent
        parent = root
        root = left
    return serialize(parent)


def _reference_157(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    return a[:b]


def _reference_158(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    out = []
    cursor = 0
    for count in b:
        out.append(a[cursor : cursor + count])
        cursor += count
    return out


def _reference_159(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return max(
        (j - i for i in range(len(a) + 1) for j in range(i, len(a) + 1) if len(set(a[i:j])) <= 2),
        default=0,
    )


def _reference_161(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None

    @lru_cache(None)
    def distance(left: str, right: str) -> int:
        if not left:
            return len(right)
        if not right:
            return len(left)
        if left[0] == right[0]:
            return distance(left[1:], right[1:])
        return 1 + min(
            distance(left[1:], right), distance(left, right[1:]), distance(left[1:], right[1:])
        )

    return distance(a, b) == 1


def _reference_163(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    out = []
    cursor = b
    for value in a + [args[2] + 1]:
        if value > cursor:
            out.append([cursor, value - 1])
        cursor = value + 1
    return out


def _reference_170(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    values = []
    out = []
    for op, value in a:
        if op == 0:
            values.append(value)
        else:
            out.append(any((x + y == value for x, y in itertools.combinations(values, 2))))
    return out


def _reference_186(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return list(" ".join("".join(a).split(" ")[::-1]))


def _reference_243(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None

    def shortest(left: str, right: str) -> int:
        return min(
            (
                abs(i - j)
                for i, x in enumerate(a)
                for j, y in enumerate(a)
                if x == left and y == right and (i != j)
            ),
            default=-1,
        )

    return [shortest(*q) for q in b] if number == 244 else shortest(b, args[2])


def _reference_246(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    pairs = {"0": "0", "1": "1", "6": "9", "8": "8", "9": "6"}

    def valid(s: str) -> bool:
        return all(c in pairs for c in s) and "".join(pairs[c] for c in s[::-1]) == s

    if number == 246:
        return valid(a)
    if number == 248:
        return sum(valid(str(n)) for n in range(int(a), int(b) + 1))

    def build(n: int, outer: bool) -> list[str]:
        if n == 0:
            return [""]
        if n == 1:
            return ["0", "1", "8"]
        return [
            left + middle + right
            for left, right in pairs.items()
            if not (outer and left == "0")
            for middle in build(n - 2, False)
        ]

    return build(a, True)


def _reference_249(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    groups: dict[Any, list[str]] = {}
    for s in a:
        groups.setdefault((len(s), tuple((ord(c) - ord(s[0])) % 26 for c in s)), []).append(s)
    return list(groups.values())


def _reference_250(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    root = tree(a)
    result = 0

    def visit(node: Any, parent: int | None = None, length: int = 0) -> list[int]:
        nonlocal result
        if not node:
            return []
        run = length + 1 if parent is not None and node[0] == parent + 1 else 1
        left = visit(node[1], node[0], run)
        right = visit(node[2], node[0], run)
        if number == 298:
            result = max(result, run)
        elif len(set([node[0], *left, *right])) == 1:
            result += 1
        return [node[0], *left, *right]

    visit(root)
    return result


def _reference_251(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return [x for row in a for x in row]


def _reference_252(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return all(
        (end <= start for (_, end), (start, _) in zip(sorted(a), sorted(a)[1:], strict=False))
    )


def _reference_253(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    active = best = 0
    for _, change in sorted([(start, 1) for start, _ in a] + [(end, -1) for _, end in a]):
        active += change
        best = max(best, active)
    return best


def _reference_254(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    def factors(n: int, minimum: int) -> list[list[int]]:
        return [
            solution
            for f in range(minimum, int(n**0.5) + 1)
            if n % f == 0
            for solution in [[f, n // f], *[[f, *tail] for tail in factors(n // f, f)]]
        ]

    return factors(a, 2)


def _reference_255(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    def valid(values: list[int], low: float, high: float) -> bool:
        if not values:
            return True
        root = values[0]
        if not low < root < high:
            return False
        split = next((i for i, x in enumerate(values[1:], 1) if x > root), len(values))
        return valid(values[1:split], low, root) and valid(values[split:], root, high)

    return valid(a, float("-inf"), float("inf"))


def _reference_256(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    @lru_cache(None)
    def cost(i: int, previous: int) -> int:
        if i == len(a):
            return 0
        return min(a[i][c] + cost(i + 1, c) for c in range(len(a[i])) if c != previous)

    return cost(0, -1)


def _reference_259(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    return sum(sum(c) < b for c in itertools.combinations(a, 3))


def _reference_261(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    seen = {0}
    queue = [0]
    for node in queue:
        for x, y in b:
            other = y if x == node else x if y == node else None
            if other is not None and other not in seen:
                seen.add(other)
                queue.append(other)
    return len(b) == a - 1 and len(seen) == a


def _reference_266(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return sum(n % 2 for n in Counter(a).values()) <= 1


def _reference_267(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    counts = Counter(a)
    odd = [c for c, n in counts.items() if n % 2]
    if len(odd) > 1:
        return []
    half = "".join((c * (n // 2) for c, n in sorted(counts.items())))
    return [
        s + (odd[0] if odd else "") + s[::-1]
        for s in sorted({"".join(p) for p in itertools.permutations(half)})
    ]


def _reference_269(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    edges: dict[str, set[str]] = {c: set() for word in a for c in word}
    for left, right in zip(a, a[1:], strict=False):
        if len(left) > len(right) and left.startswith(right):
            return ""
        for x, y in zip(left, right, strict=False):
            if x != y:
                edges[y].add(x)
                break
    out = ""
    while len(out) < len(edges):
        free = next((c for c in sorted(edges) if c not in out and (not edges[c] - set(out))), None)
        if free is None:
            return ""
        out += free
    return out


def _reference_270(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    values = traversal(tree(a))
    if number == 285:
        return next(([x] for x in values if x > b), [])
    ordered = sorted(values, key=lambda x: (abs(x - b), x))
    return ordered[0] if number == 270 else ordered[: args[2]]


def _reference_271(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    if a == 0:
        return ["".join(str(len(s.encode())) + "#" + s for s in b)]
    encoded = b[0].encode()
    out = []
    cursor = 0
    while cursor < len(encoded):
        separator = encoded.index(b"#", cursor)
        length = int(encoded[cursor:separator])
        cursor = separator + 1
        out.append(encoded[cursor : cursor + length].decode())
        cursor += length
    return out


def _reference_276(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    return sum(
        all(not colors[i] == colors[i + 1] == colors[i + 2] for i in range(a - 2))
        for colors in itertools.product(range(b), repeat=a)
    )


def _reference_277(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    return next(
        (
            i
            for i in range(len(a))
            if all((a[j][i] and (not a[i][j]) for j in range(len(a)) if j != i))
        ),
        -1,
    )


def _reference_280(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    values = sorted(a)
    for i in range(1, len(values) - 1, 2):
        values[i], values[i + 1] = (values[i + 1], values[i])
    return values


def _reference_281(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    return [x for i in range(max(len(a), len(b))) for row in (a, b) for x in row[i : i + 1]]


def _reference_286(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    out = [row[:] for row in a]
    queue = deque((r, c) for r in range(len(a)) for c in range(len(a[0])) if a[r][c] == 0)
    while queue:
        r, c = queue.popleft()
        for i, j in [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]:
            if 0 <= i < len(a) and 0 <= j < len(a[0]) and (out[i][j] == 2147483647):
                out[i][j] = out[r][c] + 1
                queue.append((i, j))
    return out


def _reference_288(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None

    def abbreviation(s: str) -> str:
        return s if len(s) <= 2 else s[0] + str(len(s) - 2) + s[-1]

    return [all(s == word or abbreviation(s) != abbreviation(word) for word in a) for s in b]


def _reference_291(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None

    def match(i: int, j: int, mapping: dict[str, str]) -> bool:
        if i == len(a):
            return j == len(b)
        c = a[i]
        if c in mapping:
            return b.startswith(mapping[c], j) and match(i + 1, j + len(mapping[c]), mapping)
        return any(
            value not in mapping.values() and match(i + 1, k, {**mapping, c: value})
            for k in range(j + 1, len(b) + 1)
            for value in [b[j:k]]
        )

    return match(0, 0, {})


def _reference_293(number: int, args: list[Any]) -> Any:
    a: Any = args[0]

    def moves(s: str) -> list[str]:
        return [s[:i] + "--" + s[i + 2 :] for i in range(len(s) - 1) if s[i : i + 2] == "++"]

    @lru_cache(None)
    def win(s: str) -> bool:
        return any(not win(child) for child in moves(s))

    return moves(a) if number == 293 else win(a)


def _reference_296(number: int, args: list[Any]) -> Any:
    a: Any = args[0]
    homes = [(r, c) for r in range(len(a)) for c in range(len(a[0])) if a[r][c]]
    return min(
        sum((abs(r - i) + abs(c - j) for i, j in homes))
        for r in range(len(a))
        for c in range(len(a[0]))
    )


REFERENCES = {
    156: _reference_156,
    157: _reference_157,
    158: _reference_158,
    159: _reference_159,
    161: _reference_161,
    163: _reference_163,
    170: _reference_170,
    186: _reference_186,
    243: _reference_243,
    244: _reference_243,
    245: _reference_243,
    246: _reference_246,
    247: _reference_246,
    248: _reference_246,
    249: _reference_249,
    250: _reference_250,
    298: _reference_250,
    251: _reference_251,
    252: _reference_252,
    253: _reference_253,
    254: _reference_254,
    255: _reference_255,
    256: _reference_256,
    265: _reference_256,
    259: _reference_259,
    261: _reference_261,
    266: _reference_266,
    267: _reference_267,
    269: _reference_269,
    270: _reference_270,
    272: _reference_270,
    285: _reference_270,
    271: _reference_271,
    276: _reference_276,
    277: _reference_277,
    280: _reference_280,
    281: _reference_281,
    286: _reference_286,
    288: _reference_288,
    291: _reference_291,
    293: _reference_293,
    294: _reference_293,
    296: _reference_296,
}


def reference(number: int, args: list[Any]) -> Any:
    return REFERENCES[number](number, args)
