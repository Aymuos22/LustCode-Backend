"""Verified fixture adapters for public problems with special method contracts."""

import re
from typing import Any

from app.judging.extra_references import serialize, tree
from app.schemas import FunctionParameter, FunctionSignature


def function(name: str, params: list[tuple[str, str]], result: str) -> FunctionSignature:
    return FunctionSignature(
        name=name,
        parameters=[FunctionParameter(name=n, type=t) for n, t in params],
        return_type=result,
    )


NATIVE = {
    141: function("hasCycle", [("head", "ListNode")], "boolean"),
    142: function("detectCycle", [("head", "ListNode")], "ListNode"),
    160: function(
        "getIntersectionNode", [("headA", "ListNode"), ("headB", "ListNode")], "ListNode"
    ),
    235: function(
        "lowestCommonAncestor",
        [("root", "TreeNode"), ("p", "TreeNode"), ("q", "TreeNode")],
        "TreeNode",
    ),
    236: function(
        "lowestCommonAncestor",
        [("root", "TreeNode"), ("p", "TreeNode"), ("q", "TreeNode")],
        "TreeNode",
    ),
    237: function("deleteNode", [("node", "ListNode")], "void"),
    278: function("firstBadVersion", [("n", "integer")], "integer"),
    297: function("deserialize", [("data", "string")], "TreeNode"),
}
ADAPTERS = {
    141: "cycle",
    142: "cycle",
    160: "intersection",
    190: "unsigned",
    235: "lca",
    236: "lca",
    237: "delete_node",
    278: "bad_version",
    297: "codec",
}
DESCRIPTIONS = {
    141: (
        "Implement hasCycle(head). The fixture-only pos connects the tail to a "
        "zero-based node position, or -1 for no cycle; pos is not a method argument."
    ),
    142: (
        "Implement detectCycle(head), returning the original entry node or null. The "
        "fixture-only pos creates the cycle. Output compares node identity, not just "
        "value."
    ),
    160: (
        "Implement getIntersectionNode(headA,headB), returning the original shared "
        "node or null. Fixtures create the shared tail from skipA/skipB; these values "
        "are not method arguments. New nodes with matching values are rejected."
    ),
    190: (
        "Reverse all 32 bits. Java signed int results are interpreted as unsigned "
        "32-bit values for comparison."
    ),
    235: (
        "Implement lowestCommonAncestor(root,p,q). p and q are existing nodes, not "
        "integer arguments. Fixtures identify them by unique value; returned node "
        "identity is checked."
    ),
    236: (
        "Implement lowestCommonAncestor(root,p,q). p and q are existing nodes, not "
        "integer arguments. Fixtures identify them by unique value; returned node "
        "identity is checked."
    ),
    237: (
        "Implement deleteNode(node) in place. node is an existing non-tail node. The "
        "fixture includes the original head and target value; only the target node is "
        "passed to the method."
    ),
    278: (
        "Implement firstBadVersion(n), calling the provided isBadVersion(version) "
        "hook. The fixture-only bad value is not a method argument. Java Solution "
        "extends VersionControl."
    ),
    297: (
        "Implement class Codec with serialize(TreeNode)->string and "
        "deserialize(string)->TreeNode. Separate encoder and decoder instances must "
        "round-trip each input tree. Your serialized format is unrestricted."
    ),
}


def reference(number: int, args: list[Any]) -> Any:
    if number in {116, 117}:
        rows = []
        level = [tree(args[0])] if args[0] else []
        while level:
            rows.append([n[0] for n in level])
            level = [c for n in level for c in n[1:] if c]
        return rows
    if number == 133:
        return [sorted(row) for row in args[0]]
    if number == 138:
        return [[v, None if r < 0 else r] for v, r in zip(args[0], args[1], strict=True)]
    a: Any = args[0]
    b: Any = args[1] if len(args) > 1 else None
    if number == 37:
        board = [row[:] for row in a]

        def fill() -> bool:
            empty = next(((r, c) for r in range(9) for c in range(9) if board[r][c] == "."), None)
            if empty is None:
                return True
            r, c = empty
            used = (
                set(board[r])
                | {board[i][c] for i in range(9)}
                | {
                    board[i][j]
                    for i in range(r // 3 * 3, r // 3 * 3 + 3)
                    for j in range(c // 3 * 3, c // 3 * 3 + 3)
                }
            )
            for digit in "123456789":
                if digit not in used:
                    board[r][c] = digit
                    if fill():
                        return True
            board[r][c] = "."
            return False

        if not fill():
            raise ValueError("Unsolvable authored Sudoku")
        return board
    if number == 89:
        return [i ^ (i >> 1) for i in range(1 << a)]
    if number == 95:

        def trees(low: int, high: int) -> list:
            if low > high:
                return [None]
            return [
                [i, left, right]
                for i in range(low, high + 1)
                for left in trees(low, i - 1)
                for right in trees(i + 1, high)
            ]

        return [serialize(node) for node in trees(1, a)]
    if number in {108, 109}:

        def balanced(values: list) -> Any:
            if not values:
                return None
            i = len(values) // 2
            return [values[i], balanced(values[:i]), balanced(values[i + 1 :])]

        return serialize(balanced(a))
    if number == 141:
        return b >= 0
    if number == 142:
        return b
    if number == 160:
        return args[3] if a != 0 else -1
    if number == 190:
        return int(f"{a:032b}"[::-1], 2)
    if number in {224, 227}:
        tokens = re.findall(r"\d+|[()+*/-]", a)
        position = 0

        def expression(level: int = 0) -> int:
            nonlocal position
            token = tokens[position]
            position += 1
            if token in {"+", "-"}:
                left = expression(3) * (1 if token == "+" else -1)
            elif token == "(":
                left = expression()
                position += 1
            else:
                left = int(token)
            while position < len(tokens) and tokens[position] != ")":
                op = tokens[position]
                precedence = 1 if op in "+-" else 2
                if precedence < level:
                    break
                position += 1
                right = expression(precedence + 1)
                left = (
                    left + right
                    if op == "+"
                    else left - right
                    if op == "-"
                    else left * right
                    if op == "*"
                    else (abs(left) // abs(right)) * (-1 if (left < 0) != (right < 0) else 1)
                )
            return left

        return expression()
    if number in {235, 236}:
        root = tree(a)

        def path(node: Any, value: int) -> list:
            if not node:
                return []
            if node[0] == value:
                return [node[0]]
            tail = path(node[1], value) or path(node[2], value)
            return [node[0], *tail] if tail else []

        left, right = path(root, b), path(root, args[2])
        return [x for x, y in zip(left, right, strict=False) if x == y][-1]
    if number == 237:
        i = a.index(b)
        return a[:i] + a[i + 1 :]
    if number == 273:
        units = [
            "",
            "One",
            "Two",
            "Three",
            "Four",
            "Five",
            "Six",
            "Seven",
            "Eight",
            "Nine",
            "Ten",
            "Eleven",
            "Twelve",
            "Thirteen",
            "Fourteen",
            "Fifteen",
            "Sixteen",
            "Seventeen",
            "Eighteen",
            "Nineteen",
        ]
        tens = [
            "",
            "",
            "Twenty",
            "Thirty",
            "Forty",
            "Fifty",
            "Sixty",
            "Seventy",
            "Eighty",
            "Ninety",
        ]

        def words(n: int) -> str:
            if n < 20:
                return units[n]
            if n < 100:
                return (tens[n // 10] + " " + words(n % 10)).strip()
            if n < 1000:
                return (units[n // 100] + " Hundred " + words(n % 100)).strip()
            for value, name in [(10**9, "Billion"), (10**6, "Million"), (1000, "Thousand")]:
                if n >= value:
                    return (words(n // value) + " " + name + " " + words(n % value)).strip()
            raise ValueError("Unexpected number")

        return words(a) if a else "Zero"
    if number == 278:
        return b
    if number == 282:
        out = []

        def visit(i: int, text: str, value: int, last: int) -> None:
            if i == len(a):
                if value == b:
                    out.append(text)
                return
            for j in range(i + 1, len(a) + 1):
                if j > i + 1 and a[i] == "0":
                    break
                token = a[i:j]
                n = int(token)
                if i == 0:
                    visit(j, token, n, n)
                else:
                    visit(j, text + "+" + token, value + n, n)
                    visit(j, text + "-" + token, value - n, -n)
                    visit(j, text + "*" + token, value - last + last * n, last * n)

        visit(0, "", 0, 0)
        return out
    if number == 297:
        return serialize(tree(a))
    raise ValueError("Missing special reference")


CASES: dict[int, list[list[Any]]] = {
    37: [],
    89: [[1], [2], [3], [4], [5]],
    95: [[1], [2], [3], [4]],
    108: [[[1]], [[-1, 0, 1]], [[-10, -3, 0, 5, 9]], [[1, 2, 3, 4, 5, 6]]],
    109: [[[]], [[1]], [[-1, 0, 1]], [[1, 2, 3, 4, 5]]],
    141: [[[], -1], [[1], 0], [[1, 2, 3], 0], [[1, 2, 3], 2], [[1, 2, 3], -1]],
    142: [[[], -1], [[1], 0], [[1, 2, 3], 0], [[1, 2, 3], 2], [[1, 2, 3], -1]],
    160: [
        [0, [1, 2], [3, 4], 2, 2],
        [3, [1, 2, 3, 4], [5, 3, 4], 2, 1],
        [1, [1, 2], [1, 2], 0, 0],
        [2, [1, 2, 3], [2, 3], 1, 0],
    ],
    190: [[0], [4], [2], [43261596], [2147483646]],
    224: [["1"], ["1-(2-3)"], ["-(3+(4-5))"], ["2147483647"], ["2-(1+2) + 3"]],
    227: [["1"], ["3+2*2"], [" 3/2 "], ["14-3/2"], ["100/3*3+1"]],
    235: [
        [[2, 1, 3], 1, 3],
        [[6, 2, 8, 0, 4, 7, 9, None, None, 3, 5], 2, 4],
        [[3, 1, 4, None, 2], 1, 2],
    ],
    236: [[[2, 1, 3], 1, 3], [[3, 5, 1, 6, 2, 0, 8, None, None, 7, 4], 5, 4], [[1, 2], 1, 2]],
    237: [[[1, 2], 1], [[4, 5, 1, 9], 1], [[1, 2, 3, 4], 2], [[2, 5, 7], 5]],
    273: [[0], [1], [100], [1001], [1000010], [2147483647]],
    278: [[1, 1], [2, 1], [2, 2], [100, 99], [2147483647, 2147483647]],
    282: [["00", 0], ["105", 5], ["232", 8], ["123", 6], ["3456237490", 9191]],
    297: [[[]], [[1]], [[1, 2, 3, None, None, 4, 5]], [[-1, None, 2, 3]], [[0, 0, 0]]],
}
for shift in range(3):
    solved = [[str((r * 3 + r // 3 + c + shift) % 9 + 1) for c in range(9)] for r in range(9)]
    for i in range(shift + 1):
        solved[i][i] = "."
    CASES[37].append([solved])

CASES[236] += [[[4, 2, 6, 1, 3, 5, 7], 1, 3], [[4, 2, 6, 1, 3, 5, 7], 1, 7]]

FIXTURES = {
    133: function("cloneGraph", [("adjList", "integer[][]")], "integer[][]"),
    138: function(
        "copyRandomList", [("values", "integer[]"), ("randomIndices", "integer[]")], "integer[][]"
    ),
}
NATIVE.update(
    {
        116: function("connect", [("root", "Node")], "Node"),
        117: function("connect", [("root", "Node")], "Node"),
        133: function("cloneGraph", [("node", "Node")], "Node"),
        138: function("copyRandomList", [("head", "Node")], "Node"),
    }
)
ADAPTERS.update({116: "next_tree", 117: "next_tree", 133: "graph", 138: "random_list"})
DESCRIPTIONS.update(
    {
        116: (
            "Implement connect(Node root). Populate next pointers along each "
            "perfect-tree level, terminating each level with null. Return the original "
            "root. Node contains val, left, right, next."
        ),
        117: (
            "Implement connect(Node root) for an arbitrary binary tree. Populate next "
            "pointers in left-to-right level order, terminating each level with null. "
            "Return the original root. Node contains val, left, right, next."
        ),
        133: (
            "Implement cloneGraph(Node node). Node contains val and neighbors. Return "
            "a deep copy with no node shared with the input. Adjacency-list fixtures "
            "label nodes 1..n; neighbor order is irrelevant."
        ),
        138: (
            "Implement copyRandomList(Node head). Node contains val, next, random. "
            "Return a deep copy with no shared nodes. Fixtures specify values and "
            "zero-based randomIndices, with -1 for null. Output preserves next order "
            "and random-reference identity."
        ),
    }
)
CASES.update(
    {
        116: [[[]], [[1]], [[1, 2, 3]], [[1, 2, 3, 4, 5, 6, 7]], [[0, 0, 0]]],
        117: [[[]], [[1]], [[1, None, 2, 3]], [[1, 2, 3, None, 4, None, 5]]],
        133: [[[]], [[[]]], [[[2], [1]]], [[[2, 3], [1, 3], [1, 2]]], [[[2, 3, 4], [1], [1], [1]]]],
        138: [
            [[], []],
            [[1], [-1]],
            [[1], [0]],
            [[7, 13, 11, 10, 1], [-1, 0, 4, 2, 0]],
            [[1, 1, 1], [2, 0, 1]],
        ],
    }
)

ADAPTERS.update({24: "relink", 25: "relink", 143: "relink"})
