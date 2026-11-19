---
id: PLAN-03
title: Recursive decomposition has no depth or budget and the task tree explodes
category: planning
severity: critical
frequency: occasional
symptom: One user request spawns thousands of subtasks; queue depth and provider 429s climb while every node reports success
stage: planning
tags: decomposition, fan-out, budgets, recursion
---

## What you see
A single request, "audit this repository", shows up as one root span with a tree of 9,841 child task spans. The orchestrator queue grows faster than it drains, the provider starts returning 429, and other tenants' runs on the same key slow down. Nothing looks broken per node: each subtask logged a result, so no stuck-run alert fires.

## Why it happens
Each decomposition decision is local: the model sees one task and judges whether it is small enough to execute or should be split. Nothing in that view says how many siblings exist or how deep the tree already is, and a subtask inherits enough of its parent's context that it rarely looks atomic. With branching factor b the tree has (b^(d+1) - 1) / (b - 1) nodes at depth d, so with b = 3 depth 8 is 9,841 nodes and depth 9 is 29,524: one extra level triples the bill. Local decisions with a global exponential consequence is the whole mechanism. The stub in the repro assumes the model keeps splitting into 3 until depth 8, because subtasks never look smaller to it.

## Minimal reproduction
```python
from collections import deque

def tree(atomic_at, depth_cap=99, budget=10**9, b=3):
    q, created = deque([0]), 1
    while q:
        d = q.popleft()
        if d < atomic_at and d < depth_cap and created + b <= budget:
            created += b
            q.extend([d + 1] * b)
    return created

n = tree(atomic_at=8)
assert n == 9841
print("FAILURE: branching 3, stops splitting at depth 8: %d task nodes" % n)
m = tree(atomic_at=8, depth_cap=4, budget=30)
assert m <= 30
print("FIXED: depth cap 4 and node budget 30: %d task nodes" % m)
```
The fuller version, including the depth-first case, is in repro/PLAN-03.py.

## Detection
Count spawn events per root task id in the orchestrator, not in the model's trace: emit `task_tree_nodes` and `task_tree_max_depth` gauges keyed by root id, and alert when nodes pass 80% of the configured budget, so the alert fires before the cap does. Also graph the queue's enqueue rate divided by its completion rate; a ratio above 1 for more than a few minutes means a tree is growing faster than it is being worked. A test that feeds a decomposer stub which always splits must terminate at the budget.

## The fix
Enforce three limits in the orchestrator, which owns the counters: a depth cap, a global node budget per root task, and leaf forcing. When a node would exceed either limit, it is not refused and it is not split; it is executed as a leaf with its full, coarse description. The model never sees the limits as a suggestion, because a prompt asking it to "keep decomposition shallow" is a band-aid on a quantity it cannot observe.
```python
if node.depth >= MAX_DEPTH or tree.count + b > BUDGET:
    return execute_as_leaf(node)
children = decompose(node)
tree.count += len(children)
```

## How it still bites
Leaf forcing hands a coarse task to one call that was expected to be split, so quality degrades exactly where the budget runs out. Order matters too: in the repro, the same budget of 30 spent depth-first leaves only 1 of the 3 root children ever split, while breadth-first spreads it across the tree. Use breadth-first expansion or per-subtree budgets, or the first branch eats the budget and its siblings get no decomposition at all.
