---
id: PLAN-05
title: The agent executes a stale plan after a step's result invalidates the later steps
category: planning
severity: high
frequency: common
symptom: Every step of a multi-step run succeeds, but the later steps acted on an object the first step showed was the wrong one
stage: planning
tags: replanning, postconditions, plan-execution
---

## What you see
A support agent's plan has four steps: look up ticket 1042, assign it, set its priority, notify the customer. Step 1 returns `status: closed-duplicate-of:1001`. Steps 2 to 4 run anyway and each returns 200, and the customer gets "we are working on your ticket" for a ticket that was merged into 1001. The trace is four green spans.

## Why it happens
The plan was written once, before any tool ran, and it encodes an assumption about what step 1 would return: an open ticket. The executor's definition of a finished step is "the tool call did not raise". That is the wrong predicate, because the assign, priority and notify tools accept any ticket id and succeed on a closed one. The information that makes steps 2 to 4 meaningless arrives in step 1's result, and nothing between steps looks at it. The repro uses a plain function as the planner, with no model, because the failure is in the executor: a model plans once, and the loop honours the plan.

## Minimal reproduction
```python
TICKETS = {"1042": {"status": "closed-duplicate-of:1001"}, "1001": {"status": "open"}}

def make_plan(ticket, effects):
    act = lambda name: (lambda: effects.append((name, ticket)))
    return [
        (lambda: TICKETS[ticket], lambda r: r["status"] == "open"),
        (act("assign"), lambda r: True),
        (act("set_priority"), lambda r: True),
        (act("notify_customer"), lambda r: True),
    ]

def execute(ticket, validate):
    effects, i, replans = [], 0, 0
    plan = make_plan(ticket, effects)
    while i < len(plan):
        step, post = plan[i]
        result = step()
        if validate and not post(result):
            replans += 1
            assert replans <= 2, "escalate to a human"
            ticket = result["status"].split(":")[1]
            plan, i = make_plan(ticket, effects), 0
            continue
        i += 1
    return effects

bad = execute("1042", validate=False)
assert [t for _, t in bad] == ["1042"] * 3
print("FAILURE: %d side effects on closed duplicate 1042: %s" % (len(bad), bad))
good = execute("1042", validate=True)
assert [t for _, t in good] == ["1001"] * 3
print("FIXED: step 1 postcondition failed, re-planned onto 1001: %s" % good)
```
The fuller version, with named steps and a replan counter, is in repro/PLAN-05.py.

## Detection
Log each step's declared postcondition and its evaluated outcome as span attributes (`postcondition.passed`), and alert on runs where a read step returned a value that differs from what the plan assumed but the next step still ran; that is a join between step 1's result and step 2's start time. In tests, fixture every read tool with the surprising variant (archived, duplicate, deleted, different type) and assert the run either re-plans or stops before the first mutating step.

## The fix
Give every plan step a postcondition that code evaluates on its result, and make the loop re-plan from the observation when it fails. A step without one is one nobody has said can be wrong. Bound the number of replans (the repro asserts at 2 and escalates), otherwise a postcondition that can never hold turns this entry into PLAN-01. Telling the model to "reconsider the plan after each step" is a band-aid: it is a per-step instruction the model has to remember to apply, where a postcondition is evaluated whether it remembers or not.

## How it still bites
Postconditions only catch the surprises their author predicted, and they are checked at one instant: a ticket that is open when step 1 runs can be merged by a human before step 3. Mutating steps therefore need their own preconditions or versioned writes (see MEM-05). Re-planning after partial side effects is harder than the repro shows, because step 1 here is read-only; once step 2 has written, the new plan must first decide whether to compensate for it.
