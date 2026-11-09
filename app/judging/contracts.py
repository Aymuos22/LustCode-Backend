import hashlib
import json
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import Language
from app.schemas import FunctionSignature, QuestionInterface

PRIMITIVES = {"integer", "double", "boolean", "string", "character", "void"}
COMPARISONS = {
    "exact",
    "unordered",
    "nested_unordered",
    "groups",
    "float",
    "two_sum",
    "palindrome",
    "peak",
    "remove_element",
    "topological",
    "alien",
    "wiggle",
    "gray",
    "balanced_bst",
}


def element_type(kind: str) -> str | None:
    if kind.endswith("[]"):
        return kind[:-2]
    if kind.startswith("list<") and kind.endswith(">"):
        return kind[5:-1]
    return None


def supported_type(kind: str) -> bool:
    if kind in PRIMITIVES or kind in {"ListNode", "TreeNode", "Node", "Iterator"}:
        return True
    inner = element_type(kind)
    return inner is not None and supported_type(inner)


class JudgeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    protocol: Literal["function", "design"] = "function"
    design: QuestionInterface | None = None
    origin: Literal["leetcode_public", "lustcode"] = "leetcode_public"
    description: str = Field(default="", max_length=4000)
    signature: FunctionSignature
    native_signature: FunctionSignature | None = None
    adapter: Literal[
        "normal",
        "cycle",
        "intersection",
        "lca",
        "delete_node",
        "bad_version",
        "codec",
        "unsigned",
        "graph",
        "random_list",
        "next_tree",
        "relink",
    ] = "normal"
    comparison: str = "exact"
    result: Literal["return", "mutated_first", "prefix"] = "return"
    languages: list[Language] = Field(default_factory=lambda: list(Language), min_length=1)
    suite_version: str = Field(min_length=1, max_length=100)
    test_count: int = Field(ge=2, le=1000)
    suite_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    statement_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def valid_contract(self) -> "JudgeProfile":
        signatures = [self.signature] + ([self.native_signature] if self.native_signature else [])
        if self.protocol == "design":
            if (
                self.design is None
                or self.design.kind != "design"
                or self.design.constructor is None
            ):
                raise ValueError("Design judging requires a class constructor and methods")
            signatures += [self.design.constructor, *self.design.methods]
            if self.design.class_name != self.design.constructor.name:
                raise ValueError("Design class name must match its constructor")
        names = [
            name
            for signature in signatures
            for name in [signature.name, *(p.name for p in signature.parameters)]
        ]
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names):
            raise ValueError("Invalid function identifier")
        kinds = [
            kind
            for signature in signatures
            for kind in [*(p.type for p in signature.parameters), signature.return_type or "void"]
        ]
        if not all(supported_type(kind) for kind in kinds):
            raise ValueError("This driver does not support a signature type")
        if self.comparison not in COMPARISONS or len(set(self.languages)) != len(self.languages):
            raise ValueError("Invalid comparison or duplicate languages")
        if self.result != "return" and not self.signature.parameters:
            raise ValueError("Mutating contract needs a parameter")
        if (
            self.signature.return_type == "void"
            and self.protocol == "function"
            and self.result == "return"
            and self.adapter != "delete_node"
        ):
            raise ValueError("Void function must identify its mutated result")
        return self


def valid_value(value: Any, kind: str) -> bool:
    if kind == "Iterator":
        return valid_value(value, "integer[]")
    inner = element_type(kind)
    if inner:
        return (
            isinstance(value, list)
            and len(value) <= 10000
            and all(valid_value(v, inner) for v in value)
        )
    if kind == "integer":
        return type(value) is int and -(2**31) <= value < 2**31
    if kind == "double":
        return type(value) in (int, float) and math.isfinite(value)
    if kind == "boolean":
        return type(value) is bool
    if kind == "string":
        return isinstance(value, str) and len(value.encode()) <= 16384
    if kind == "character":
        return isinstance(value, str) and len(value) == 1 and ord(value) < 128
    if kind in {"TreeNode", "ListNode"}:
        return (
            isinstance(value, list)
            and len(value) <= 10000
            and all((v is None and kind == "TreeNode") or valid_value(v, "integer") for v in value)
        )
    return kind == "void" and value is None


def arguments(stdin: str, profile: JudgeProfile) -> list[Any]:
    values = json.loads(stdin)
    if profile.protocol == "design":
        if (
            not isinstance(values, list)
            or len(values) != 2
            or not isinstance(values[0], list)
            or not isinstance(values[1], list)
        ):
            raise ValueError("Design fixture requires operation and argument arrays")
        operations, params = values
        if (
            not operations
            or len(operations) != len(params)
            or len(operations) > 10000
            or not profile.design
        ):
            raise ValueError("Invalid operation sequence")
        methods = {m.name: m for m in profile.design.methods}
        for i, (name, args) in enumerate(zip(operations, params, strict=True)):
            signature = (
                profile.design.constructor
                if i == 0 and name == profile.design.class_name
                else methods.get(name)
                if i
                else None
            )
            if (
                signature is None
                or not isinstance(args, list)
                or len(args) != len(signature.parameters)
            ):
                raise ValueError("Unknown operation or invalid arity")
            if not all(
                valid_value(value, p.type)
                for value, p in zip(args, signature.parameters, strict=True)
            ):
                raise ValueError("Invalid typed operation argument")
        return values
    if not isinstance(values, list) or len(values) != len(profile.signature.parameters):
        raise ValueError("Test arguments do not match function signature")
    if not all(
        valid_value(value, parameter.type)
        for value, parameter in zip(values, profile.signature.parameters, strict=True)
    ):
        raise ValueError("Invalid typed test argument")
    return values


def suite_hash(cases: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(cases, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
