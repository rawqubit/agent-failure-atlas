---
id: COST-02
title: A timestamp at the top of the system prompt defeats the prefix cache on every request
category: economics
severity: medium
frequency: common
symptom: Cached-token share is near zero despite a system prompt and tool list that have not changed, so every request pays full input price and full prefill
stage: billing
tags: prompt-caching, prefix-cache, cost, tool-ordering
---

## What you see
The usage block on every response reports zero cached input tokens. The system prompt and tool list are byte-for-byte what you shipped, nothing errors, and the prompt-caching feature is enabled in config. In the repro, a request stream where the first token is a timestamp hits 0.0% of cache blocks over 20 requests, and the same prompt with static content first hits 93.1%, a gap that shows up as a higher invoice and longer prefill, with no functional symptom.

## Why it happens
A prefix cache can only reuse a stretch of the prompt that is identical from the very first token. Implementations typically key each block of tokens by a hash of that block together with every block before it, so one changed byte in block 0 changes the key of every later block, however static the rest is. The assumption that breaks is that "mostly the same prompt" is mostly cached. It is cached up to the first difference and not after it. Anything that varies per request and sits early in the prompt acts as that first difference: a "current time" line, a request or session id, a user name, or a tool list assembled from a set or a concurrently populated registry whose iteration order differs from one process or request to the next.

## Minimal reproduction
```python
import hashlib, random

BLOCK = 16
SYSTEM = ["rule%d" % i for i in range(400)]
TOOLS = {"tool%02d" % i: ["arg%d_%d" % (i, j) for j in range(40)] for i in range(12)}

def build(n, volatile_first, names):
    stamp = ["now=2026-11-19T10:00:%02dZ" % n]
    tools = [w for name in names for w in [name] + TOOLS[name]]
    history = ["turn%d_word%d" % (k, j) for k in range(n) for j in range(60)]
    body = SYSTEM + tools + history
    return stamp + body if volatile_first else body + stamp

def hit_rate(prompts):
    seen, hits, total = set(), 0, 0
    for words in prompts:
        h, run, missed = "", 0, False
        for b in range(len(words) // BLOCK):
            h = hashlib.sha256((h + " ".join(words[b * BLOCK:(b + 1) * BLOCK])).encode()).hexdigest()
            run, missed = (run + 1, missed) if not missed and h in seen else (run, True)
            seen.add(h)
        hits, total = hits + run, total + len(words) // BLOCK
    return hits / total

N, rng = range(1, 21), random.Random(7)
lead = hit_rate([build(n, True, sorted(TOOLS)) for n in N])
shuffled = hit_rate([build(n, False, rng.sample(sorted(TOOLS), 12)) for n in N])
assert lead == 0.0 and shuffled < 0.35
print("FAILURE: leading timestamp %.1f%% hits; unstable tool order %.1f%%" % (100 * lead, 100 * shuffled))
fixed = hit_rate([build(n, False, sorted(TOOLS)) for n in N])
assert fixed > 0.9
print("FIXED: static first, tools sorted, timestamp last: %.1f%% hits" % (100 * fixed))
```
The cache is a simulator with 16-word blocks and chained block hashes; it models exact-prefix matching and nothing about any provider's real block size or retention. The fuller version is repro/COST-02.py.

## Detection
Read the cached-token count the provider returns on each response and chart `cached_tokens / input_tokens` per prompt template; a healthy templated agent sits high after warmup, and a flat line near zero is this bug. Add a CI test that renders the prompt twice with different timestamps, ids and tool-registry insertion orders, finds the first index where the two strings differ, and fails if that index is earlier than the start of the dynamic section. The same test with the diff index printed names the offending field. A hash of the first N tokens of the rendered prompt, logged per request, should have very few distinct values per template; a distinct value per request is the volatile prefix.

## The fix
Render the prompt in order of volatility: system instructions, then tool definitions in a canonical order, then conversation history that only ever appends, then the per-request values last, ideally inside the final user turn. Sort tool lists and serialize any dict with sorted keys, so two processes produce the same bytes from the same data.
```python
tools = sorted(registry.values(), key=lambda t: t.name)
messages = [system, *history, user_turn_with_clock(now)]
```
Reordering is structural and permanent, while a note to engineers saying "do not put dynamic text at the top" is gone by the next template edit; the CI test above is what holds the line.

## How it still bites
Coarse values only move the problem: a date-only header at the top hits 88.2% overall in the repro, but the first request after the date rolls over hits 0%, so every long-lived template takes a full-price prefill spike at the same moment, at the same moment for every tenant that shares the template. Appending the time at the end also fails if a later step re-renders earlier turns with a fresh value, because the edit lands inside the cached region and the damage is the same as a timestamp at the top.
