# ruff: noqa: E501
"""Node fixtures and identity validation inside Judge0's sandbox."""

PYTHON = r"""
class Node:
    def __init__(self,val=0,*args,**kwargs):
        self.val=val;self.left=self.right=self.next=self.random=None;self.neighbors=[]
        names=('neighbors',) if _lc_node_kind=='graph' else ('next','random') if _lc_node_kind=='random_list' else ('left','right','next')
        for name,value in zip(names,args):setattr(self,name,value)
        for name,value in kwargs.items():setattr(self,name,value)
def _lc_graph(values):
    nodes=[Node(i+1) for i in range(len(values))]
    for node,edges in zip(nodes,values):node.neighbors=[nodes[i-1] for i in edges]
    return nodes
def _lc_random(values,indices):
    nodes=[Node(v) for v in values]
    for i,node in enumerate(nodes):
        node.next=nodes[i+1] if i+1<len(nodes) else None
        node.random=nodes[indices[i]] if indices[i]>=0 else None
    return nodes
def _lc_graph_output(root,original):
    if root is None:return []
    if root.val!=1:raise ValueError('invalid root')
    nodes={1:root};queue=[root];original={id(n) for n in original}
    for node in queue:
        if id(node) in original or len(nodes)>10000:raise ValueError('copy aliases input')
        for other in node.neighbors:
            if other is None or type(other.val) is not int or not 1<=other.val<=10000:raise ValueError('invalid graph')
            if other.val in nodes and nodes[other.val] is not other:raise ValueError('duplicate label')
            if other.val not in nodes:nodes[other.val]=other;queue.append(other)
    if set(nodes)!=set(range(1,len(nodes)+1)):raise ValueError('missing label')
    return [sorted(n.val for n in nodes[i].neighbors) for i in range(1,len(nodes)+1)]
def _lc_random_output(root,original):
    original={id(n) for n in original};nodes=[];seen=set()
    while root is not None:
        if id(root) in original or id(root) in seen or len(nodes)>=10000:raise ValueError('invalid copy')
        seen.add(id(root));nodes.append(root);root=root.next
    indices={id(n):i for i,n in enumerate(nodes)}
    if any(n.random is not None and id(n.random) not in indices for n in nodes):raise ValueError('external random pointer')
    return [[n.val,indices[id(n.random)] if n.random is not None else None] for n in nodes]
def _lc_node_tree(node):
    if node is None:return None
    out=Node(node.val);out.left=_lc_node_tree(node.left);out.right=_lc_node_tree(node.right);return out
def _lc_next_output(root,original):
    if root is not original:raise ValueError('must return original root')
    result=[];level=[root] if root else []
    while level:
        current=level[0]
        for expected in level:
            if current is not expected:raise ValueError('incorrect next pointer')
            current=current.next
        if current is not None:raise ValueError('non-null level tail')
        result.append([n.val for n in level]);level=[c for n in level for c in (n.left,n.right) if c]
    return result
"""

CPP = r"""
struct Node {
    int val;Node *left=nullptr,*right=nullptr,*next=nullptr,*random=nullptr;vector<Node*> neighbors;
    Node(int v=0):val(v){}
    Node(int v,vector<Node*> n):val(v),neighbors(n){}
    Node(int v,Node*n,Node*r):val(v),next(n),random(r){}
    Node(int v,Node*l,Node*r,Node*n):val(v),left(l),right(r),next(n){}
};
vector<Node*> lcGraph(vector<vector<int>> values) {
    vector<Node*> nodes;for(int i=0;i<(int)values.size();i++)nodes.push_back(new Node(i+1));
    for(size_t i=0;i<values.size();i++)for(int j:values[i])nodes[i]->neighbors.push_back(nodes[j-1]);return nodes;
}
vector<Node*> lcRandom(vector<int> values,vector<int> indices) {
    vector<Node*> nodes;for(int x:values)nodes.push_back(new Node(x));
    for(size_t i=0;i<nodes.size();i++){nodes[i]->next=i+1<nodes.size()?nodes[i+1]:nullptr;nodes[i]->random=indices[i]>=0?nodes[indices[i]]:nullptr;}return nodes;
}
string lcGraphOutput(Node*root,vector<Node*> original) {
    if(!root)return "[]";if(root->val!=1)throw runtime_error("invalid graph root");
    unordered_set<Node*> input(original.begin(),original.end());map<int,Node*> nodes{{1,root}};vector<Node*> q{root};
    for(size_t i=0;i<q.size();i++) {
        Node*n=q[i];if(input.count(n)||nodes.size()>10000)throw runtime_error("invalid copy");
        for(Node*m:n->neighbors){if(!m||m->val<1||m->val>10000)throw runtime_error("invalid neighbor");
            if(nodes.count(m->val)){if(nodes[m->val]!=m)throw runtime_error("duplicate label");}
            else{nodes[m->val]=m;q.push_back(m);}}
    }
    vector<vector<int>> out;
    for(int i=1;i<=(int)nodes.size();i++) {if(!nodes.count(i))throw runtime_error("missing label");vector<int> row;for(auto*n:nodes[i]->neighbors)row.push_back(n->val);sort(row.begin(),row.end());out.push_back(row);}
    return lcJson(out);
}
string lcRandomOutput(Node*root,vector<Node*> original) {
    unordered_set<Node*> input(original.begin(),original.end());unordered_map<Node*,int> indices;vector<Node*> nodes;
    for(auto*n=root;n;n=n->next){if(input.count(n)||indices.count(n)||nodes.size()>=10000)throw runtime_error("invalid copy");indices[n]=nodes.size();nodes.push_back(n);}
    string out="[";
    for(auto*n:nodes){if(n->random&&!indices.count(n->random))throw runtime_error("external pointer");if(out.size()>1)out+=",";out+="["+lcJson(n->val)+","+(n->random?lcJson(indices[n->random]):string("null"))+"]";}
    return out+"]";
}
Node* lcNodeTree(TreeNode*n){if(!n)return nullptr;auto*r=new Node(n->val);r->left=lcNodeTree(n->left);r->right=lcNodeTree(n->right);return r;}
string lcNextOutput(Node*root,Node*original) {
    if(root!=original)throw runtime_error("must return original root");vector<vector<int>> out;vector<Node*> level;if(root)level.push_back(root);
    while(!level.empty()) {Node*current=level[0];vector<Node*> next;vector<int> row;
        for(auto*n:level){if(current!=n)throw runtime_error("wrong next pointer");current=current->next;row.push_back(n->val);if(n->left)next.push_back(n->left);if(n->right)next.push_back(n->right);}
        if(current)throw runtime_error("non-null tail");out.push_back(row);level=next;
    } return lcJson(out);
}
"""

JAVA = r"""
class Node {
    int val;Node left,right,next,random;List<Node> neighbors=new ArrayList<>();
    Node(){} Node(int v){val=v;} Node(int v,ArrayList<Node> n){val=v;neighbors=n;}
    Node(int v,Node n,Node r){val=v;next=n;random=r;}
    Node(int v,Node l,Node r,Node n){val=v;left=l;right=r;next=n;}
}
class NodeFixtures {
    static ArrayList<Node> graph(int[][] values){ArrayList<Node> nodes=new ArrayList<>();for(int i=0;i<values.length;i++)nodes.add(new Node(i+1));for(int i=0;i<values.length;i++)for(int j:values[i])nodes.get(i).neighbors.add(nodes.get(j-1));return nodes;}
    static ArrayList<Node> random(int[]values,int[]indices){ArrayList<Node> nodes=new ArrayList<>();for(int x:values)nodes.add(new Node(x));for(int i=0;i<nodes.size();i++){Node n=nodes.get(i);n.next=i+1<nodes.size()?nodes.get(i+1):null;n.random=indices[i]>=0?nodes.get(indices[i]):null;}return nodes;}
    static Object graphOutput(Node root,ArrayList<Node> original){
        List<List<Integer>> out=new ArrayList<>();if(root==null)return out;if(root.val!=1)throw new IllegalArgumentException("invalid root");
        Map<Integer,Node> nodes=new TreeMap<>();ArrayList<Node> q=new ArrayList<>();nodes.put(1,root);q.add(root);
        for(int i=0;i<q.size();i++){Node n=q.get(i);if(original.contains(n)||nodes.size()>10000)throw new IllegalArgumentException("invalid copy");for(Node m:n.neighbors){if(m==null||m.val<1||m.val>10000)throw new IllegalArgumentException("invalid neighbor");if(nodes.containsKey(m.val)){if(nodes.get(m.val)!=m)throw new IllegalArgumentException("duplicate label");}else{nodes.put(m.val,m);q.add(m);}}}
        for(int i=1;i<=nodes.size();i++){if(!nodes.containsKey(i))throw new IllegalArgumentException("missing label");List<Integer> row=new ArrayList<>();for(Node n:nodes.get(i).neighbors)row.add(n.val);Collections.sort(row);out.add(row);}return out;
    }
    static Object randomOutput(Node root,ArrayList<Node> original){
        IdentityHashMap<Node,Integer> indices=new IdentityHashMap<>();List<Node> nodes=new ArrayList<>();
        for(Node n=root;n!=null;n=n.next){if(original.contains(n)||indices.containsKey(n)||nodes.size()>=10000)throw new IllegalArgumentException("invalid copy");indices.put(n,nodes.size());nodes.add(n);}
        List<List<Integer>> out=new ArrayList<>();for(Node n:nodes){if(n.random!=null&&!indices.containsKey(n.random))throw new IllegalArgumentException("external pointer");out.add(Arrays.asList(n.val,n.random==null?null:indices.get(n.random)));}return out;
    }
    static Node tree(TreeNode n){if(n==null)return null;Node root=new Node(n.val);root.left=tree(n.left);root.right=tree(n.right);return root;}
    static Object nextOutput(Node root,Node original){
        if(root!=original)throw new IllegalArgumentException("must return original root");List<List<Integer>> out=new ArrayList<>();List<Node> level=new ArrayList<>();if(root!=null)level.add(root);
        while(!level.isEmpty()){Node current=level.get(0);List<Node> next=new ArrayList<>();List<Integer> row=new ArrayList<>();for(Node n:level){if(current!=n)throw new IllegalArgumentException("wrong next pointer");current=current.next;row.add(n.val);if(n.left!=null)next.add(n.left);if(n.right!=null)next.add(n.right);}if(current!=null)throw new IllegalArgumentException("non-null tail");out.add(row);level=next;}return out;
    }
}
"""
