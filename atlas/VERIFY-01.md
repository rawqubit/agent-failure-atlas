---
id: VERIFY-01
title: The agent grades its own work with the same misreading that produced it
category: verification
severity: high
frequency: common
symptom: Every self-written test is green and the agent reports the work verified, but the output is off by one at the boundary the spec was ambiguous about
stage: evaluation
tags: self-verification, spec-ambiguity, tests
---

## What you see
The run ends with `5 passed` from tests the agent wrote itself, and the final message says the function is verified. A user calls `days(3, 5)` and gets `[3, 4]` where the spec says both ends are included, and `days(1, 1)` returns `[]`. In the repro the self-tests pass 5/5 on the misreading and 5/5 on the correct code, while a four-case oracle copied from the spec fails the misreading 4/4.

## Why it happens
The agent treats a check it wrote as independent evidence about code it wrote, but both come out of one reading of the spec. Here the belief "hi is excluded" feeds the implementation (`range(lo, hi)`) and the test (`len(out) == hi - lo`, `out[-1] == hi - 1`) alike. A test suite that is a function of the belief passes under every belief, so a green run says nothing about which belief is right; the repro shows the same self-tests passing 5/5 under both readings. Tests written after looking at the output make it worse, because `[3, 4]` looks plausible once you already think the range is half-open. The agent's cases also skip `lo == hi`, the one input that would have returned an empty list and drawn attention to the boundary. The assumption that breaks is that agreement between two artifacts from the same author is a second opinion.

## Minimal reproduction
No model is called. The misreading is hard-coded as the agent's belief, and the self-tests are derived from that belief the way a model's tests are derived from its own interpretation of the spec.
```python
ORACLE = [((3, 5), [3, 4, 5]), ((1, 1), [1]), ((0, 2), [0, 1, 2]), ((7, 9), [7, 8, 9])]
CASES = [(3, 5), (1, 4), (0, 9), (2, 3), (6, 8)]

def build(hi_included):
    return lambda lo, hi: list(range(lo, hi + int(hi_included)))

def self_tests(fn, hi_included):
    last = lambda hi: hi if hi_included else hi - 1
    return sum(
        fn(lo, hi)[0] == lo and fn(lo, hi)[-1] == last(hi) and len(fn(lo, hi)) == last(hi) - lo + 1
        for lo, hi in CASES
    )

def oracle_failures(fn):
    return sum(fn(*args) != want for args, want in ORACLE)

misread, correct = build(False), build(True)
print("FAILURE: self-tests pass %d/%d on the misreading, %d/%d on the correct code; spec oracle fails %d/%d (days(3, 5) -> %s)"
      % (self_tests(misread, False), len(CASES), self_tests(correct, True), len(CASES),
         oracle_failures(misread), len(ORACLE), misread(3, 5)))
assert self_tests(misread, False) == self_tests(correct, True) == len(CASES)
assert oracle_failures(misread) == len(ORACLE) and oracle_failures(correct) == 0
print("FIXED: oracle written from the spec fails the misreading %d/%d and the corrected code %d/%d"
      % (oracle_failures(misread), len(ORACLE), oracle_failures(correct), len(ORACLE)))
```
The same code with extra assertions about the flipped belief is in repro/VERIFY-01.py.

## Detection
Keep the spec's worked examples as machine-readable fixtures created with the task, and run them in a verifier step that imports only the entry point. Log one event per task with `self_tests_passed` and `oracle_passed`, and alert on the combination `true, false`; that pair is the signature of a shared misreading. A check that needs no oracle is boundary coverage: classify the inputs in the agent's own tests (empty, single element, lo equal to hi, negative) and flag any task whose tests contain none of the degenerate classes. In the repro the five self-test inputs all have lo below hi, and the only inputs where the two readings produce visibly different shapes, like `days(1, 1)` returning `[]`, are missing.

## The fix
Write the acceptance cases from the spec before any implementation exists, in a separate process that never sees the code, and give the verifier only the spec and a callable. Literal examples from the spec text are the strongest anchor, because they cannot be reinterpreted. Asking the same agent to "re-read the spec carefully" is a band-aid: it asks the same reader to find its own reading wrong.
```python
ORACLE = [((3, 5), [3, 4, 5]), ((1, 1), [1])]

def verify(entry_point):
    return [(a, want, entry_point(*a)) for a, want in ORACLE if entry_point(*a) != want]
```

## How it still bites
A second instance of the same model writing the oracle shares the first one's priors, so for a genuinely ambiguous sentence it will often pick the same default reading and the two will agree again. Independence of process is not independence of belief; the oracle has to be anchored to something outside the model's reading, such as a human-written example, a reference implementation, or recorded real inputs and outputs.
