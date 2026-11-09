"""Explicit adapters for fixture-only fields and identity-sensitive pointer problems."""

from typing import Any

from app.judging import node_runtimes
from app.judging.contracts import JudgeProfile
from app.models import Language


def prepare(
    profile: JudgeProfile, language: Language, values: list[Any]
) -> tuple[str, list[str], str | None, str | None]:
    kind = profile.adapter
    if kind in {"normal", "unsigned"}:
        return "", [], None, None
    method = (profile.native_signature or profile.signature).name
    if language == Language.PYTHON:
        call = f"Solution().{method}"
    elif language == Language.CPP:
        call = f"Solution().{method}"
    else:
        call = f"new Solution().{method}"
    if kind == "relink":
        names = [f"_lc_arg{i}" for i in range(len(profile.signature.parameters))]
        target = "_lc_arg0" if profile.result == "mutated_first" else "_lc_result"
        if language == Language.PYTHON:
            prelude = (
                "def _lc_relinked(root,original):\n    for node,value in "
                "original.items():\n        if node.val!=value: raise ValueError('node "
                "values changed')\n    seen=set()\n    node=root\n    while node is not "
                "None:\n        if node not in original or node in seen: raise "
                "ValueError('invalid nodes')\n        seen.add(node);node=node.next\n    "
                "return _lc_encode(root) if root is not None else []\n"
            )
            lines = [
                "_lc_original={}\n_lc_ptr=_lc_arg0",
                (
                    "while _lc_ptr is not None:\n    _lc_original[_lc_ptr]=_lc_ptr.val\n "
                    "   _lc_ptr=_lc_ptr.next"
                ),
            ]
            output = f"json.dumps(_lc_relinked({target},_lc_original),separators=(',',':'))"
        elif language == Language.CPP:
            prelude = (
                "string lcRelinked(ListNode*root,unordered_map<ListNode*,int>original){"
                "for(auto entry:original)if(entry.first->val!=entry.second)throw "
                'runtime_error("node values changed");unordered_set<ListNode*>seen;for('
                "auto*n=root;n;n=n->next)if(!original.count(n)||!seen.insert(n).second)"
                'throw runtime_error("invalid nodes");return lcJson(root);}\n'
            )
            lines = [
                (
                    "unordered_map<ListNode*,int> _lc_original;for(auto*n=_lc_arg0;n;n="
                    "n->next)_lc_original[n]=n->val;"
                )
            ]
            output = f"lcRelinked({target},_lc_original)"
        else:
            prelude = (
                "class RelinkFixture { static String output(ListNode "
                "root,IdentityHashMap<ListNode,Integer>original){for(Map.Entry<ListNode"
                ",Integer>e:original.entrySet())if(e.getKey().val!=e.getValue())throw "
                'new IllegalArgumentException("node values '
                'changed");Set<ListNode>seen=Collections.newSetFromMap(new '
                "IdentityHashMap<>());for(ListNode n=root;n!=null;n=n.next)if(!original"
                ".containsKey(n)||!seen.add(n))throw new "
                'IllegalArgumentException("invalid nodes");return '
                'root==null?"[]":Main.lcJson(root);}}\n'
            )
            lines = [
                (
                    "IdentityHashMap<ListNode,Integer> _lc_original=new "
                    "IdentityHashMap<>();for(ListNode n=_lc_arg0;n!=null;n=n.next)_lc_o"
                    "riginal.put(n,n.val);"
                )
            ]
            output = f"RelinkFixture.output({target},_lc_original)"
        return prelude, lines, call + "(" + ",".join(names) + ")", output
    if kind in {"graph", "random_list", "next_tree"}:
        if language == Language.PYTHON:
            prefix = f"_lc_node_kind={kind!r}\n" + node_runtimes.PYTHON
            if kind == "next_tree":
                lines = ["_lc_root=_lc_node_tree(_lc_arg0)"]
                return (
                    prefix,
                    lines,
                    call + "(_lc_root)",
                    "json.dumps(_lc_next_output(_lc_result,_lc_root),separators=(',',':'))",
                )
            builder = "_lc_graph(_lc_arg0)" if kind == "graph" else "_lc_random(_lc_arg0,_lc_arg1)"
            lines = [
                "_lc_original=" + builder,
                "_lc_root=_lc_original[0] if _lc_original else None",
            ]
            output = "_lc_graph_output" if kind == "graph" else "_lc_random_output"
            return (
                prefix,
                lines,
                call + "(_lc_root)",
                f"json.dumps({output}(_lc_result,_lc_original),separators=(',',':'))",
            )
        if language == Language.CPP:
            if kind == "next_tree":
                return (
                    node_runtimes.CPP,
                    ["Node*_lc_root=lcNodeTree(_lc_arg0);"],
                    call + "(_lc_root)",
                    "lcNextOutput(_lc_result,_lc_root)",
                )
            builder = "lcGraph(_lc_arg0)" if kind == "graph" else "lcRandom(_lc_arg0,_lc_arg1)"
            output = "lcGraphOutput" if kind == "graph" else "lcRandomOutput"
            return (
                node_runtimes.CPP,
                [
                    "auto _lc_original=" + builder + ";",
                    "Node* _lc_root=_lc_original.empty()?nullptr:_lc_original[0];",
                ],
                call + "(_lc_root)",
                f"{output}(_lc_result,_lc_original)",
            )
        if kind == "next_tree":
            return (
                node_runtimes.JAVA,
                ["Node _lc_root=NodeFixtures.tree(_lc_arg0);"],
                call + "(_lc_root)",
                "lcJson(NodeFixtures.nextOutput(_lc_result,_lc_root))",
            )
        builder = (
            "NodeFixtures.graph(_lc_arg0)"
            if kind == "graph"
            else "NodeFixtures.random(_lc_arg0,_lc_arg1)"
        )
        output = "graphOutput" if kind == "graph" else "randomOutput"
        return (
            node_runtimes.JAVA,
            [
                "ArrayList<Node> _lc_original=" + builder + ";",
                "Node _lc_root=_lc_original.isEmpty()?null:_lc_original.get(0);",
            ],
            call + "(_lc_root)",
            f"lcJson(NodeFixtures.{output}(_lc_result,_lc_original))",
        )
    if kind == "bad_version":
        if language == Language.PYTHON:
            prefix = "def isBadVersion(version): return version >= _lc_bad\n"
            setup = ["_lc_bad=_lc_arg1"]
        elif language == Language.CPP:
            prefix = "int _lc_bad; bool isBadVersion(int version){return version>=_lc_bad;}\n"
            setup = ["_lc_bad=_lc_arg1;"]
        else:
            prefix = (
                "class VersionControl {static int bad; protected boolean "
                "isBadVersion(int version){return version>=bad;}}\n"
            )
            setup = ["VersionControl.bad=_lc_arg1;"]
        return prefix, setup, call + "(_lc_arg0)", None
    if kind == "codec":
        if language == Language.PYTHON:
            lines = ["_lc_encoder=Codec()", "_lc_decoder=Codec()"]
        elif language == Language.CPP:
            lines = ["Codec _lc_encoder, _lc_decoder;"]
        else:
            lines = ["Codec _lc_encoder=new Codec(), _lc_decoder=new Codec();"]
        return "", lines, "_lc_decoder.deserialize(_lc_encoder.serialize(_lc_arg0))", None
    if kind == "lca":
        if language == Language.PYTHON:
            lines = [
                "_lc_nodes=[_lc_arg0]",
                (
                    "for _lc_node in _lc_nodes:\n    _lc_nodes.extend(n for n in "
                    "(_lc_node.left,_lc_node.right) if n is not None)"
                ),
                "_lc_p=next(n for n in _lc_nodes if n.val==_lc_arg1)",
                "_lc_q=next(n for n in _lc_nodes if n.val==_lc_arg2)",
            ]
            output = (
                "json.dumps(_lc_result.val if any(n is _lc_result for n in _lc_nodes) else None)"
            )
        elif language == Language.CPP:
            lines = [
                "vector<TreeNode*> _lc_nodes{_lc_arg0}; TreeNode *_lc_p=nullptr,*_lc_q=nullptr;",
                (
                    "for(size_t i=0;i<_lc_nodes.size();++i){auto*n=_lc_nodes[i];if(n->v"
                    "al==_lc_arg1)_lc_p=n;if(n->val==_lc_arg2)_lc_q=n;if(n->left)_lc_no"
                    "des.push_back(n->left);if(n->right)_lc_nodes.push_back(n->right);}"
                ),
            ]
            output = (
                "(find(_lc_nodes.begin(),_lc_nodes.end(),_lc_result)==_lc_nodes.end()?s"
                'tring("null"):lcJson(_lc_result->val))'
            )
        else:
            lines = [
                (
                    "ArrayList<TreeNode> _lc_nodes=new "
                    "ArrayList<>();_lc_nodes.add(_lc_arg0);TreeNode "
                    "_lc_p=null,_lc_q=null;"
                ),
                (
                    "for(int i=0;i<_lc_nodes.size();i++){TreeNode "
                    "n=_lc_nodes.get(i);if(n.val==_lc_arg1)_lc_p=n;if(n.val==_lc_arg2)_"
                    "lc_q=n;if(n.left!=null)_lc_nodes.add(n.left);if(n.right!=null)_lc_"
                    "nodes.add(n.right);}"
                ),
            ]
            output = '(_lc_nodes.contains(_lc_result)?lcJson(_lc_result.val):"null")'
        return "", lines, call + "(_lc_arg0,_lc_p,_lc_q)", output
    root = "_lc_arg1" if kind == "intersection" else "_lc_arg0"
    if language == Language.PYTHON:
        lines = [
            f"_lc_nodes=[]\n_lc_ptr={root}",
            "while _lc_ptr is not None:\n    _lc_nodes.append(_lc_ptr)\n    _lc_ptr=_lc_ptr.next",
        ]
        index_output = (
            "json.dumps(next((i for i,n in enumerate(_lc_nodes) if n is _lc_result),-1 "
            "if _lc_result is None else -2))"
        )
        if kind == "cycle":
            lines.append("if _lc_arg1>=0: _lc_nodes[-1].next=_lc_nodes[_lc_arg1]")
            return (
                "",
                lines,
                call + "(_lc_arg0)",
                index_output if profile.signature.name == "detectCycle" else None,
            )
        if kind == "delete_node":
            lines.append("_lc_node=next(n for n in _lc_nodes if n.val==_lc_arg1)")
            return "", lines, call + "(_lc_node)", None
        lines.append(
            "if _lc_arg0!=0:\n    if _lc_arg4==0: _lc_arg2=_lc_nodes[_lc_arg3]\n    "
            "else:\n        _lc_ptr=_lc_arg2\n        for _lc_i in "
            "range(_lc_arg4-1): _lc_ptr=_lc_ptr.next\n        "
            "_lc_ptr.next=_lc_nodes[_lc_arg3]"
        )
        return "", lines, call + "(_lc_arg1,_lc_arg2)", index_output
    if language == Language.CPP:
        lines = [
            f"vector<ListNode*> _lc_nodes;for(auto*p={root};p;p=p->next)_lc_nodes.push_back(p);"
        ]
        index_output = (
            "lcJson(_lc_result==nullptr?-1:(find(_lc_nodes.begin(),_lc_nodes.end(),_lc_"
            "result)==_lc_nodes.end()?-2:(int)(find(_lc_nodes.begin(),_lc_nodes.end(),_"
            "lc_result)-_lc_nodes.begin())))"
        )
        if kind == "cycle":
            lines.append("if(_lc_arg1>=0)_lc_nodes.back()->next=_lc_nodes[_lc_arg1];")
            return (
                "",
                lines,
                call + "(_lc_arg0)",
                index_output if profile.signature.name == "detectCycle" else None,
            )
        if kind == "delete_node":
            lines.append(
                "ListNode* _lc_node=nullptr;for(auto*n:_lc_nodes)if(n->val==_lc_arg1)_lc_node=n;"
            )
            return "", lines, call + "(_lc_node)", None
        lines.append(
            "if(_lc_arg0!=0){if(_lc_arg4==0)_lc_arg2=_lc_nodes[_lc_arg3];else{auto*"
            "p=_lc_arg2;for(int i=0;i<_lc_arg4-1;i++)p=p->next;p->next=_lc_nodes[_l"
            "c_arg3];}}"
        )
        return "", lines, call + "(_lc_arg1,_lc_arg2)", index_output
    lines = [
        "ArrayList<ListNode> _lc_nodes=new ArrayList<>();"
        f"for(ListNode n={root};n!=null;n=n.next)_lc_nodes.add(n);"
    ]
    index_output = (
        "lcJson(_lc_result==null?-1:(_lc_nodes.contains(_lc_result)?_lc_nodes.indexOf(_"
        "lc_result):-2))"
    )
    if kind == "cycle":
        lines.append(
            "if(_lc_arg1>=0)_lc_nodes.get(_lc_nodes.size()-1).next=_lc_nodes.get(_lc_arg1);"
        )
        return (
            "",
            lines,
            call + "(_lc_arg0)",
            index_output if profile.signature.name == "detectCycle" else None,
        )
    if kind == "delete_node":
        lines.append(
            "ListNode _lc_node=null;for(ListNode n:_lc_nodes)if(n.val==_lc_arg1)_lc_node=n;"
        )
        return "", lines, call + "(_lc_node)", None
    lines.append(
        "if(_lc_arg0!=0){if(_lc_arg4==0)_lc_arg2=_lc_nodes.get(_lc_arg3);else{ListN"
        "ode n=_lc_arg2;for(int i=0;i<_lc_arg4-1;i++)n=n.next;n.next=_lc_nodes.get("
        "_lc_arg3);}}"
    )
    return "", lines, call + "(_lc_arg1,_lc_arg2)", index_output
