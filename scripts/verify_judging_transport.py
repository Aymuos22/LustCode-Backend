import json
import subprocess
from pathlib import Path

from app.judging.contracts import JudgeProfile
from app.judging.drivers import build_source, type_name
from app.judging.wire import pack_stdin
from app.models import Language
from app.schemas import FunctionParameter, FunctionSignature

root = Path("/tmp/lustcode-native-echo")
root.mkdir(exist_ok=True)
values = {
    "integer": -2147483648,
    "double": -123.25,
    "boolean": True,
    "string": '"\n\x00é🙂\\u0022#',
    "character": "\n",
    "integer[]": [-2147483648, 0, 2147483647],
    "integer[][]": [[], [-1, 2], [3]],
    "string[]": ["", "a", "#", "🙂"],
    "boolean[]": [True, False],
    "character[][]": [["a", "\x00"], ["\n", '"']],
    "list<string>": ["a", ""],
    "list<list<integer>>": [[1, 2], [], [-1]],
    "list<list<string>>": [["a", "b"], [], ["é"]],
    "ListNode[]": [[], [1, 2], [-3]],
    "list<TreeNode>": [[1, None, 2], [], [3]],
    "TreeNode": [1, None, 2, 3],
    "ListNode": [1, 2, 3],
}
checks = []
subprocess.run(
    [
        "docker",
        "run",
        "-d",
        "--name",
        "lustcode-judging-jdk",
        "--network",
        "none",
        "--memory=512m",
        "-v",
        str(root) + ":/work",
        "-w",
        "/work",
        "eclipse-temurin:21-jdk",
        "sleep",
        "600",
    ],
    check=True,
    capture_output=True,
)
try:
    for kind, value in values.items():
        profile = JudgeProfile(
            signature=FunctionSignature(
                name="echo",
                parameters=[FunctionParameter(name="value", type=kind)],
                return_type=kind,
            ),
            comparison="float" if kind == "double" else "exact",
            suite_version="wire-transport-check",
            test_count=2,
        )
        for lang in [Language.CPP, Language.JAVA]:
            native = type_name(kind, lang)
            source = (
                f"class Solution {{public: {native} echo({native} value){{return value;}}}};"
                if lang == Language.CPP
                else f"class Solution {{public {native} echo({native} value){{return value;}}}}"
            )
            code = build_source(source, lang, json.dumps([value]), profile)
            filename = root / ("main.cpp" if lang == Language.CPP else "Main.java")
            filename.write_text(code)
            cmd = (
                ["clang++", "-std=c++17", "-O0", str(filename), "-o", str(root / "program")]
                if lang == Language.CPP
                else ["docker", "exec", "lustcode-judging-jdk", "javac", "Main.java"]
            )
            compiled = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if compiled.returncode:
                raise RuntimeError(f"{lang.value}/{kind}: " + compiled.stderr[:1000])
            run_cmd = (
                [str(root / "program")]
                if lang == Language.CPP
                else ["docker", "exec", "-i", "lustcode-judging-jdk", "java", "Main"]
            )
            result = subprocess.run(
                run_cmd,
                input=pack_stdin(json.dumps([value]), lang),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode:
                raise RuntimeError(f"{lang.value}/{kind}: " + result.stderr[:1000])
            actual = json.loads(result.stdout)
            assert actual == value, (lang, kind, actual, value)
            checks.append({"language": lang.value, "type": kind, "passed": True})
            print(json.dumps(checks[-1]), flush=True)
    # Large values must not grow Java bytecode and full output must survive transport.
    large = [1] * 9000
    stdin = json.dumps([large])
    profile = JudgeProfile(
        signature=FunctionSignature(
            name="echo",
            parameters=[FunctionParameter(name="value", type="integer[]")],
            return_type="integer[]",
        ),
        suite_version="large-transport",
        test_count=2,
    )
    (root / "Main.java").write_text(
        build_source(
            "class Solution {public int[] echo(int[] value){return value;}}",
            Language.JAVA,
            stdin,
            profile,
        )
    )
    subprocess.run(
        ["docker", "exec", "lustcode-judging-jdk", "javac", "Main.java"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    result = subprocess.run(
        ["docker", "exec", "-i", "lustcode-judging-jdk", "java", "Main"],
        input=pack_stdin(stdin, Language.JAVA),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert json.loads(result.stdout) == large and len(result.stdout) > 16384
    checks.append(
        {
            "language": "java",
            "type": "integer[9000]",
            "output_bytes": len(result.stdout),
            "passed": True,
        }
    )
finally:
    subprocess.run(["docker", "rm", "-f", "lustcode-judging-jdk"], capture_output=True)
Path("/tmp/lustcode-native-echo-results.json").write_text(json.dumps(checks, indent=2))
print(json.dumps({"passed": len(checks)}), flush=True)
