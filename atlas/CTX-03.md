---
id: CTX-03
title: One huge tool output pushes the system prompt out of the window
category: context
severity: high
frequency: common
symptom: Right after a large log or file is pasted or fetched, the agent forgets its persona, output format and safety rules
stage: context-assembly
tags: truncation, system-prompt, context-window, tool-output
---

## What you see
Turn 14 returns a 90,000-token build log. The very next response is in the wrong format, ignores the "never print customer emails" rule and signs off as a generic assistant. The request that went out starts with the user's fourth message instead of the system prompt, and your trace shows 103,550 tokens assembled against a 100,000-token window.

## Why it happens
The truncation policy assumes that the oldest content is the least valuable, which is true of chat turns and false of the system prompt, since it is the oldest message by construction. When the assembled prompt exceeds the window, the policy pops messages from the front until the total fits. A single 90,000-token message makes the overflow large enough that popping has to go past the first few turns, and the system prompt is the first thing in the list to go. Nothing raises an error: the request succeeds, the model answers with whatever it has left, and the only symptom is behaviour. The size of the tool result is also never checked on its own; each message was individually allowed, and only the sum is policed.

## Minimal reproduction
Tokens are approximated as whitespace-separated words; the window is 100k to keep the numbers readable.
```python
WINDOW = 100_000
tokens = lambda m: len(m["text"].split())
msg = lambda role, n, tag="x": {"role": role, "text": " ".join([tag] * n)}
msgs = ([msg("system", 1500, "RULES")] + [msg("user", 1000) for _ in range(12)]
        + [msg("tool", 90_000, "LOG"), msg("user", 50)])

def truncate_oldest(msgs):
    msgs = list(msgs)
    while sum(map(tokens, msgs)) > WINDOW:
        msgs.pop(0)
    return msgs

def clip(m, cap):
    w = m["text"].split()
    if m["role"] != "tool" or len(w) <= cap:
        return m
    mark = f"[... {len(w) - cap} tokens cut; call fetch_log(offset) for more ...]"
    return {**m, "text": " ".join(w[: cap // 2] + [mark] + w[-(cap // 2):])}

def truncate_safe(msgs, cap=2_000):
    msgs = [clip(m, cap) for m in msgs]
    while sum(map(tokens, msgs)) > WINDOW:
        msgs.remove(next(m for m in msgs if m["role"] != "system"))
    return msgs

kept = truncate_oldest(msgs)
assert not any(m["role"] == "system" for m in kept)
print(f"FAILURE: {sum(map(tokens, msgs))} tokens > {WINDOW}; system prompt evicted, {len(msgs) - len(kept)} messages dropped")
safe = truncate_safe(msgs)
assert safe[0]["role"] == "system" and len(safe) == len(msgs)
print(f"FIXED: system prompt kept, nothing evicted, {sum(map(tokens, safe))} tokens in the window")
```
The same code, with a third case where non-pinned messages flood the window, is in repro/CTX-03.py.

## Detection
Assert on the final request, after truncation and before the model call: `messages[0]` must hash to the known system prompt, or the call raises. Log `dropped_messages` and `dropped_tokens` per call and alert on any non-zero `dropped_tokens` for a run that has pinned content. Also log the largest single message as a share of the window (`max_msg_share`) and alert above 25 percent: that is the early warning, days before an eviction. If your provider returns prompt token usage, compare it with your own count of the kept messages; a large gap means your counter is wrong and your window is silently being exceeded or truncated downstream.

## The fix
Three changes, in order of importance. Pinned messages (system prompt, standing constraints) are never candidates for eviction; the eviction loop skips them and raises if pinned content alone does not fit. Every tool result is clipped at the adapter, before it enters history, to a per-tool token budget, keeping the head and the tail with an explicit marker and a pointer to the call that fetches the rest. And eviction, when still needed, removes the oldest unpinned messages, not the oldest messages. Capping the result is the structural part: trimming history to make room for an oversized message gives the one low-value item the space of many high-value ones.
```python
msgs = [clip(m, cap=2_000) for m in msgs]
```

## How it still bites
Head and tail clipping keeps the two ends of a log and throws away the middle, which is where a stack trace often is, so the agent now confidently diagnoses from the wrong 2,000 tokens. The pointer to fetch more costs a turn, and a model has to choose to use it; many will answer from what they have instead of paging.
