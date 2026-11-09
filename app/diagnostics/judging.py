"""Explicit live judging flow: python -m app.diagnostics.judging.

Uses the retained local test account. Makes real Judge0 executions through the API.
Passwords, access/refresh tokens, provider tokens and hidden case data are never reported.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

from app.ingestion.catalog import question_id

PYTHON_TWO_SUM = """class Solution:
    def twoSum(self,nums,target):
        seen={}
        for i,value in enumerate(nums):
            if target-value in seen:return [i,seen[target-value]]
            seen[value]=i
"""
JAVA_TWO_SUM = """class Solution {
    public int[] twoSum(int[] nums,int target){
        Map<Long,Integer> seen=new HashMap<>();
        for(int i=0;i<nums.length;i++){
            long wanted=(long)target-nums[i];
            if(seen.containsKey(wanted))return new int[]{i,seen.get(wanted)};
            seen.put((long)nums[i],i);
        }return new int[0];
    }
}"""
CPP_TWO_SUM = """class Solution {public:
    vector<int> twoSum(vector<int>& nums,int target){
        unordered_map<long long,int> seen;
        for(int i=0;i<(int)nums.size();i++){
            long long wanted=(long long)target-nums[i];
            if(seen.count(wanted))return {i,seen[wanted]};
            seen[nums[i]]=i;
        }return {};
    }
};"""

CASES: list[dict[str, Any]] = [
    {
        "case": "wrong_answer",
        "question": 1,
        "language": "python",
        "expected": "wrong_answer",
        "source": "class Solution:\n    def twoSum(self,nums,target): return [0,0]\n",
    },
    {
        "case": "compilation_error",
        "question": 1,
        "language": "java",
        "expected": "compilation_error",
        "source": "class Solution { public int[] twoSum(int[] nums,int target){ return; } }",
    },
    {
        "case": "runtime_error",
        "question": 1,
        "language": "python",
        "expected": "runtime_error",
        ("source"): (
            "class Solution:\n    def twoSum(self,nums,target): raise RuntimeError('inte"
            "ntional verification failure')\n"
        ),
    },
    {
        "case": "time_limit",
        "question": 1,
        "language": "python",
        "expected": "time_limit_exceeded",
        "source": "class Solution:\n    def twoSum(self,nums,target):\n        while True: pass\n",
    },
    {
        "case": "python_correct",
        "question": 1,
        "language": "python",
        "expected": "accepted",
        "source": PYTHON_TWO_SUM,
    },
    {
        "case": "java_correct",
        "question": 1,
        "language": "java",
        "expected": "accepted",
        "source": JAVA_TWO_SUM,
    },
    {
        "case": "cpp_correct",
        "question": 1,
        "language": "cpp",
        "expected": "accepted",
        "source": CPP_TWO_SUM,
    },
    {
        "case": "java_in_place",
        "question": 27,
        "language": "java",
        "expected": "accepted",
        ("source"): (
            "class Solution {public int removeElement(int[] nums,int val){int k=0;for(i"
            "nt x:nums)if(x!=val)nums[k++]=x;return k;}}"
        ),
    },
    {
        "case": "cpp_linked_list",
        "question": 206,
        "language": "cpp",
        "expected": "accepted",
        ("source"): (
            "class Solution {public: ListNode* reverseList(ListNode* head){ListNode* pr"
            "evious=nullptr;while(head){auto*next=head->next;head->next=previous;previo"
            "us=head;head=next;}return previous;}};"
        ),
    },
    {
        "case": "python_tree",
        "question": 226,
        "language": "python",
        "expected": "accepted",
        ("source"): (
            "class Solution:\n    def invertTree(self,root):\n        if root:\n          "
            "  root.left,root.right=self.invertTree(root.right),self.invertTree(root.le"
            "ft)\n        return root\n"
        ),
    },
    {
        "case": "cpp_graph_clone",
        "question": 133,
        "language": "cpp",
        "expected": "accepted",
        ("source"): (
            "class Solution {public: Node* cloneGraph(Node* node){if(!node)return nullp"
            "tr;unordered_map<Node*,Node*> copies;queue<Node*>q;q.push(node);copies[nod"
            "e]=new Node(node->val);while(!q.empty()){auto*n=q.front();q.pop();for(auto"
            "*m:n->neighbors){if(!copies.count(m)){copies[m]=new Node(m->val);q.push(m)"
            ";}copies[n]->neighbors.push_back(copies[m]);}}return copies[node];}};"
        ),
    },
    {
        "case": "java_stateful_median",
        "question": 295,
        "language": "java",
        "expected": "accepted",
        ("source"): (
            "class MedianFinder {PriorityQueue<Integer>low=new PriorityQueue<>(Comparat"
            "or.reverseOrder()),high=new PriorityQueue<>();public MedianFinder(){}publi"
            "c void addNum(int n){if(low.isEmpty()||n<=low.peek())low.add(n);else high."
            "add(n);if(low.size()>high.size()+1)high.add(low.poll());if(high.size()>low"
            ".size())low.add(high.poll());}public double findMedian(){return low.size()"
            ">high.size()?low.peek():((double)low.peek()+high.peek())/2;}}"
        ),
    },
    {
        "case": "python_large_output",
        "question": 238,
        "language": "python",
        "expected": "accepted",
        "source": """class Solution:
    def productExceptSelf(self,nums):
        output=[1]*len(nums);product=1
        for i,x in enumerate(nums):output[i]=product;product*=x
        product=1
        for i in range(len(nums)-1,-1,-1):output[i]*=product;product*=nums[i]
        return output
""",
    },
    {
        "case": "lustcode_unicode_codec",
        "question": 271,
        "language": "python",
        "expected": "accepted",
        "source": """class Solution:
    def transformStrings(self,mode,strings):
        if mode==0:return [''.join(str(len(s.encode()))+'#'+s for s in strings)]
        data=strings[0].encode();result=[];cursor=0
        while cursor<len(data):
            separator=data.index(b'#',cursor);size=int(data[cursor:separator]);cursor=separator+1
            result.append(data[cursor:cursor+size].decode());cursor+=size
        return result
""",
    },
    {
        "case": "java_api_hook",
        "question": 278,
        "language": "java",
        "expected": "accepted",
        ("source"): (
            "class Solution extends VersionControl {public int firstBadVersion(int n){i"
            "nt lo=1,hi=n;while(lo<hi){int mid=lo+(hi-lo)/2;if(isBadVersion(mid))hi=mid"
            ";else lo=mid+1;}return lo;}}"
        ),
    },
    {
        "case": "cpp_tree_codec",
        "question": 297,
        "language": "cpp",
        "expected": "accepted",
        ("source"): (
            'class Codec {public:string serialize(TreeNode* root){if(!root)return "#,";'
            'return to_string(root->val)+","+serialize(root->left)+serialize(root->righ'
            "t);}TreeNode* read(istringstream&in){string value;getline(in,value,',');if"
            '(value=="#")return nullptr;auto*node=new TreeNode(stoi(value));node->left='
            "read(in);node->right=read(in);return node;}TreeNode* deserialize(string da"
            "ta){istringstream in(data);return read(in);}};"
        ),
    },
]


CASES.append(
    {
        "case": "cpp_graph_alias_rejected",
        "question": 133,
        "language": "cpp",
        "expected": "wrong_answer",
        "source": "class Solution {public: Node* cloneGraph(Node* node){return node;}};",
    }
)


CASES.extend(
    [
        {
            "case": "python_debug_output",
            "question": 1,
            "language": "python",
            "expected": "accepted",
            "source": PYTHON_TWO_SUM.replace("seen={}", "print('debug')\n        seen={}"),
        },
        {
            "case": "java_debug_output",
            "question": 1,
            "language": "java",
            "expected": "accepted",
            "source": JAVA_TWO_SUM.replace(
                "Map<Long,Integer> seen", 'System.out.println("debug"); Map<Long,Integer> seen'
            ),
        },
        {
            "case": "cpp_debug_output",
            "question": 1,
            "language": "cpp",
            "expected": "accepted",
            "source": CPP_TWO_SUM.replace(
                "unordered_map<long long,int> seen;",
                'printf("debug printf\\n");cout<<"debug cout"<<endl;'
                "unordered_map<long long,int> seen;",
            ),
        },
    ]
)


async def verify(
    account_file: Path,
    output: Path,
    budget_seconds: float = 900,
    case_names: list[str] | None = None,
) -> bool:
    selected = [case for case in CASES if case_names is None or case["case"] in case_names]
    credentials = dotenv_values(account_file)
    base = credentials.get("TEST_API_BASE_URL") or "http://127.0.0.1:8000"
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "base_url": base,
        "status": "running",
        "checks": {},
        "submissions": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        output.write_text(json.dumps(report, indent=2) + "\n")

    refresh = None
    async with httpx.AsyncClient(base_url=base + "/api/v1", timeout=30, trust_env=False) as api:

        async def request(method: str, path: str, status: int = 200, **kwargs: Any) -> Any:
            nonlocal refresh
            response = await api.request(method, path, **kwargs)
            if response.status_code == 401 and status != 401 and refresh and kwargs.get("headers"):
                rotated = await api.post("/auth/refresh", json={"refresh_token": refresh})
                if rotated.status_code == 200:
                    tokens = rotated.json()["data"]
                    refresh = tokens["refresh_token"]
                    kwargs["headers"]["Authorization"] = "Bearer " + tokens["access_token"]
                    response = await api.request(method, path, **kwargs)
            if response.status_code != status:
                raise RuntimeError(
                    f"{method} {path}: HTTP {response.status_code}; expected {status}"
                )
            return response.json() if response.content else None

        try:
            await request("GET", "/health/live")
            await request("GET", "/health/ready")
            report["checks"]["health"] = "passed"
            tokens = (
                await request(
                    "POST",
                    "/auth/login",
                    json={
                        "email": credentials.get("TEST_ACCOUNT_EMAIL"),
                        "password": credentials.get("TEST_ACCOUNT_PASSWORD"),
                    },
                )
            )["data"]
            refresh = tokens["refresh_token"]
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            me = (await request("GET", "/users/me", headers=headers))["data"]
            report["account"] = {"id": me["id"], "username": me["username"]}
            questions = []
            for page in range(1, 4):
                response = await request(
                    "GET", "/questions", params={"page": page, "page_size": 100}
                )
                assert response["total"] == 300
                questions.extend(response["data"])
            assert sum(q["is_judgeable"] for q in questions) == 283
            assert sum(q["judging_status"] == "unsupported" for q in questions) == 17
            assert all(
                not q["is_judgeable"] or set(q["judgeable_languages"]) == {"python", "java", "cpp"}
                for q in questions
            )
            report["checks"]["catalog"] = {
                "ready": 283,
                "unsupported": 17,
                "languages": ["python", "java", "cpp"],
            }
            for number in [1, 133, 142, 146, 160, 235, 237, 271, 278, 284, 295, 297]:
                detail = (await request("GET", f"/questions/{question_id(number)}"))["data"]
                assert (
                    detail["is_judgeable"]
                    and detail["evaluation_contract"]
                    and set(detail["starter_code"]) == {"python", "java", "cpp"}
                )
                assert "ingestion" not in detail and "suite_sha256" not in str(detail)
            report["checks"]["public_contracts_and_privacy"] = "passed"
            disabled = next(q for q in questions if q["judging_status"] == "unsupported")
            refused = await request(
                "POST",
                "/submissions",
                status=409,
                headers=headers,
                json={
                    "question_id": disabled["id"],
                    "language": "python",
                    "source_code": "print(1)",
                },
            )
            assert refused["error"]["code"] == "question_unavailable"
            report["checks"]["sql_shell_closed"] = "passed"
            initial_stats = (await request("GET", "/users/me/statistics", headers=headers))["data"]
            progress = await request(
                "GET", "/users/me/progress", headers=headers, params={"page_size": 100}
            )
            solved = {row["question_id"] for row in progress["data"] if row["solved_at"]}
            start = time.monotonic()

            async def phase(cases: list[dict[str, Any]]) -> None:
                todo = list(cases)
                active: list[dict[str, Any]] = []
                while todo or active:
                    while todo and len(active) < 4:
                        item = todo.pop(0)
                        submission = (
                            await request(
                                "POST",
                                "/submissions",
                                status=202,
                                headers=headers,
                                json={
                                    "question_id": str(question_id(item["question"])),
                                    "language": item["language"],
                                    "source_code": item["source"],
                                },
                            )
                        )["data"]
                        entry = {
                            "case": item["case"],
                            "id": submission["id"],
                            "question": item["question"],
                            "language": item["language"],
                            "version": submission["language_version"],
                            "expected": item["expected"],
                            "status": submission["status"],
                            "tests": submission["total_tests"],
                        }
                        report["submissions"].append(entry)
                        active.append(entry)
                        save()
                    for entry in list(active):
                        detail = (
                            await request("GET", "/submissions/" + entry["id"], headers=headers)
                        )["data"]
                        entry["status"] = detail["status"]
                        entry["passed_tests"] = detail["passed_tests"]
                        if detail["status"] in {"queued", "running"}:
                            continue
                        entry["passed"] = detail["status"] == entry["expected"]
                        assert all(
                            row["stdout"] is None
                            and row["stderr"] is None
                            and row["compile_output"] is None
                            for row in detail["results"]
                            if row["hidden"]
                        )
                        assert "evaluation" not in detail and "provider_token" not in str(detail)
                        if entry["expected"] == "accepted":
                            entry["passed"] &= detail["passed_tests"] == detail["total_tests"]
                        active.remove(entry)
                        save()
                        print(
                            json.dumps(
                                {
                                    "case": entry["case"],
                                    "status": entry["status"],
                                    "passed": entry["passed"],
                                }
                            ),
                            flush=True,
                        )
                        if not entry["passed"]:
                            raise RuntimeError("Unexpected verdict for " + entry["case"])
                    if time.monotonic() - start > budget_seconds:
                        raise RuntimeError("Live judging verification deadline reached")
                    if active:
                        await asyncio.sleep(8)

            failures = [case for case in selected if case["expected"] != "accepted"]
            await phase(failures)
            assert (await request("GET", "/users/me/statistics", headers=headers))["data"][
                "solved_questions"
            ] == initial_stats["solved_questions"]
            report["checks"]["incorrect_solutions_award_no_solved_credit"] = (
                "passed" if failures else "not_run"
            )
            accepted_cases = [case for case in selected if case["expected"] == "accepted"]
            await phase(accepted_cases)
            statistics = (await request("GET", "/users/me/statistics", headers=headers))["data"]
            newly_solved = {str(question_id(c["question"])) for c in accepted_cases} - solved
            assert statistics["solved_questions"] == initial_stats["solved_questions"] + len(
                newly_solved
            )
            report["checks"]["solve_once_across_languages"] = "passed"
            report["checks"]["private_results_redacted"] = "passed"
            report["checks"]["history"] = (await request("GET", "/submissions", headers=headers))[
                "total"
            ]
            report["elapsed_seconds"] = round(time.monotonic() - start, 2)
            report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["error_type"] = type(exc).__name__
            report["error"] = (
                str(exc)
                if isinstance(exc, RuntimeError)
                else "Live verification assertion failed; inspect recorded check and verdict."
            )
        finally:
            if refresh:
                await api.post("/auth/logout", json={"refresh_token": refresh})
            report["finished_at"] = datetime.now(UTC).isoformat()
            save()
    print(json.dumps({"status": report["status"], "report": str(output)}), flush=True)
    return report["status"] == "passed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-file", type=Path, default=Path(".env.test-account"))
    parser.add_argument("--output", type=Path, default=Path("audit/judging_live.json"))
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--cases", nargs="+", choices=[case["case"] for case in CASES])
    args = parser.parse_args()
    raise SystemExit(
        0 if asyncio.run(verify(args.account_file, args.output, args.timeout, args.cases)) else 1
    )


if __name__ == "__main__":
    main()
