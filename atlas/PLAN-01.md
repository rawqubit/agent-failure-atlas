---
id: PLAN-01
title: The agent repeats the same tool call forever because nothing in its loop measures progress
category: planning
severity: high
frequency: common
symptom: Run ends at max_turns with dozens of identical tool calls returning identical results
stage: planning
tags: loops, termination, progress-detection
---

## What you see
The trace for a stuck run is 50 rows of the same span: `search_invoices(q="invoice 4471")` returning `[]` in 120 ms, every time. The run ends with `status=max_turns_exceeded`, which on the dashboard looks identical to a hard task that ran out of turns while making real progress. No error was raised anywhere; every tool call succeeded.

## Why it happens
The loop assumes that each turn moves the task forward and that the turn counter is therefore a proxy for work done. It is not: the cap counts turns, not progress, so it only decides how long the loop is allowed to spin. When the next action is determined by the last observation and the last observation is "no results", the agent's state is a fixed point: same context, same obvious recovery (search again), same result. Real models sample, so they are not literally pure functions, but with no new information in context the modal next action is the same call, and the repeated identical results in context give it no reason to deviate. Raising the cap changes the cost of the failure, not its occurrence. The stub in the repro assumes the policy is a pure function of the last observation, which is the limiting case of this behaviour.

## Minimal reproduction
```python
import hashlib, json

def search(q):
    return "no results"

def policy(obs):
    return ("search", {"q": "invoice 4471"})

def run(max_turns, detect, limit=3):
    seen, calls, obs = {}, 0, "start"
    for turn in range(max_turns):
        name, args = policy(obs)
        obs = search(**args)
        calls += 1
        if detect:
            blob = json.dumps([name, args, obs], sort_keys=True).encode()
            key = hashlib.sha1(blob).hexdigest()
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= limit:
                return calls, "escalated after %d identical calls" % limit
    return calls, "hit max_turns"

calls, end = run(50, detect=False)
assert calls == 50
print("FAILURE: %d identical calls, ended by: %s" % (calls, end))
calls, end = run(50, detect=True)
assert calls == 3
print("FIXED: %d calls, %s" % (calls, end))
```
The fuller version, including a result that carries a request id, is in repro/PLAN-01.py.

## Detection
Emit one fingerprint per tool span, `sha1(tool, args, normalized_result)`, and keep a per-run counter of the maximum repeat count; page or auto-escalate when it reaches 3. A cheap fleet-level query is "runs that ended in `max_turns_exceeded` where distinct fingerprints divided by turns is below 0.1", which separates spinning runs from slow-but-moving ones. In tests, stub every search-like tool to return empty and assert the run terminates in far fewer turns than the cap.

## The fix
Put a progress detector in the harness, outside the model. Hash each (tool, args, result) after dropping volatile fields such as request ids and timestamps. On the second identical repeat, return a synthetic observation that names the repetition and lists the untried alternatives (broaden the query, use a different tool, ask the user). On the third, stop the run and escalate. A line in the system prompt saying "do not repeat yourself" is a band-aid: the looping model is already reading it, and the harness is the only component that can see the whole history of calls.
```python
key = fingerprint(name, args, strip_volatile(result))
seen[key] += 1
if seen[key] >= 3:
    raise NoProgress(name, args)
```

## How it still bites
Results usually carry volatile fields: in the repro, a `request_id` makes the raw hash unique on every call, so the detector sees 50 distinct calls and never fires until the volatile keys are stripped. Models also loop through near-duplicates ("invoice 4471", then "Invoice 4471 ", then "4471 invoice") that never hash the same; the more robust signal is whether the run's accumulated state gained a new fact, not whether the call text repeated.
