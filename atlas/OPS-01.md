---
id: OPS-01
title: An incident cannot be reproduced because the run left no replayable record
category: operations
severity: high
frequency: common
symptom: The postmortem reruns the failing task, the agent takes a different path and succeeds, and nobody can say what happened the first time
stage: deployment
tags: observability, replay, non-determinism, tracing
---

## What you see
An agent restarted the wrong job at 02:10. In the morning someone reruns the same prompt against the same account and gets a clean run: different tool calls, different results, a different final answer. The logs hold the user prompt and the final message, and perhaps a list of tool names, but not the tool results or the model's intermediate outputs. In the repro, the incident run polls the quota three times before restarting and the rerun polls once.

## Why it happens
An agent run is a function of its sampled model outputs, the data its tools returned, and the clock, and none of the three is reproducible after the fact. Sampling means the same prompt yields a different action. Tool backends return data that changes with time and load. Ids, timestamps and ordering are generated fresh on each call. The assumption that breaks is that you can recreate a failure by re-running its inputs; the input that mattered was the entire sequence of observations, and only the first message of it was kept. Logging the prompt keeps the one piece that was already known.

## Minimal reproduction
```python
import random

def make_world(clock):
    t = [clock]
    def tool(action):
        t[0] += 7
        return t[0] % 37
    return tool

def make_model(seed):
    rng = random.Random(seed)
    return lambda history: "done" if len(history) >= 4 or (history and rng.random() < 0.3) \
        else rng.choice(["poll", "restart"])

def run(model, tool):
    history = []
    while (action := model(history)) != "done":
        history.append((action, tool(action)))
    return history

def record(model, tool, log):
    def m(history):
        log.append(model(history)); return log[-1]
    def t(action):
        log.append(tool(action)); return log[-1]
    return m, t

def replay(log):
    it = iter(log)
    return (lambda history: next(it)), (lambda action: next(it))

log = []
incident = run(*record(make_model(0), make_world(1000), log))
rerun = run(make_model(1), make_world(1013))
print("FAILURE: incident", incident, "rerun", rerun, "same:", incident == rerun)
replayed = run(*replay(log))
print("FIXED: replay", replayed, "same:", replayed == incident)
assert incident != rerun and replayed == incident
```
The model is a seeded stub, so the repro shows that reruns diverge when sampling and tool data differ; it does not measure how often real models diverge. repro/OPS-01.py adds tool-call matching during replay and the patched-code case below.

## Detection
Make replayability a tested property: pick a recent production trace, run the replay harness on it, and assert the replayed step sequence equals the recorded one; do this in CI against a rotating sample of traces. Measure the share of runs that have a complete trace (every model response and tool result present, with a clock value) and alert when it drops below 100%, since a trace missing one tool result cannot be replayed past that step. During an incident, a quick signal is whether the on-call can state, from stored data alone, the exact arguments of the call that caused the damage.

## The fix
Record at the two boundaries the agent crosses: each model request and response, and each tool call with its result, plus the clock and any seed or generated id the code consumed. Store the trace per run id, immutable, with the version of the agent code and the resolved model id. A replay harness runs the unchanged agent loop with a model client and tool client that return the recorded values in order, and raises when the loop's request differs from the recorded one. Recording outputs, not just a seed, is the structural choice: a seed only helps when the sampler is under your control, and tool data never is.
```python
class ReplayDivergence(Exception): ...
def tool_call(name, args):
    step = next(steps)
    if (step.tool, step.args) != (name, args):
        raise ReplayDivergence(f"recorded {step.tool}{step.args}, now {name}{args}")
    return step.result
```

## How it still bites
Strict replay breaks the moment you fix the bug: in repro/OPS-01.py the patched code adds a `dry_run` argument to the restart call, the harness sees a request that differs from the recording and raises ReplayDivergence at step 4, so the trace cannot confirm the fix on the original incident without a deliberate lenient mode for the fields you changed. Traces also contain whatever the tools returned, including customer data and secrets (see SEC-05), so retention and access rules for the replay store need to be set before the first incident, not after it.
