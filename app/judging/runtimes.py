# ruff: noqa: E501
"""Small serialization runtimes injected into sandboxed programs, never run by the API."""

PYTHON = r"""
import json, sys, math, collections, heapq, itertools, functools, bisect, re
from typing import *
from collections import *
from functools import *
from heapq import *
from bisect import bisect_left, bisect_right, insort, insort_left, insort_right
class ListNode:
    def __init__(self, val=0, next=None): self.val, self.next = val, next
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val, self.left, self.right = val, left, right
def _lc_list(values):
    head = tail = ListNode()
    for value in values:
        tail.next = ListNode(value); tail = tail.next
    return head.next
def _lc_tree(values):
    if not values or values[0] is None: return None
    root = TreeNode(values[0]); queue = [root]; i = 1
    for node in queue:
        for side in ('left', 'right'):
            if i < len(values) and values[i] is not None:
                child = TreeNode(values[i]); setattr(node, side, child); queue.append(child)
            i += 1
    return root
def _lc_encode(value):
    if isinstance(value, ListNode):
        result, seen = [], set()
        while value:
            if id(value) in seen or len(result) >= 10000: raise ValueError('invalid list')
            seen.add(id(value)); result.append(value.val); value = value.next
        return result
    if isinstance(value, TreeNode):
        result, queue, seen = [], [value], set()
        for node in queue:
            if node is None: result.append(None); continue
            if id(node) in seen or len(seen) >= 10000: raise ValueError('invalid tree')
            seen.add(id(node)); result.append(node.val); queue.extend([node.left, node.right])
        while result and result[-1] is None: result.pop()
        return result
    if isinstance(value, (list, tuple)): return [_lc_encode(v) for v in value]
    if isinstance(value, dict): return {k: _lc_encode(v) for k, v in value.items()}
    return value
"""

CPP = r"""
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <unordered_map>
#include <unordered_set>
#include <map>
#include <set>
#include <queue>
#include <stack>
#include <deque>
#include <list>
#include <numeric>
#include <functional>
#include <limits>
#include <climits>
#include <cmath>
#include <optional>
#include <stdexcept>
#include <array>
#include <bitset>
#include <tuple>
#include <cstring>
#include <cctype>
#include <cstdint>
#include <cassert>
#include <cstdio>
#include <unistd.h>
using namespace std;
struct ListNode {
    int val; ListNode *next;
    ListNode(int x=0, ListNode *p=nullptr):val(x),next(p){}
};
struct TreeNode {
    int val; TreeNode *left, *right;
    TreeNode(int x=0, TreeNode *l=nullptr, TreeNode *r=nullptr):val(x),left(l),right(r){}
};
ListNode* lcList(vector<int> values) {
    auto *head=new ListNode(), *tail=head;
    for (int x:values) { tail->next=new ListNode(x); tail=tail->next; }
    return head->next;
}
TreeNode* lcTree(vector<optional<int>> values) {
    if (values.empty() || !values[0]) return nullptr;
    auto *root=new TreeNode(*values[0]); vector<TreeNode*> q{root}; size_t i=1;
    for (size_t n=0;n<q.size();++n) {
        for (auto slot : {&q[n]->left, &q[n]->right}) {
            if (i<values.size() && values[i]) { *slot=new TreeNode(*values[i]); q.push_back(*slot); }
            ++i;
        }
    }
    return root;
}
string lcJson(const string &s) {
    ostringstream out; out << '"';
    for (unsigned char c:s) {
        if (c=='"' || c=='\\') out << '\\' << c;
        else if (c<32) out << "\\u" << hex << setw(4) << setfill('0') << (int)c << dec;
        else out << c;
    }
    return out.str()+'"';
}
string lcJson(bool v) { return v?"true":"false"; }
string lcJson(char v) { return lcJson(string(1,v)); }
string lcJson(int v) { return to_string(v); }
string lcJson(long v) { return to_string(v); }
string lcJson(long long v) { return to_string(v); }
string lcJson(double v) { ostringstream s; s << setprecision(17) << v; return s.str(); }
string lcJson(nullptr_t) { return "null"; }
string lcJson(ListNode *node) {
    string out="["; unordered_set<ListNode*> seen;
    while(node) {
        if (!seen.insert(node).second || seen.size()>10000) throw runtime_error("invalid list");
        if (out.size()>1) out+=","; out+=to_string(node->val); node=node->next;
    }
    return out+"]";
}
string lcJson(TreeNode *node) {
    vector<string> result; vector<TreeNode*> q{node}; unordered_set<TreeNode*> seen;
    for (size_t i=0;i<q.size();++i) {
        auto *n=q[i]; if(!n) { result.push_back("null"); continue; }
        if (!seen.insert(n).second || seen.size()>10000) throw runtime_error("invalid tree");
        result.push_back(to_string(n->val)); q.push_back(n->left); q.push_back(n->right);
    }
    while (!result.empty() && result.back()=="null") result.pop_back();
    string out="["; for (auto &s:result) { if(out.size()>1)out+=","; out+=s; } return out+"]";
}
template<class T> string lcJson(const vector<T> &values) {
    string out="["; for (const auto &v:values) { if(out.size()>1)out+=","; out+=lcJson(v); }
    return out+"]";
}
"""

JAVA = r"""
import java.util.*;
import java.io.*;
import java.math.*;
import java.lang.reflect.Array;
class LCOutput {
    static final PrintStream output=System.out;
    static { System.setOut(System.err); }
}
class ListNode {
    int val; ListNode next;
    ListNode(){} ListNode(int x){val=x;} ListNode(int x,ListNode n){val=x;next=n;}
}
class TreeNode {
    int val; TreeNode left,right;
    TreeNode(){} TreeNode(int x){val=x;}
    TreeNode(int x,TreeNode l,TreeNode r){val=x;left=l;right=r;}
}
"""

JAVA_MAIN = r"""
public class Main {
    static final PrintStream _lc_result_output=LCOutput.output;
    static String lcTyped(Object value,String kind) {
        if(kind.equals("TreeNode")||kind.equals("ListNode"))return value==null?"[]":lcJson(value);
        if(kind.endsWith("[]")||kind.startsWith("list<")) {
            String inner=kind.endsWith("[]")?kind.substring(0,kind.length()-2):kind.substring(5,kind.length()-1);
            List<Object> values=new ArrayList<>();
            if(value.getClass().isArray())for(int i=0;i<Array.getLength(value);i++)values.add(Array.get(value,i));
            else for(Object item:(Iterable<?>)value)values.add(item);
            StringBuilder out=new StringBuilder("[");for(Object item:values){if(out.length()>1)out.append(',');out.append(lcTyped(item,inner));}return out.append(']').toString();
        }
        return lcJson(value);
    }
    static ListNode lcList(int[] a) {
        ListNode head=new ListNode(), tail=head;
        for(int x:a) {tail.next=new ListNode(x);tail=tail.next;} return head.next;
    }
    static TreeNode lcTree(Integer[] a) {
        if(a.length==0 || a[0]==null)return null;
        TreeNode root=new TreeNode(a[0]); List<TreeNode> q=new ArrayList<>(); q.add(root);int i=1;
        for(int n=0;n<q.size();n++) {
            TreeNode t=q.get(n);
            if(i<a.length && a[i]!=null) {t.left=new TreeNode(a[i]);q.add(t.left);} i++;
            if(i<a.length && a[i]!=null) {t.right=new TreeNode(a[i]);q.add(t.right);} i++;
        } return root;
    }
    static String lcJson(Object value) {
        if(value==null)return "null";
        if(value instanceof String || value instanceof Character) {
            String s=value.toString(); StringBuilder out=new StringBuilder("\"");
            for(int i=0;i<s.length();i++) {
                char c=s.charAt(i);
                if(c=='"'||c=='\\') out.append('\\').append(c);
                else if(c<32)out.append(String.format("\\u%04x",(int)c));
                else out.append(c);
            } return out.append('"').toString();
        }
        if(value instanceof ListNode) {
            List<Integer> out=new ArrayList<>(); Set<ListNode> seen=Collections.newSetFromMap(new IdentityHashMap<>());
            for(ListNode n=(ListNode)value;n!=null;n=n.next) {
                if(!seen.add(n)||seen.size()>10000)throw new IllegalArgumentException("invalid list");
                out.add(n.val);
            } return lcJson(out);
        }
        if(value instanceof TreeNode) {
            List<Integer> out=new ArrayList<>(); List<TreeNode> q=new ArrayList<>(); q.add((TreeNode)value);
            Set<TreeNode> seen=Collections.newSetFromMap(new IdentityHashMap<>());
            for(int i=0;i<q.size();i++) {
                TreeNode n=q.get(i);if(n==null){out.add(null);continue;}
                if(!seen.add(n)||seen.size()>10000)throw new IllegalArgumentException("invalid tree");
                out.add(n.val);q.add(n.left);q.add(n.right);
            }
            while(!out.isEmpty()&&out.get(out.size()-1)==null)out.remove(out.size()-1);
            return lcJson(out);
        }
        if(value.getClass().isArray()) {
            List<Object> out=new ArrayList<>();for(int i=0;i<Array.getLength(value);i++)out.add(Array.get(value,i));
            return lcJson(out);
        }
        if(value instanceof Iterable<?>) {
            StringBuilder out=new StringBuilder("[");
            for(Object x:(Iterable<?>)value) {if(out.length()>1)out.append(',');out.append(lcJson(x));}
            return out.append(']').toString();
        }
        if(value instanceof Number || value instanceof Boolean)return value.toString();
        throw new IllegalArgumentException("invalid output type");
    }
"""
