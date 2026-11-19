---
id: CTX-04
title: Append-only history makes every turn slower until the run hits the context limit
category: context
severity: medium
frequency: common
symptom: Per-turn latency climbs steadily through a long run, then the call fails with a context-length error although no single message was large
stage: context-assembly
tags: context-growth, latency, observation-masking, long-runs
---

## What you see
A run whose prefill took 0.1 seconds on turn 1 takes 8.5 seconds on turn 100, and at turn 118 the provider returns a context-length error. Each tool result was about 1,500 tokens and no single message was large, so nothing in the logs looks wrong; the only thing that changed is the `prompt_tokens` field, which grew by the same amount every turn.

## Why it happens
The loop assumes that history is free to keep: each turn appends the model's output and the tool result and sends the whole transcript again. Prefill cost is proportional to prompt length, so the per-turn cost of turn n is proportional to everything before it, and a run of n turns pays a growing price for the same early observations on every turn. In the repro, a turn adds 1,700 tokens, which is nothing, and yet the prompt crosses a 200,000-token window at turn 118. The run does not degrade gracefully at the end; it works at turn 117 and fails outright at turn 118. The observations are also stale in a way the transcript does not show: a directory listing from turn 6 has no value at turn 90, but it is priced like fresh evidence.

## Minimal reproduction
The token counts and the prefill rate (0.05 ms per token) are labelled constants, not measurements.
```python
LIMIT, SYSTEM, MODEL_OUT, TOOL_OUT, STUB, KEEP, MS_PER_TOKEN = 200_000, 2_000, 200, 1_500, 20, 5, 0.05

def prompt_tokens(n, mask):
    prior = n - 1
    kept = min(prior, KEEP) if mask else prior
    return SYSTEM + prior * MODEL_OUT + kept * TOOL_OUT + (prior - kept) * STUB

def first_overflow(mask, horizon=2000):
    return next((n for n in range(1, horizon + 1) if prompt_tokens(n, mask) > LIMIT), None)

dies = first_overflow(mask=False)
assert dies == 118
print(f"FAILURE: turn 1 prefill {prompt_tokens(1, False) * MS_PER_TOKEN:.0f} ms, turn 100 "
      f"{prompt_tokens(100, False) * MS_PER_TOKEN:.0f} ms, turn {dies} overflows {LIMIT} tokens")

assert first_overflow(mask=True, horizon=300) is None
print(f"FIXED: last {KEEP} results verbatim, older ones stubbed: turn 300 prompt = "
      f"{prompt_tokens(300, True)} tokens, overflow moves to turn {first_overflow(mask=True)}")
```
The same arithmetic, plus a pre-call budget check that fails by name, is in repro/CTX-04.py.

## Detection
Chart `prompt_tokens` against turn index for every run, and alert on slope: a run whose prompt grows by more than a fixed number of tokens per turn for ten consecutive turns is on the way to the limit, which gives you a warning many turns before the failure. Add a pre-call guard that raises `ContextBudgetExceeded` when the assembled prompt passes 80 percent of the window, so the failure carries a name, a turn number and a size instead of a provider error string. For latency, plot time-to-first-token against prompt tokens; a straight line confirms prefill is the cause and not the tools.

## The fix
Mask observations once they have been consumed. After the model has acted on a tool result, replace everything except the last K results with a one-line stub that names the tool, the arguments and the size, and tells the agent it can re-run the call. Enforce a token budget before every call, and make exceeding it trigger masking or compaction rather than an error. Masking is cheaper than summarizing the old results because it needs no model call and cannot invent anything. This is about the window and the latency; the bill is a different arithmetic, covered in COST-01, and a single oversized result is CTX-03.
```python
history = [stub(r) if r.age > K else r for r in history]
```

## How it still bites
Masking only flattens the slope: the masked run in the repro still overflows, at turn 868 instead of 118. Rewriting an old message also changes the prompt prefix at that position, so a prefix cache is invalidated from the first masked message onward (see COST-02); if you mask one result per turn, you pay full prefill every turn, so mask in batches and keep the prefix stable between them.
