import json

from app.judging import runtimes, wire
from app.judging.adapters import prepare
from app.judging.contracts import JudgeProfile, arguments, element_type
from app.models import Language


def type_name(kind: str, language: Language, *, boxed: bool = False) -> str:
    inner = element_type(kind)
    if language == Language.CPP:
        if inner:
            return f"vector<{type_name(inner, language)}>"
        return {
            "integer": "int",
            "boolean": "bool",
            "character": "char",
            "ListNode": "ListNode*",
            "TreeNode": "TreeNode*",
            "Node": "Node*",
        }.get(kind, kind)
    if inner:
        if kind.endswith("[]"):
            return type_name(inner, language) + "[]"
        return f"List<{type_name(inner, language, boxed=True)}>"
    return {
        "integer": "Integer" if boxed else "int",
        "double": "Double" if boxed else "double",
        "boolean": "Boolean" if boxed else "boolean",
        "character": "Character" if boxed else "char",
        "string": "String",
    }.get(kind, kind)


def build_source(source: str, language: Language, stdin: str, profile: JudgeProfile) -> str:
    if language not in profile.languages:
        raise ValueError("Language does not have a verified driver")
    if profile.protocol == "design":
        from app.judging.design import build_source as build_design

        return build_design(source, language, stdin, profile)
    values = arguments(stdin, profile)
    native = profile.native_signature or profile.signature
    params = profile.signature.parameters
    names = [f"_lc_arg{i}" for i in range(len(params))]
    call = (
        "Solution()." + profile.signature.name
        if language == Language.PYTHON
        else "Solution()." + profile.signature.name
        if language == Language.CPP
        else "new Solution()." + profile.signature.name
    )
    call += "(" + ",".join(names) + ")"
    lines = (
        ["_lc_values=json.load(sys.stdin)"]
        if language == Language.PYTHON
        else ["lcWireLine();"]
        if language == Language.CPP
        else ["List<?> _lc_values=(List<?>)LCWire.read();"]
    )
    for name, param, _value in zip(names, params, values, strict=True):
        prefix = "" if language == Language.PYTHON else type_name(param.type, language) + " "
        expression = (
            f"_lc_from(_lc_values[{names.index(name)}],{param.type!r})"
            if language == Language.PYTHON
            else f"LCRead<{type_name(param.type, language)}>::get()"
            if language == Language.CPP
            else f"{wire.java_name(param.type)}(_lc_values.get({names.index(name)}))"
        )
        lines.append(
            f"{prefix}{name} = {expression}" + ("" if language == Language.PYTHON else ";")
        )
    prelude, setup, adapted_call, adapted_output = prepare(profile, language, values)
    lines.extend(setup)
    if adapted_call:
        call = adapted_call
    if profile.result == "mutated_first":
        lines.append(call + ("" if language == Language.PYTHON else ";"))
        result = names[0]
    else:
        lines.append(
            (
                "_lc_result = "
                if language == Language.PYTHON
                else "auto _lc_result = "
                if language == Language.CPP
                else type_name(native.return_type or "void", language) + " _lc_result = "
            )
            + call
            + ("" if language == Language.PYTHON else ";")
        )
        result = "_lc_result"
    if profile.result == "prefix":
        if language == Language.PYTHON:
            output = (
                "json.dumps({'length':_lc_result,'values':_lc_arg0[:_lc_result]},"
                "separators=(',',':'))"
            )
        elif language == Language.CPP:
            output = (
                r'string("{\"length\":")+lcJson(_lc_result)+",\"values\":"+'
                'lcJson(vector<int>(_lc_arg0.begin(),_lc_arg0.begin()+_lc_result))+"}"'
            )
        else:
            output = (
                r'"{\"length\":"+lcJson(_lc_result)+",\"values\":"+'
                'lcJson(Arrays.copyOf(_lc_arg0,_lc_result))+"}"'
            )
        if language == Language.PYTHON:
            output = (
                f"({output} if type(_lc_result) is int and "
                f"0<=_lc_result<=len(_lc_arg0) else {wire.INVALID_RESULT!r})"
            )
        else:
            bound = "_lc_arg0.size()" if language == Language.CPP else "_lc_arg0.length"
            output = (
                f"((_lc_result<0 || (size_t)_lc_result>{bound})?"
                f"string({json.dumps(wire.INVALID_RESULT)}):({output}))"
                if language == Language.CPP
                else (
                    f"((_lc_result<0 || _lc_result>{bound})?"
                    f"{json.dumps(wire.INVALID_RESULT)}:({output}))"
                )
            )
    else:
        # Empty node results are serialized as an empty list, matching the catalog's
        # tree/list representation rather than JSON null.
        result_type = (
            profile.signature.parameters[0].type
            if profile.result == "mutated_first"
            else native.return_type
        )
        if language == Language.PYTHON:
            encoded = f"_lc_typed({result},{result_type!r})"
            output = f"json.dumps({encoded},separators=(',',':'),allow_nan=False)"
        else:
            output = f"lcJson({result})"
            if language == Language.JAVA:
                output = f'lcTyped({result},"{result_type}")'
    if adapted_output:
        output = adapted_output
    if profile.adapter == "unsigned":
        output = (
            "json.dumps(_lc_result & 4294967295)"
            if language == Language.PYTHON
            else "lcJson(((long long)_lc_result)&4294967295LL)"
            if language == Language.CPP
            else "lcJson(((long)_lc_result)&4294967295L)"
        )
    if language == Language.PYTHON:
        return (
            runtimes.PYTHON
            + "\n"
            + wire.PYTHON
            + "\n_lc_result_output=sys.stdout\nsys.stdout=sys.stderr\n"
            + prelude
            + source
            + "\n"
            + "\n".join(lines)
            + "\n"
            + wire.render_output(output, language)
        )
    if language == Language.CPP:
        return (
            runtimes.CPP
            + "\n"
            + wire.CPP
            + prelude
            + source
            + "\nint main(){\n"
            + "\n".join(lines)
            + "\n"
            + wire.render_output(output, language)
            + "}\n"
        )
    return (
        runtimes.JAVA
        + "\n"
        + wire.JAVA
        + "}\n"
        + prelude
        + source
        + "\n"
        + runtimes.JAVA_MAIN
        + wire.java_converters([p.type for p in params])
        + "\npublic static void main(String[] args) throws Exception {\n"
        + "\n".join(lines)
        + "\n"
        + wire.render_output(output, language)
        + "}\n}\n"
    )
