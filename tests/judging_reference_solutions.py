# ruff: noqa: E501
"""Trusted fixture programs for driver tests, never sourced from user submissions."""

from app.judging.contracts import JudgeProfile

DESIGNS = {
    146: """class LRUCache:
    def __init__(self,capacity):self.capacity=capacity;self.values=collections.OrderedDict()
    def get(self,key):
        if key not in self.values:return -1
        self.values.move_to_end(key);return self.values[key]
    def put(self,key,value):
        self.values[key]=value;self.values.move_to_end(key)
        if len(self.values)>self.capacity:self.values.popitem(last=False)
""",
    155: """class MinStack:
    def __init__(self):self.values=[]
    def push(self,val):self.values.append(val)
    def pop(self):self.values.pop()
    def top(self):return self.values[-1]
    def getMin(self):return min(self.values)
""",
    173: """class BSTIterator:
    def __init__(self,root):
        self.values=[];self.index=0
        def visit(node):
            if node:visit(node.left);self.values.append(node.val);visit(node.right)
        visit(root)
    def hasNext(self):return self.index<len(self.values)
    def next(self):value=self.values[self.index];self.index+=1;return value
""",
    208: """class Trie:
    def __init__(self):self.words=set()
    def insert(self,word):self.words.add(word)
    def search(self,word):return word in self.words
    def startsWith(self,prefix):return any(s.startswith(prefix) for s in self.words)
""",
    211: """class WordDictionary:
    def __init__(self):self.words=set()
    def addWord(self,word):self.words.add(word)
    def search(self,word):return any(re.fullmatch(word,w) for w in self.words)
""",
    225: """class MyStack:
    def __init__(self):self.values=[]
    def push(self,x):self.values.append(x)
    def pop(self):return self.values.pop()
    def top(self):return self.values[-1]
    def empty(self):return not self.values
""",
    232: """class MyQueue:
    def __init__(self):self.values=collections.deque()
    def push(self,x):self.values.append(x)
    def pop(self):return self.values.popleft()
    def peek(self):return self.values[0]
    def empty(self):return not self.values
""",
    284: """class PeekingIterator:
    def __init__(self,iterator):self.iterator=iterator;self.cached=None;self.filled=False
    def peek(self):
        if not self.filled:self.cached=self.iterator.next();self.filled=True
        return self.cached
    def next(self):
        if not self.filled:return self.iterator.next()
        self.filled=False;return self.cached
    def hasNext(self):return self.filled or self.iterator.hasNext()
""",
    295: """class MedianFinder:
    def __init__(self):self.values=[]
    def addNum(self,num):bisect.insort(self.values,num)
    def findMedian(self):n=len(self.values);return (self.values[(n-1)//2]+self.values[n//2])/2
""",
}

SPECIAL = {
    133: """class Solution:
    def cloneGraph(self,node):
        if node is None:return None
        copies={node:Node(node.val)};queue=[node]
        for original in queue:
            for other in original.neighbors:
                if other not in copies:copies[other]=Node(other.val);queue.append(other)
                copies[original].neighbors.append(copies[other])
        return copies[node]
""",
    138: """class Solution:
    def copyRandomList(self,head):
        nodes=[];node=head
        while node:nodes.append(node);node=node.next
        copies={node:Node(node.val) for node in nodes};copies[None]=None
        for node in nodes:copies[node].next=copies[node.next];copies[node].random=copies[node.random]
        return copies[head]
""",
    141: """class Solution:
    def hasCycle(self,head):
        seen=set()
        while head:
            if head in seen:return True
            seen.add(head);head=head.next
        return False
""",
    142: """class Solution:
    def detectCycle(self,head):
        seen=set()
        while head:
            if head in seen:return head
            seen.add(head);head=head.next
        return None
""",
    160: """class Solution:
    def getIntersectionNode(self,headA,headB):
        seen=set()
        while headA:seen.add(headA);headA=headA.next
        while headB:
            if headB in seen:return headB
            headB=headB.next
        return None
""",
    237: """class Solution:
    def deleteNode(self,node):node.val=node.next.val;node.next=node.next.next
""",
    278: """class Solution:
    def firstBadVersion(self,n):
        low,high=1,n
        while low<high:
            mid=(low+high)//2
            if isBadVersion(mid):high=mid
            else:low=mid+1
        return low
""",
    297: """class Codec:
    def serialize(self,root):return json.dumps(_lc_encode(root))
    def deserialize(self,data):return _lc_tree(json.loads(data))
""",
    24: """class Solution:
    def swapPairs(self,head):
        dummy=ListNode(0,head);previous=dummy
        while previous.next and previous.next.next:
            left,right=previous.next,previous.next.next
            left.next=right.next;right.next=left;previous.next=right;previous=left
        return dummy.next
""",
    25: """class Solution:
    def reverseKGroup(self,head,k):
        nodes=[];node=head
        while node:nodes.append(node);node=node.next
        ordered=[n for i in range(0,len(nodes),k) for n in (nodes[i:i+k][::-1] if i+k<=len(nodes) else nodes[i:i+k])]
        for i,node in enumerate(ordered):node.next=ordered[i+1] if i+1<len(ordered) else None
        return ordered[0] if ordered else None
""",
    143: """class Solution:
    def reorderList(self,head):
        nodes=[];node=head
        while node:nodes.append(node);node=node.next
        ordered=[];left,right=0,len(nodes)-1
        while left<=right:
            ordered.append(nodes[left])
            if left!=right:ordered.append(nodes[right])
            left+=1;right-=1
        for i,node in enumerate(ordered):node.next=ordered[i+1] if i+1<len(ordered) else None
""",
}
CONNECT = """class Solution:
    def connect(self,root):
        level=[root] if root else []
        while level:
            for i,node in enumerate(level):node.next=level[i+1] if i+1<len(level) else None
            level=[child for node in level for child in (node.left,node.right) if child]
        return root
"""
LCA = """class Solution:
    def lowestCommonAncestor(self,root,p,q):
        if root is None or root is p or root is q:return root
        left=self.lowestCommonAncestor(root.left,p,q);right=self.lowestCommonAncestor(root.right,p,q)
        return root if left and right else left or right
"""


def python_solution(number: int, profile: JudgeProfile) -> str:
    if number in DESIGNS:
        return DESIGNS[number]
    if number in SPECIAL:
        return SPECIAL[number]
    if number in {116, 117}:
        return CONNECT
    if number in {235, 236}:
        return LCA
    oracle = (
        "independent"
        if profile.origin == "lustcode"
        else "special"
        if number in {37, 89, 95, 108, 109, 190, 224, 227, 273, 282}
        else "references"
    )
    parameters = profile.signature.parameters
    source = f"from app.judging.{oracle} import reference as _trusted_reference\n"
    source += """def _normalize(value,kind):
    if kind in ('TreeNode','ListNode'):return [] if value is None else _lc_encode(value)
    if kind.endswith('[]'):return [_normalize(v,kind[:-2]) for v in value]
    if kind.startswith('list<'):return [_normalize(v,kind[5:-1]) for v in value]
    return value
def _restore(value,kind):
    if kind=='ListNode':return _lc_list(value)
    if kind=='TreeNode':return _lc_tree(value)
    if kind.endswith('[]'):return [_restore(v,kind[:-2]) for v in value]
    if kind.startswith('list<'):return [_restore(v,kind[5:-1]) for v in value]
    return value
"""
    source += (
        "class Solution:\n    def "
        + profile.signature.name
        + "(self"
        + "".join(", " + p.name for p in parameters)
        + "):\n"
    )
    source += (
        "        _args=[" + ",".join(f"_normalize({p.name},{p.type!r})" for p in parameters) + "]\n"
    )
    source += f"        _answer=_trusted_reference({number},_args)\n"
    if profile.result == "prefix":
        source += (
            f'        {parameters[0].name}[:]=_answer["values"]\n        return _answer["length"]\n'
        )
    elif profile.result == "mutated_first":
        if parameters[0].type == "TreeNode":
            source += f"        _root=_lc_tree(_answer)\n        if {parameters[0].name} is not None:\n            {parameters[0].name}.val=_root.val\n            {parameters[0].name}.left=_root.left\n            {parameters[0].name}.right=_root.right\n"
        else:
            source += f"        {parameters[0].name}[:]=_answer\n"
    else:
        source += f"        return _restore(_answer,{profile.signature.return_type!r})\n"
    return source
