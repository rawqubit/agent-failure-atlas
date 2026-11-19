"""PLAN-03: recursive decomposition with branching factor 3 and no depth or node budget."""
from collections import deque

B = 3


def bfs(atomic_at, depth_cap=99, budget=10**9):
    q, created, leaves, forced = deque([0]), 1, 0, 0
    while q:
        d = q.popleft()
        wants_children = d < atomic_at
        allowed = d < depth_cap and created + B <= budget
        kids = [d + 1] * B if wants_children and allowed else []
        forced += wants_children and not allowed
        created += len(kids)
        q.extend(kids)
        leaves += not kids
    return created, leaves, forced


def dfs(atomic_at, depth_cap=99, budget=10**9):
    created = 1
    depth1_expanded = 0

    def visit(d):
        nonlocal created, depth1_expanded
        if d >= atomic_at or d >= depth_cap or created + B > budget:
            return
        created += B
        if d == 1:
            depth1_expanded += 1
        for _ in range(B):
            visit(d + 1)

    visit(0)
    return created, depth1_expanded


nodes, leaves, _ = bfs(atomic_at=8)
assert nodes == sum(B ** k for k in range(9)) == 9841
print("FAILURE: b=3, tasks only stop splitting at depth 8: %d nodes (%d leaf tasks, one model call each)" % (nodes, leaves))

nodes, leaves, forced = bfs(atomic_at=8, depth_cap=4, budget=30)
assert nodes <= 30 and leaves >= 1
print("FIXED: depth cap 4, budget 30: %d nodes, %d leaves, %d tasks forced to run as leaves" % (nodes, leaves, forced))

nodes, expanded = dfs(atomic_at=8, depth_cap=4, budget=30)
assert nodes <= 30 and expanded < B
print("STILL BITES: same budget depth-first: %d nodes, only %d of %d root children were ever split" % (nodes, expanded, B))
