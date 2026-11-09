"""Stateful class drivers and independently authored operation-sequence oracles."""

import re
from collections import OrderedDict
from typing import Any

from app.judging import runtimes
from app.judging.contracts import JudgeProfile, arguments
from app.judging.extra_references import traversal, tree
from app.models import Language
from app.schemas import FunctionParameter, FunctionSignature, QuestionInterface

PEEKING = QuestionInterface(
    kind="design",
    class_name="PeekingIterator",
    constructor=FunctionSignature(
        name="PeekingIterator", parameters=[FunctionParameter(name="iterator", type="Iterator")]
    ),
    methods=[
        FunctionSignature(name="peek", return_type="integer"),
        FunctionSignature(name="next", return_type="integer"),
        FunctionSignature(name="hasNext", return_type="boolean"),
    ],
)
ITERATOR_PY = """
class Iterator:
    def __init__(self,nums): self._values=list(nums); self._index=0
    def hasNext(self): return self._index<len(self._values)
    def next(self): value=self._values[self._index];self._index+=1;return value
"""
ITERATOR_CPP = """
class Iterator {
    vector<int> values; size_t index=0;
public:
    Iterator(const vector<int>& nums):values(nums){}
    Iterator(const Iterator& other)=default;
    virtual ~Iterator(){}
    int next(){return values.at(index++);}
    bool hasNext()const{return index<values.size();}
};
"""


def _parameter(kind: str, language: Language) -> str:
    from app.judging.drivers import type_name

    if kind == "Iterator":
        return "const vector<int>&" if language == Language.CPP else "Iterator<Integer>"
    return type_name(kind, language)


def starter(profile: JudgeProfile) -> dict[str, str]:
    assert profile.design and profile.design.constructor
    design = profile.design
    constructor = design.constructor
    assert constructor is not None
    name = design.class_name
    py = (
        f"class {name}:\n    def __init__(self"
        + "".join(", " + p.name for p in constructor.parameters)
        + "):\n        pass\n"
    )
    cpp = (
        f"class {name}"
        + (" : public Iterator" if name == "PeekingIterator" else "")
        + " {\npublic:\n    "
        + str(name)
        + "("
        + ", ".join(_parameter(p.type, Language.CPP) + " " + p.name for p in constructor.parameters)
        + ")"
        + (" : Iterator(iterator)" if name == "PeekingIterator" else "")
        + " {}\n"
    )
    java = (
        f"class {name} {{\n    public {name}("
        + ", ".join(
            _parameter(p.type, Language.JAVA) + " " + p.name for p in constructor.parameters
        )
        + ") {}\n"
    )
    for method in design.methods:
        py += (
            f"\n    def {method.name}(self"
            + "".join(", " + p.name for p in method.parameters)
            + "):\n        raise NotImplementedError\n"
        )
        cpp += (
            "    "
            + _parameter(method.return_type or "void", Language.CPP)
            + " "
            + method.name
            + "("
            + ", ".join(_parameter(p.type, Language.CPP) + " " + p.name for p in method.parameters)
            + ') { throw runtime_error("Implement"); }\n'
        )
        java += (
            "    public "
            + _parameter(method.return_type or "void", Language.JAVA)
            + " "
            + method.name
            + "("
            + ", ".join(_parameter(p.type, Language.JAVA) + " " + p.name for p in method.parameters)
            + ") { throw new UnsupportedOperationException(); }\n"
        )
    return {"python": py, "cpp": cpp + "};\n", "java": java + "}\n"}


def build_source(source: str, language: Language, stdin: str, profile: JudgeProfile) -> str:
    from app.judging import wire
    from app.judging.drivers import type_name

    arguments(stdin, profile)
    assert profile.design and profile.design.constructor
    design = profile.design
    constructor = design.constructor
    assert constructor is not None

    def declarations(signature: FunctionSignature, prefix: str) -> tuple[list[str], list[str]]:
        lines = []
        names = []
        for j, param in enumerate(signature.parameters):
            name = f"_lc_{prefix}_{j}"
            names.append(name)
            if language == Language.PYTHON:
                expression = (
                    f"Iterator(_lc_row[{j}])"
                    if param.type == "Iterator"
                    else f"_lc_from(_lc_row[{j}],{param.type!r})"
                )
                lines.append(name + "=" + expression)
            elif language == Language.CPP:
                kind = (
                    "vector<int>" if param.type == "Iterator" else type_name(param.type, language)
                )
                lines.append(f"{kind} {name}=LCRead<{kind}>::get();")
            else:
                kind = (
                    "Iterator<Integer>"
                    if param.type == "Iterator"
                    else type_name(param.type, language)
                )
                expression = (
                    wire.java_name("list<integer>" if param.type == "Iterator" else param.type)
                    + f"(_lc_row.get({j}))"
                    + (".iterator()" if param.type == "Iterator" else "")
                )
                lines.append(f"{kind} {name}={expression};")
        return lines, names

    lines = []
    if language == Language.PYTHON:
        lines = [
            "_lc_input=json.load(sys.stdin)",
            "_lc_ops,_lc_params=_lc_input",
            "_lc_row=_lc_params[0]",
        ]
    elif language == Language.CPP:
        lines = [
            (
                "lcWireLine();int _lc_count=stoi(lcWireLine().substr(2));vector<string>"
                " _lc_ops;for(int i=0;i<_lc_count;i++)_lc_ops.push_back(LCRead<string>:"
                ":get());lcWireLine();lcWireLine();"
            )
        ]
    else:
        lines = [
            (
                "List<?> _lc_input=(List<?>)LCWire.read();List<?> "
                "_lc_ops=(List<?>)_lc_input.get(0),_lc_params=(List<?>)_lc_input.get(1)"
                ",_lc_row=(List<?>)_lc_params.get(0);"
            )
        ]
    initial, names = declarations(constructor, "ctor")
    lines.extend(initial)
    joined = ",".join(names)
    if language == Language.PYTHON:
        lines += [
            f"_lc_object={design.class_name}({joined})",
            "_lc_outputs=[None]",
            "for _lc_i in range(1,len(_lc_ops)):",
            "    _lc_row=_lc_params[_lc_i]",
        ]
    elif language == Language.CPP:
        lines += [
            f"{design.class_name} _lc_object{{{joined}}};",
            'vector<string> _lc_outputs{"null"};',
            "for(size_t _lc_i=1;_lc_i<_lc_ops.size();_lc_i++){lcWireLine();",
        ]
    else:
        lines += [
            f"{design.class_name} _lc_object=new {design.class_name}({joined});",
            'List<String> _lc_outputs=new ArrayList<>();_lc_outputs.add("null");',
            "for(int _lc_i=1;_lc_i<_lc_ops.size();_lc_i++){_lc_row=(List<?>)_lc_params.get(_lc_i);",
        ]
    for i, method in enumerate(design.methods):
        branch, names = declarations(method, f"method{i}")
        call = f"_lc_object.{method.name}(" + ",".join(names) + ")"
        void = not method.return_type or method.return_type == "void"
        if language == Language.PYTHON:
            lines.append(
                ("    if " if i == 0 else "    elif ") + f"_lc_ops[_lc_i]=={method.name!r}:"
            )
            lines.extend("        " + line for line in branch)
            if void:
                lines.append("        " + call)
            lines.append("        _lc_outputs.append(" + ("None" if void else call) + ")")
        else:
            condition = (
                f'_lc_ops[_lc_i]=="{method.name}"'
                if language == Language.CPP
                else f'_lc_ops.get(_lc_i).equals("{method.name}")'
            )
            lines.append(("if" if i == 0 else "else if") + "(" + condition + "){")
            lines.extend(branch)
            if void:
                lines.append(call + ";")
            lines.append(
                "_lc_outputs."
                + ("push_back(" if language == Language.CPP else "add(")
                + ('"null"' if void else "lcJson(" + call + ")")
                + ");}"
            )
    if language == Language.PYTHON:
        lines += [
            "    else: raise ValueError('unknown operation')",
            wire.render_output(
                "json.dumps(_lc_encode(_lc_outputs),separators=(',',':'),allow_nan=False)", language
            ),
        ]
        return (
            runtimes.PYTHON
            + wire.PYTHON
            + "\n_lc_result_output=sys.stdout\nsys.stdout=sys.stderr\n"
            + ITERATOR_PY
            + "\n"
            + source
            + "\n"
            + "\n".join(lines)
            + "\n"
        )
    if language == Language.CPP:
        lines += [
            'else{throw runtime_error("unknown operation");}}',
            (
                'string _lc_combined="[";for(size_t i=0;i<_lc_outputs.size();i++){'
                'if(i)_lc_combined+=",";_lc_combined+=_lc_outputs[i];}_lc_combined+="]";'
            ),
            wire.render_output("_lc_combined", language),
        ]
        return (
            runtimes.CPP
            + wire.CPP
            + ITERATOR_CPP
            + "\n"
            + source
            + "\nint main(){\n"
            + "\n".join(lines)
            + "\n}\n"
        )
    kinds = [p.type for method in [constructor, *design.methods] for p in method.parameters]
    lines += [
        'else{throw new IllegalArgumentException("unknown operation");}}',
        wire.render_output('"["+String.join(",",_lc_outputs)+"]"', language),
    ]
    return (
        runtimes.JAVA
        + wire.JAVA
        + "}\n"
        + source
        + "\n"
        + runtimes.JAVA_MAIN
        + wire.java_converters(kinds)
        + "\npublic static void main(String[]args)throws Exception {\n"
        + "\n".join(lines)
        + "\n}\n}\n"
    )


def reference(number: int, args: list[Any]) -> list[Any]:
    operations, params = args
    out = [None]
    values = []
    cache: OrderedDict[int, int] = OrderedDict()
    words = set()
    index = 0
    if number == 173:
        values = traversal(tree(params[0][0]))
    if number == 284:
        values = params[0][0][:]
    for name, operands in zip(operations[1:], params[1:], strict=True):
        result: Any = None
        if number == 146:
            if name == "put":
                key, value = operands
                if key in cache:
                    del cache[key]
                cache[key] = value
                if len(cache) > params[0][0]:
                    cache.popitem(last=False)
            else:
                key = operands[0]
                result = cache.get(key, -1)
                if key in cache:
                    cache.move_to_end(key)
        elif number in {155, 225, 232}:
            if name == "push":
                values.append(operands[0])
            elif name == "pop":
                result = values.pop(0 if number == 232 else -1)
                result = None if number == 155 else result
            elif name == "getMin":
                result = min(values)
            elif name in {"top", "peek"}:
                result = values[0 if number == 232 else -1]
            else:
                result = not values
        elif number in {173, 284}:
            if name == "hasNext":
                result = index < len(values)
            else:
                result = values[index]
                index += int(name == "next")
        elif number in {208, 211}:
            text = operands[0]
            if name in {"insert", "addWord"}:
                words.add(text)
            elif name == "startsWith":
                result = any(word.startswith(text) for word in words)
            elif number == 208:
                result = text in words
            else:
                result = any(re.fullmatch(text, word) is not None for word in words)
        elif number == 295:
            if name == "addNum":
                values.append(operands[0])
            else:
                ordered = sorted(values)
                n = len(values)
                result = (ordered[(n - 1) // 2] + ordered[n // 2]) / 2
        else:
            raise ValueError("Missing class oracle")
        out.append(result)
    return out


CASES: dict[int, list[list[Any]]] = {
    146: [
        [
            ["LRUCache", "put", "put", "get", "put", "get", "get"],
            [[2], [1, 1], [2, 2], [1], [3, 3], [2], [3]],
        ],
        [["LRUCache", "put", "put", "get"], [[1], [1, 4], [1, 9], [1]]],
        [["LRUCache", "get", "put", "get"], [[1], [4], [0, 7], [0]]],
    ],
    155: [
        [
            ["MinStack", "push", "push", "getMin", "pop", "top", "getMin"],
            [[], [2], [-2], [], [], [], []],
        ],
        [["MinStack", "push", "push", "push", "pop", "getMin"], [[], [1], [1], [2], [], []]],
        [["MinStack", "push", "top", "getMin"], [[], [-2147483648], [], []]],
    ],
    173: [
        [["BSTIterator", "hasNext", "next", "hasNext"], [[[1]], [], [], []]],
        [["BSTIterator", "next", "next", "next", "hasNext"], [[[2, 1, 3]], [], [], [], []]],
    ],
    208: [
        [
            ["Trie", "insert", "search", "search", "startsWith"],
            [[], ["apple"], ["apple"], ["app"], ["app"]],
        ],
        [
            ["Trie", "insert", "insert", "search", "startsWith"],
            [[], ["ab"], ["abc"], ["a"], ["ab"]],
        ],
        [["Trie", "search", "startsWith"], [[], ["x"], ["x"]]],
    ],
    211: [
        [
            ["WordDictionary", "addWord", "addWord", "search", "search"],
            [[], ["bad"], ["dad"], [".ad"], ["b.."]],
        ],
        [["WordDictionary", "addWord", "search", "search"], [[], ["a"], ["."], [".."]]],
        [["WordDictionary", "search", "addWord", "search"], [[], ["x"], ["x"], ["x"]]],
    ],
    225: [
        [
            ["MyStack", "push", "push", "top", "pop", "empty", "pop", "empty"],
            [[], [1], [2], [], [], [], [], []],
        ],
        [["MyStack", "empty", "push", "pop", "empty"], [[], [], [4], [], []]],
        [["MyStack", "push", "top"], [[], [9], []]],
    ],
    232: [
        [
            ["MyQueue", "push", "push", "peek", "pop", "empty", "pop", "empty"],
            [[], [1], [2], [], [], [], [], []],
        ],
        [["MyQueue", "push", "pop", "push", "peek"], [[], [1], [], [3], []]],
        [["MyQueue", "empty", "push", "empty"], [[], [], [9], []]],
    ],
    284: [
        [
            ["PeekingIterator", "peek", "peek", "next", "hasNext", "next", "hasNext"],
            [[[1, 2]], [], [], [], [], [], []],
        ],
        [["PeekingIterator", "next", "peek", "next", "hasNext"], [[[2, 1]], [], [], [], []]],
        [["PeekingIterator", "peek", "next", "hasNext"], [[[9]], [], [], []]],
    ],
    295: [
        [["MedianFinder", "addNum", "findMedian"], [[], [1], []]],
        [
            ["MedianFinder", "addNum", "addNum", "findMedian", "addNum", "findMedian"],
            [[], [-1], [2], [], [3], []],
        ],
        [["MedianFinder", "addNum", "addNum", "findMedian"], [[], [-100000], [100000], []]],
    ],
}
