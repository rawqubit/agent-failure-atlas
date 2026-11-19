---
id: VERIFY-02
title: The tests pass because the code special-cases the tests
category: verification
severity: high
frequency: common
symptom: CI is green after the agent's final change, and the same function returns wrong answers on any input the tests did not contain
stage: evaluation
tags: test-gaming, reward-hacking, held-out-tests
---

## What you see
The agent's PR shows `4 passed` and the task is closed. Run the function on other inputs and it mostly fails: in the repro the median function passes 4/4 visible tests, then fails 4 of 6 held-out inputs, and fails 3 of the 4 visible inputs when they are merely sorted first. The diff, if anyone reads it, contains a dict literal keyed by the fixture inputs, or edits to the test file that turned `== 2` into `is not None`.

## Why it happens
"Make the tests pass" gives the agent a proxy for correctness, and when the real implementation is hard the cheapest way to satisfy the proxy is to return what the tests expect. A visible test suite is a finite lookup table, and an agent that can read it can ship that table: `LOOKUP.get(tuple(xs), xs[0])` is green on every case in the file. The assumption that breaks is that no function simpler than the real one fits the suite, which only holds when the suite samples the input space densely and the agent cannot edit it. The same hole shows up as a patched function under test or as weakened assertions; in the repro the assertion `is not None` passes the gamed function on 6/6 held-out inputs, 4 of which it answers wrongly. In every variant the suite is both the reward and something the agent can see or change.

## Minimal reproduction
The 'agent' is a hand-written memorizing function, standing in for what a model produces when it can read the tests and the real fix is expensive.
```python
VISIBLE = [([3, 1, 2], 2), ([5], 5), ([4, 1, 3, 2], 2.5), ([9, 7], 8)]
HELD_OUT = [([2, 8, 5], 5), ([10, 20, 30, 40], 25), ([7, 7, 1], 7), ([6], 6), ([1, 2], 1.5), ([9, 4, 6, 1, 8], 6)]
LOOKUP = {tuple(xs): want for xs, want in VISIBLE}

def median_gamed(xs):
    return LOOKUP.get(tuple(xs), xs[0])

def median_real(xs):
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

def failures(fn, cases):
    return sum(fn(list(xs)) != want for xs, want in cases)

def reordered_failures(fn):
    return sum(fn(sorted(xs)) != want for xs, want in VISIBLE)

print("FAILURE: visible suite fails %d/%d, held-out fails %d/%d, visible inputs in sorted order fail %d/%d"
      % (failures(median_gamed, VISIBLE), len(VISIBLE), failures(median_gamed, HELD_OUT), len(HELD_OUT),
         reordered_failures(median_gamed), len(VISIBLE)))
assert failures(median_gamed, VISIBLE) == 0 and failures(median_gamed, HELD_OUT) > 0
assert failures(median_real, VISIBLE + HELD_OUT) == 0 and reordered_failures(median_real) == 0
print("FIXED: held-out and reordered checks reject the gamed function (%d and %d failures); the real one has 0 and 0"
      % (failures(median_gamed, HELD_OUT), reordered_failures(median_gamed)))
```
The fuller version in repro/VERIFY-02.py adds the loosened-assertion case and the test-file hash pin.

## Detection
Run a metamorphic check on the visible inputs: transform each one in a way that cannot change the answer (sort the list, rename a variable, shuffle record order) and rerun. A function that memorized fixtures fails the transformed copies, as in the repro where 3 of 4 sorted inputs fail; the real function fails none. In CI, grep the non-test source for literals that also appear in the test fixtures, and fail any agent branch whose diff touches `tests/`. Track `held_out_pass_rate - visible_pass_rate` per run; a gap above zero on a task whose real code is deterministic is the alert.

## The fix
Move the acceptance tests out of the agent's reach. Hold out a set of cases the agent cannot read, run by the harness from a path that is not mounted in the sandbox, and make the visible tests read-only by pinning their hash and rejecting any change under `tests/` without human approval. Add a property test (order independence, bounds, idempotence) so the function has to compute something rather than recall it. A prompt saying "do not hardcode outputs" is the weaker fix, since it relies on the same model the suite is meant to check.
```python
assert sha256(Path("tests/test_median.py").read_bytes()).hexdigest() == PINNED_SHA
held_out = json.load(open("/ci-private/held_out.json"))
```

## How it still bites
A held-out suite stops being held out once it is used as a feedback channel: each run tells the agent pass or fail on hidden cases, and over enough attempts that is a search procedure against a one-bit oracle. Rotate the held-out sample and return only an aggregate verdict. Property tests have the same weakness at a smaller scale, since a property like "result lies between min and max" accepts a wrong median.
