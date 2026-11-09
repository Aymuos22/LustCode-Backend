import json
import re
import subprocess
from pathlib import Path

from app.ingestion.catalog import CatalogBundle
from app.judging import runtimes
from app.judging.drivers import build_source
from app.judging.suites import build_suites
from app.models import Language

bundle = CatalogBundle.model_validate_json(Path("data/questions/leetcode_001_300.json").read_text())
suites = build_suites(bundle)
root = Path("/tmp/lustcode-judging-compile")
root.mkdir(exist_ok=True)
cpp = [runtimes.CPP]
java = []
for number, suite in suites.items():
    p = suite["profile"]
    args = suite["cases"][0]["stdin"]
    generated = (
        build_source(suite["starter_code"]["cpp"], Language.CPP, args, p)
        .removeprefix(runtimes.CPP)
        .replace("int main(){", "void check(){")
    )
    cpp.append(f"namespace Q{number} {{\n" + generated + "\n}")
    generated = build_source(suite["starter_code"]["java"], Language.JAVA, args, p).removeprefix(
        runtimes.JAVA
    )
    prefix, tail = generated.split(runtimes.JAVA_MAIN)
    prefix = re.sub(r"(?m)^class ", "static class ", prefix)
    match = re.search(r"public static void main\(String\[\].*?throws Exception \{\n", tail)
    converters = tail[: match.start()]
    body = tail[match.end() :]
    body = body.removesuffix("\n}\n}\n")
    java.append(
        f"static class Q{number} {{\n"
        + prefix
        + "\n"
        + converters
        + "\nstatic void check() throws Exception {\n"
        + body
        + "\n}\n}"
    )
(root / "all.cpp").write_text("\n".join(cpp) + "\nint main(){return 0;}\n")
(root / "Main.java").write_text(
    runtimes.JAVA
    + runtimes.JAVA_MAIN
    + "\n"
    + "\n".join(java)
    + "\npublic static void main(String[] args){}\n}\n"
)
results = []
for lang, cmd in [
    ("cpp", ["clang++", "-std=c++17", "-fsyntax-only", str(root / "all.cpp")]),
    (
        "java",
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory=1g",
            "-v",
            str(root) + ":/work",
            "-w",
            "/work",
            "eclipse-temurin:21-jdk",
            "javac",
            "Main.java",
        ],
    ),
]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    (root / (lang + ".log")).write_text(r.stdout + r.stderr)
    results.append({"language": lang, "signatures": len(suites), "passed": r.returncode == 0})
    print(json.dumps(results[-1]), flush=True)
    if r.returncode:
        print((r.stdout + r.stderr)[:3000], flush=True)
Path("/tmp/lustcode-judging-compile-results.json").write_text(json.dumps(results, indent=2))
raise SystemExit(0 if all(r["passed"] for r in results) else 1)
