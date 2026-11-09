# ruff: noqa: E501
"""Bounded typed stdin transport. Test data is never compiled into submitted source."""

import hashlib
import json
from typing import Any

from app.models import Language

INVALID_RESULT = '{"_lustcode_invalid_result":true}'


def render_output(expression: str, language: Language) -> str:
    if language == Language.PYTHON:
        return (
            f"try:\n    _lc_rendered={expression}\n"
            "except (ValueError,TypeError,AttributeError,KeyError,IndexError,RecursionError):\n"
            f"    _lc_rendered={INVALID_RESULT!r}\n"
            "_lc_result_output.write(_lc_rendered+'\\n')\n_lc_result_output.flush()\n"
        )
    marker = json.dumps(INVALID_RESULT)
    if language == Language.CPP:
        return (
            f"string _lc_rendered;try{{_lc_rendered={expression};}}catch(const runtime_error&){{_lc_rendered={marker};}}catch(const logic_error&){{_lc_rendered={marker};}}\n"
            "cout.flush();fflush(stdout);dup2(_lc_output_guard.fd,STDOUT_FILENO);"
            "cout<<_lc_rendered<<endl;cout.flush();fflush(stdout);"
            "dup2(STDERR_FILENO,STDOUT_FILENO);close(_lc_output_guard.fd);\n"
        )
    return f"try{{_lc_result_output.println({expression});}}catch(IllegalArgumentException|ClassCastException|NullPointerException|IndexOutOfBoundsException e){{_lc_result_output.println({marker});}}\n"


def pack_stdin(stdin: str, language: Language) -> str:
    if language == Language.PYTHON:
        return stdin

    def encode(value: Any) -> str:
        if value is None:
            return "Z\n"
        if type(value) is bool:
            return "B " + str(int(value)) + "\n"
        if isinstance(value, str):
            return "S " + value.encode().hex() + "\n"
        if isinstance(value, list):
            return "A " + str(len(value)) + "\n" + "".join(encode(v) for v in value)
        return "N " + json.dumps(value, allow_nan=False) + "\n"

    return encode(json.loads(stdin))


PYTHON = r"""
def _lc_from(value,kind):
    if kind=='ListNode':return _lc_list(value)
    if kind=='TreeNode':return _lc_tree(value)
    if kind.endswith('[]'):return [_lc_from(v,kind[:-2]) for v in value]
    if kind.startswith('list<'):return [_lc_from(v,kind[5:-1]) for v in value]
    return value
def _lc_typed(value,kind):
    if kind in ('ListNode','TreeNode'):return [] if value is None else _lc_encode(value)
    if kind.endswith('[]'):return [_lc_typed(v,kind[:-2]) for v in value]
    if kind.startswith('list<'):return [_lc_typed(v,kind[5:-1]) for v in value]
    return _lc_encode(value)
"""

CPP = r"""
struct LCOutputGuard {int fd;LCOutputGuard(){cout.flush();fflush(stdout);fd=dup(STDOUT_FILENO);if(fd<0||dup2(STDERR_FILENO,STDOUT_FILENO)<0)throw runtime_error("output initialization failed");}};
LCOutputGuard _lc_output_guard;
string lcWireLine(){string line;if(!getline(cin,line))throw runtime_error("missing input");return line;}
template<class T>struct LCRead;
template<>struct LCRead<int>{static int get(){return stoi(lcWireLine().substr(2));}};
template<>struct LCRead<double>{static double get(){return stod(lcWireLine().substr(2));}};
template<>struct LCRead<bool>{static bool get(){return lcWireLine()=="B 1";}};
template<>struct LCRead<string>{static string get(){string hex=lcWireLine().substr(2),out;for(size_t i=0;i<hex.size();i+=2)out.push_back((char)stoi(hex.substr(i,2),nullptr,16));return out;}};
template<>struct LCRead<char>{static char get(){return LCRead<string>::get().at(0);}};
template<>struct LCRead<optional<int>>{static optional<int> get(){string line=lcWireLine();return line=="Z"?nullopt:optional<int>(stoi(line.substr(2)));}};
template<class T>struct LCRead<vector<T>>{static vector<T> get(){int size=stoi(lcWireLine().substr(2));vector<T>out;out.reserve(size);for(int i=0;i<size;i++)out.push_back(LCRead<T>::get());return out;}};
template<>struct LCRead<ListNode*>{static ListNode* get(){return lcList(LCRead<vector<int>>::get());}};
template<>struct LCRead<TreeNode*>{static TreeNode* get(){return lcTree(LCRead<vector<optional<int>>>::get());}};
"""

JAVA = r"""
class LCWire {
    static BufferedReader input=new BufferedReader(new InputStreamReader(System.in,java.nio.charset.StandardCharsets.US_ASCII));
    static Object read()throws Exception {
        String line=input.readLine();if(line==null)throw new EOFException();
        switch(line.charAt(0)) {
            case 'Z':return null;
            case 'B':return line.equals("B 1");
            case 'N':String n=line.substring(2);if(n.contains(".")||n.contains("e")||n.contains("E"))return Double.valueOf(n);return Long.valueOf(n);
            case 'S':String s=line.substring(2);byte[]bytes=new byte[s.length()/2];for(int i=0;i<bytes.length;i++)bytes[i]=(byte)Integer.parseInt(s.substring(i*2,i*2+2),16);return new String(bytes,java.nio.charset.StandardCharsets.UTF_8);
            case 'A':int count=Integer.parseInt(line.substring(2));List<Object>out=new ArrayList<>();for(int i=0;i<count;i++)out.add(read());return out;
            default:throw new IllegalArgumentException("invalid wire input");
        }
    }
"""


def java_name(kind: str) -> str:
    return "lcConvert" + hashlib.sha256(kind.encode()).hexdigest()[:12]


def java_converters(kinds: list[str]) -> str:
    from app.judging.contracts import element_type
    from app.judging.drivers import type_name

    done = set()
    methods = []

    def visit(kind: str) -> None:
        if kind in done:
            return
        done.add(kind)
        inner = element_type(kind)
        name = java_name(kind)
        result = type_name(kind, Language.JAVA)
        if inner:
            visit(inner)
            if kind.endswith("[]"):
                allocation = "new " + result.replace("[]", "[items.size()]", 1)
                body = f"List<?>items=(List<?>)value;{result}out={allocation};for(int i=0;i<items.size();i++)out[i]={java_name(inner)}(items.get(i));return out;"
            else:
                body = f"{result}out=new ArrayList<>();for(Object item:(List<?>)value)out.add({java_name(inner)}(item));return out;"
        elif kind == "ListNode":
            visit("integer[]")
            body = f"return lcList({java_name('integer[]')}(value));"
        elif kind == "TreeNode":
            body = "List<?>items=(List<?>)value;Integer[]out=new Integer[items.size()];for(int i=0;i<items.size();i++)out[i]=items.get(i)==null?null:((Number)items.get(i)).intValue();return lcTree(out);"
        else:
            conversion = {
                "integer": "((Number)value).intValue()",
                "double": "((Number)value).doubleValue()",
                "boolean": "(Boolean)value",
                "string": "(String)value",
                "character": "((String)value).charAt(0)",
            }[kind]
            body = "return " + conversion + ";"
        methods.append(f"static {result} {name}(Object value){{{body}}}\n")

    for kind in kinds:
        visit("list<integer>" if kind == "Iterator" else kind)
    return "".join(methods)
