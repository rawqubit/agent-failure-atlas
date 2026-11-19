---
id: CTX-01
title: A constraint placed in the middle of a long context is ignored
category: context
severity: high
frequency: common
symptom: The agent violates a rule that is verifiably present in the prompt, only on runs where a large tool output sits above or below it
stage: model-call
tags: long-context, position-bias, constraints, prompt-assembly
---

## What you see
The prompt dump for the bad run shows the rule "do not delete any files" at about 50% of a 20k-token prompt, between a repo listing and eleven pages of search results. The agent runs `rm -rf build/ dist/ tmp/` anyway and its explanation never mentions the rule. The identical task with a short context passes, so the failure looks random until you sort violations by prompt length and by where the rule landed.

## Why it happens
The harness assumes that a sentence in the context is a sentence the model will act on, regardless of where it sits. Recall over a long context is not flat: instructions near the start and near the end get more weight than instructions buried between large blocks of unrelated text. Prompt assembly makes this worse by accident, because the system prompt stays at the front and tool results are appended after it, so a rule that arrives as a user message on turn 3 ends up in the middle once forty more turns of output pile up behind it. The competing instruction, usually the latest user request, sits at the very end where weight is highest. The constraint does not need to be missing from the context to lose; it only needs to be far from both edges.

## Minimal reproduction
The model here is a stub whose pull for each instruction is its strength times a U-shaped position weight; that models position-dependent recall and proves nothing about any real model.
```python
def weight(pos, total, span=12000):
    return max(0.2, 1 - min(pos, total - pos) / span)

def decide(context):
    pull, total, pos = {"keep": 0.0, "delete": 0.0}, sum(n for n, *_ in context), 0
    for n, kind, strength in context:
        if kind:
            pull[kind] += strength * weight(pos + n / 2, total)
        pos += n
    return max(pull, key=pull.get)

def build(constraint_at, chunks=40, restate=False):
    ctx = [(500, None, 0)] * chunks
    ctx.insert(constraint_at, (50, "keep", 1.0))
    if restate:
        ctx.append((50, "keep", 1.0))
    return ctx + [(50, "delete", 0.6)]

assert decide(build(0)) == "keep" and decide(build(40)) == "keep"
assert decide(build(20)) == "delete"
print("FAILURE: constraint at 50% of a 20k-token context loses to the final request; at 0% and 100% it wins")

assert decide(build(20, restate=True)) == "keep"
assert decide(build(3, chunks=6)) == "keep"
print("FIXED: restated after the haystack, or haystack cut to 3k tokens: the constraint wins at the middle")
```
The same code, with a sweep over nine positions, is in repro/CTX-01.py.

## Detection
Log, for every model call, the token offset of each pinned constraint as a fraction of total prompt tokens (`constraint_offset_frac`) next to the total prompt length. Alert on any call where a constraint sits between 0.2 and 0.8 and the prompt is over a length you set from your own data. Then run a position-sweep canary in CI: take a real long prompt from your logs, plant a synthetic rule with a trivially checkable violation ("never answer with the word PINEAPPLE"), place it at 0, 25, 50, 75 and 100 percent, and assert that compliance at 50 percent is within your tolerance of compliance at the edges. A gap in that table is the number to track across model upgrades.

## The fix
Assemble the prompt from typed slots instead of appending to a transcript: hard constraints go first, the bulk of tool output goes in the middle, and the constraints are repeated verbatim after the last tool result, immediately before the user's request. Also cut the haystack, because the middle position is less weak the shorter the context is; the cap from CTX-03 and the masking from CTX-04 do that. Rewording the rule ("IMPORTANT: ...") is a band-aid, since emphasis does not change where the text sits.
```python
def assemble(constraints, history, tool_outputs, request):
    return [*constraints, *history, *tool_outputs, *constraints, request]
```
Anything that must never happen should also be enforced in the tool layer (the delete tool refuses), so the prompt is the second line of defence, not the only one.

## How it still bites
Edge positions are finite: with fifteen rules, restating all of them at both ends makes the edges long, and the same dilution reappears inside the constraint block. Placement lowers the violation rate; it does not give you a rate of zero, so a constraint you can only state in words, with no check in code, stays probabilistic however well it is placed.
