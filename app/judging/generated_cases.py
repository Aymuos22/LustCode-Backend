"""Deterministic bounded random cases, respecting each covered problem's domain."""

import random
from typing import Any


def generated_cases(number: int, count: int = 10) -> list[list[Any]]:
    rng = random.Random(846219340152 + number)
    cases = []
    for _ in range(count):
        size = rng.randint(1, 9)
        nums = [rng.randint(-5, 5) for _ in range(size)]
        positive = [rng.randint(1, 8) for _ in range(size)]
        text = "".join(rng.choice("abc") for _ in range(rng.randint(0, 8)))
        other = "".join(rng.choice("abc") for _ in range(rng.randint(0, 8)))
        case: list[Any] | None = None
        if number in {3, 5, 159}:
            case = [text]
        elif number == 4:
            left = sorted(nums)
            right = sorted(rng.randint(-8, 8) for _ in range(rng.randint(0, 8)))
            case = [left, right]
        elif number == 6:
            case = [text or "a", rng.randint(1, 6)]
        elif number in {7, 9, 231, 263}:
            case = [rng.randint(-(2**31), 2**31 - 1)]
        elif number == 8:
            case = [
                rng.choice(["", " ", "   ", "+", "-"])
                + str(rng.randint(0, 10**12))
                + rng.choice(["", " word", "x3"])
            ]
        elif number == 10:
            case = [
                text or "a",
                "".join(
                    rng.choice("abc.") + rng.choice(["", "*"]) for _ in range(rng.randint(1, 5))
                ),
            ]
        elif number == 11:
            case = [[rng.randint(0, 10) for _ in range(rng.randint(2, 12))]]
        elif number == 12:
            case = [rng.randint(1, 3999)]
        elif number == 14:
            case = [[text, other, text[:2]]]
        elif number in {15, 18}:
            case = (
                [nums + [rng.randint(-5, 5) for _ in range(max(0, 3 - len(nums)))]]
                if number == 15
                else [nums, rng.randint(-10, 10)]
            )
        elif number == 17:
            case = ["".join(rng.choice("23456789") for _ in range(rng.randint(1, 3)))]
        elif number == 20:
            case = ["".join(rng.choice("()[]{}") for _ in range(size))]
        elif number == 22:
            case = [rng.randint(1, 5)]
        elif number in {26, 80}:
            case = [sorted(nums)]
        elif number == 27:
            case = [[rng.randint(0, 50) for _ in range(size)], rng.randint(0, 100)]
        elif number == 28:
            case = [text or "a", other or "b"]
        elif number == 29:
            case = [rng.randint(-(2**31), 2**31 - 1), rng.choice([-9, -3, -1, 1, 2, 7])]
        elif number == 31:
            case = [positive]
        elif number == 32:
            case = ["".join(rng.choice("()") for _ in range(size))]
        elif number in {33, 153}:
            unique = sorted(rng.sample(range(-20, 21), size))
            pivot = rng.randrange(size)
            rotated = unique[pivot:] + unique[:pivot]
            case = [rotated, rng.randint(-20, 20)] if number == 33 else [rotated]
        elif number == 34:
            case = [sorted(nums), rng.randint(-5, 5)]
        elif number == 35:
            case = [sorted(set(nums)), rng.randint(-8, 8)]
        elif number == 38:
            case = [rng.randint(1, 7)]
        elif number in {39, 40}:
            case = [
                sorted(set(rng.randint(2, 9) for _ in range(size))) if number == 39 else positive,
                rng.randint(1, 16),
            ]
        elif number in {41, 53, 152, 164, 217, 229, 238, 283, 300}:
            if number == 164:
                case = [positive]
            elif number == 238:
                case = [nums + [rng.randint(-3, 3)]]
            elif number == 152:
                case = [[rng.randint(-3, 3) for _ in range(size)]]
            else:
                case = [nums]
        elif number in {42, 84}:
            case = [[rng.randint(0, 8) for _ in range(size)]]
        elif number == 43:
            case = [str(rng.randint(0, 10**9)), str(rng.randint(0, 10**9))]
        elif number == 44:
            case = [text, "".join(rng.choice("abc?*") for _ in range(size))]
        elif number == 45:
            case = [[rng.randint(1, 3) for _ in range(size)]]
        elif number == 46:
            case = [rng.sample(range(-10, 11), rng.randint(1, 6))]
        elif number in {47, 90}:
            case = [[rng.randint(0, 2) for _ in range(rng.randint(1, 6))]]
        elif number in {48, 59}:
            n = rng.randint(1, 4)
            case = (
                [[[rng.randint(-9, 9) for _ in range(n)] for _ in range(n)]]
                if number == 48
                else [n]
            )
        elif number in {49, 249}:
            case = [[text, other, text[::-1], other[::-1]]]
        elif number == 50:
            case = [float(rng.choice([-4, -2, -1, 1, 2, 4])), rng.randint(-8, 8)]
        elif number in {51, 52}:
            case = [rng.randint(1, 6)]
        elif number in {54, 64, 73, 286, 296}:
            r, c = rng.randint(1, 4), rng.randint(1, 4)
            if number == 286:
                case = [[[rng.choice([-1, 0, 2147483647]) for _ in range(c)] for _ in range(r)]]
            elif number == 296:
                grid = [[rng.randint(0, 1) for _ in range(c)] for _ in range(r)]
                grid[0][0] = 1
                case = [grid]
            else:
                case = [[[rng.randint(0, 9) for _ in range(c)] for _ in range(r)]]
        elif number in {55, 198, 213}:
            case = [[rng.randint(0, 7) for _ in range(size)]]
        elif number == 56:
            case = [[[2 * i, 2 * i + rng.randint(0, 4)] for i in range(size)]]
        elif number == 57:
            case = [
                [[3 * i, 3 * i + 1] for i in range(size)],
                [rng.randint(0, 6), rng.randint(7, 20)],
            ]
        elif number == 58:
            case = [(text or "a") + " " + (other or "b") + " " * rng.randint(0, 3)]
        elif number == 62:
            case = [rng.randint(1, 12), rng.randint(1, 12)]
        elif number == 63:
            case = [[[rng.randint(0, 1) for _ in range(3)] for _ in range(3)]]
        elif number == 66:
            case = [[int(c) for c in str(rng.randint(0, 10**8))]]
        elif number == 67:
            case = [bin(rng.randint(0, 1024))[2:], bin(rng.randint(0, 1024))[2:]]
        elif number == 69:
            case = [rng.randint(0, 2**31 - 1)]
        elif number == 70:
            case = [rng.randint(1, 45)]
        elif number in {72, 161}:
            case = [text, other]
        elif number == 75:
            case = [[rng.randint(0, 2) for _ in range(size)]]
        elif number == 76:
            case = None  # Public contract promises a unique optimum; use authored fixtures.
        elif number == 77:
            n = rng.randint(1, 7)
            case = [n, rng.randint(1, n)]
        elif number == 78:
            case = [rng.sample(range(-10, 11), rng.randint(1, 6))]
        elif number in {81, 154}:
            sorted_nums = sorted(nums)
            pivot = rng.randrange(size)
            rotated = sorted_nums[pivot:] + sorted_nums[:pivot]
            case = [rotated, rng.choice(nums)] if number == 81 else [rotated]
        elif number in {82, 83}:
            case = [sorted(nums)]
        elif number in {85, 200, 221}:
            case = [[[rng.choice("01") for _ in range(3)] for _ in range(3)]]
        elif number == 86:
            case = [positive, rng.randint(0, 9)]
        elif number == 89:
            case = [rng.randint(1, 6)]
        elif number == 91:
            case = ["".join(rng.choice("0123456789") for _ in range(size))]
        elif number == 96:
            case = [rng.randint(1, 10)]
        elif number == 115:
            case = [text or "a", other or "b"]
        elif number in {118, 119}:
            case = [rng.randint(1, 10) if number == 118 else rng.randint(0, 15)]
        elif number in {121, 122, 123}:
            case = [positive]
        elif number == 125:
            case = [text + ":" + rng.choice([text[::-1], other])]
        elif number in {128, 147, 148, 206}:
            case = [nums]
        elif number == 135:
            case = [positive]
        elif number == 136:
            chosen = rng.sample(range(-10, 11), 4)
            arr = chosen[:3] * 2 + chosen[3:]
            rng.shuffle(arr)
            case = [arr]
        elif number == 137:
            chosen = rng.sample(range(-10, 11), 4)
            arr = chosen[:3] * 3 + chosen[3:]
            rng.shuffle(arr)
            case = [arr]
        elif number == 150:
            case = [[str(positive[0]), str(rng.randint(1, 9)), "-", str(rng.randint(1, 9)), "*"]]
        elif number == 151:
            case = ["  " + (text or "a") + "   " + (other or "b") + " "]
        elif number == 165:
            case = [
                ".".join(str(rng.randint(0, 20)) for _ in range(3)),
                ".".join(str(rng.randint(0, 20)) for _ in range(2)),
            ]
        elif number == 166:
            case = [rng.randint(-100, 100), rng.choice([-13, -7, -2, 2, 3, 7, 11])]
        elif number == 168:
            case = [rng.randint(1, 10000)]
        elif number == 169:
            repeated = rng.randint(-5, 5)
            arr = [repeated] * 6 + nums[:4]
            rng.shuffle(arr)
            case = [arr]
        elif number == 172:
            case = [rng.randint(0, 10000)]
        elif number == 179:
            case = [[rng.randint(0, 999) for _ in range(rng.randint(1, 6))]]
        elif number == 189:
            case = [nums, rng.randint(0, 20)]
        elif number == 190:
            case = [2 * rng.randint(0, 2**30 - 1)]
        elif number == 191:
            case = [rng.randint(1, 2**31 - 1)]
        elif number == 201:
            lo = rng.randint(0, 1000)
            case = [lo, lo + rng.randint(0, 300)]
        elif number == 202:
            case = [rng.randint(1, 10000)]
        elif number == 203:
            case = [positive, rng.randint(1, 9)]
        elif number == 204:
            case = [rng.randint(0, 1000)]
        elif number == 209:
            case = [rng.randint(1, 50), positive]
        elif number == 215:
            case = [nums, rng.randint(1, size)]
        elif number == 216:
            case = [rng.randint(2, 6), rng.randint(1, 50)]
        elif number == 219:
            case = [nums, rng.randint(0, 10)]
        elif number == 220:
            case = [nums + [0], rng.randint(1, size), rng.randint(0, 8)]
        elif number == 228:
            case = [sorted(set(nums))]
        elif number == 233:
            case = [rng.randint(0, 300)]
        elif number == 234:
            case = [[rng.randint(0, 9) for _ in range(size)]]
        elif number == 239:
            case = [nums, rng.randint(1, size)]
        elif number == 242:
            case = [text or "a", rng.choice([other or "b", (text or "a")[::-1]])]
        elif number == 258:
            case = [rng.randint(0, 2**31 - 1)]
        elif number == 260:
            chosen = rng.sample(range(-10, 11), 5)
            arr = chosen[:3] * 2 + chosen[3:]
            rng.shuffle(arr)
            case = [arr]
        elif number == 264:
            case = [rng.randint(1, 100)]
        elif number == 268:
            missing = rng.randint(0, size)
            arr = [i for i in range(size + 1) if i != missing]
            rng.shuffle(arr)
            case = [arr]
        elif number in {274, 275}:
            citations = [rng.randint(0, 20) for _ in range(size)]
            case = [sorted(citations) if number == 275 else citations]
        elif number == 279:
            case = [rng.randint(1, 100)]
        elif number == 287:
            arr = list(range(1, size + 1)) + [rng.randint(1, size)]
            rng.shuffle(arr)
            case = [arr]
        elif number == 289:
            case = [[[rng.randint(0, 1) for _ in range(3)] for _ in range(3)]]
        elif number == 292:
            case = [rng.randint(1, 2**31 - 1)]
        elif number == 299:
            case = [
                "".join(rng.choice("0123456789") for _ in range(size)),
                "".join(rng.choice("0123456789") for _ in range(size)),
            ]
        if case is not None:
            if number == 50 and abs(case[0] ** case[1]) > 10000:
                continue
            cases.append(case)
    return cases
