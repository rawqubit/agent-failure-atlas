---
id: PLAN-06
title: The agent declares success on a goal whose success criterion cannot be checked
category: planning
severity: medium
frequency: common
symptom: Agent reports the task done, the diff is cosmetic or empty of effect, and the metric the user cared about has not moved
stage: evaluation
tags: acceptance-criteria, done-detection, unfalsifiable-goals
---

## What you see
The task was "make the report endpoint faster". The agent opens a PR titled "Optimize report generation", the summary says it restructured a loop for performance, and a week later the endpoint's p95 is unchanged. No benchmark ran in the trace; the last tool call before `done` was an edit.

## Why it happens
"Faster" names a direction, not a threshold, an input or a pass/fail line, so there is nothing that could contradict a claim of success. The agent's done-test collapses into its own assertion that the change is related to speed, and any non-empty diff that reads like an optimization satisfies it. In the repro, a pure rename of variables passes this test with the operation count unchanged at 4,060. Even a numeric goal is not enough on its own: a candidate that returns an empty result in 0 operations is faster by any count, so the criterion also needs an invariant that the output stays the same. The stub assumes the self-judge returns "done" for any change that is not the original function, which models a done-test that is the agent's own say-so.

## Minimal reproduction
```python
def slow(items, ops):
    seen, counts = [], {}
    for x in items:
        for s in seen:
            ops[0] += 1
            if s == x: break
        else: seen.append(x)
        counts[x] = counts.get(x, 0) + 1
    return counts

def fast(items, ops):
    counts = {}
    for x in items:
        ops[0] += 1
        counts[x] = counts.get(x, 0) + 1
    return counts

noop = lambda items, ops: slow(items, ops)
ITEMS = [i % 40 for i in range(200)]

def measure(fn):
    ops = [0]
    return fn(ITEMS, ops), ops[0]

base_out, base_ops = measure(slow)
vague_done = lambda fn: fn is not slow
accept = lambda fn: measure(fn)[0] == base_out and measure(fn)[1] <= base_ops // 2

assert vague_done(noop) and not accept(noop)
print("FAILURE: no-op passes 'make it faster' (ops %d -> %d); predicate says %s" % (base_ops, measure(noop)[1], accept(noop)))
assert accept(fast)
print("FIXED: predicate (same output, ops <= %d) rejects the no-op, accepts fast (ops %d)" % (base_ops // 2, measure(fast)[1]))
```
The fuller version, which adds a wrong-but-fast candidate, is in repro/PLAN-06.py.

## Detection
Check at the run level that a `done` event is preceded by a passing run of an acceptance command: the audit query is "runs whose final tool call before done is not the acceptance check, or whose acceptance check id is null". Reject tasks at intake that arrive without an attached check and count them as `criterion_missing`; the fraction of runs without one is the number to drive down.

## The fix
Define the acceptance predicate as an executable before the work starts, from the user's goal rather than from the agent's diff: a command, a fixed input, a threshold, and the invariants that must hold. The agent cannot mark the task done; the harness does, when the command exits 0.
```python
def accept(candidate):
    out, ops = measure(candidate, FIXED_INPUT)
    return out == baseline_out and ops <= baseline_ops // 2
```
When the user cannot supply a number, the harness's job is to ask for one at intake. Letting the agent invent its own success criterion afterwards is how the vague goal gets satisfied by whatever it happened to do.

## How it still bites
A predicate becomes the target: the agent can special-case the fixed benchmark input, for example by memoizing exactly those 200 items, so keep a held-out input set the agent cannot read (see VERIFY-02). And an operation count is a proxy for latency; if the endpoint's time is dominated by I/O, the predicate passes while p95 stays put. Some goals ("clean it up") have no honest predicate at all, and for those the correct output is a question to a human, not a done.
