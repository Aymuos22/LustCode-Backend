from app.models import Language
from app.schemas import LanguageView

NAMES = {Language.PYTHON: "Python", Language.JAVA: "Java", Language.CPP: "C++"}
STARTERS = {
    Language.PYTHON: """import sys

def main():
    data = sys.stdin.read()
    print(data, end='')

if __name__ == '__main__':
    main()
""",
    Language.JAVA: (
        "import java.io.*;\n"
        "import java.util.*;\n"
        "\n"
        "class Main {\n"
        "    public static void main(String[] args) throws Exception {\n"
        "        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));\n"
        "        String line;\n"
        "        while ((line = reader.readLine()) != null) System.out.println(line);\n"
        "    }\n"
        "}\n"
    ),
    Language.CPP: (
        "#include <iostream>\n"
        "#include <string>\n"
        "using namespace std;\n"
        "\n"
        "int main() {\n"
        "    string line;\n"
        "    while (getline(cin, line)) cout << line << '\\n';\n"
        "    return 0;\n"
        "}\n"
    ),
}


def language_metadata(runtime: LanguageView) -> LanguageView:
    return runtime.model_copy(
        update={
            "display_name": NAMES[runtime.language],
            "capabilities": [
                "playground",
                "question_samples",
                "question_custom_inputs",
                "graded_submissions",
            ],
            "playground_starter_code": STARTERS[runtime.language],
        }
    )
