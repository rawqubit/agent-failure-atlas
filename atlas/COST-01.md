---
id: COST-01
title: Resending the full history every turn makes total input tokens grow quadratically
category: economics
severity: high
frequency: common
symptom: Cost per run grows with the square of run length; a run twice as long costs about four times as much, and the invoice outruns usage growth
stage: billing
tags: token-cost, quadratic-growth, prompt-caching, context-growth
---

## What you see
Per-turn input tokens climb in a straight line through a run, and the cost per completed task climbs faster than the task count does. In the repro's model, a 60-turn run that adds 800 tokens per turn bills 1,464,000 input tokens, while the new content it produced was 48,000 tokens. Doubling the run to 120 turns bills 5,808,000, which is 3.97 times as much for twice the work. Finance sees a cost line that doesn't track tasks or users; engineering sees no error.

## Why it happens
A chat-completion call is stateless, so every turn resends everything so far. If turn k adds t tokens, turn n's input is n*t, and the run's total is t*n*(n+1)/2: for t=800 and n=60 that is 800 * 1830 = 1,464,000. Nothing in a single turn looks wrong, because each request is only as large as the history, which is within the context limit and grows by a modest amount. The assumption that breaks is that cost is proportional to new work. It is proportional to new work times the number of turns it has to be carried through, and long agent runs with large tool results maximize both. This is the bill; the same growth also hits the context limit and latency, which is CTX-04.

## Minimal reproduction
```python
PRICE, CACHED = 3.00, 0.10
SIZE = {"full": 800, "stub": 120, "sum": 500}

def run(n_turns, cache=False, stride=0, cap=0, keep=3):
    hist, prev, tokens, equiv = [], [], 0, 0.0
    for n in range(1, n_turns + 1):
        hist.append((n, "full"))
        if stride and n % stride == 0:
            hist = [(k, v if v != "full" or i >= len(hist) - keep else "stub") for i, (k, v) in enumerate(hist)]
        if cap and sum(SIZE[v] for _, v in hist) > cap:
            hist = [(n, "sum")] + hist[-keep:]
        size = [SIZE[v] for _, v in hist]
        hit = 0
        while cache and hit < min(len(prev), len(hist)) and prev[hit] == hist[hit]:
            hit += 1
        tokens += sum(size)
        equiv += CACHED * sum(size[:hit]) + sum(size[hit:])
        prev = list(hist)
    return tokens, equiv

naive, cost = run(60)
print("FAILURE: 60 turns bill %d input tokens ($%.2f) for %d tokens of new content" % (naive, cost * PRICE / 1e6, 60 * 800))
assert naive == 1_464_000 and run(120)[1] / cost > 3.9
_, fixed = run(60, cache=True, stride=10, cap=6000)
ratio = run(120, cache=True, stride=10, cap=6000)[1] / fixed
print("FIXED: masking + cap + cache bills %d token-equivalents ($%.2f); doubling turns costs %.2fx" % (fixed, fixed * PRICE / 1e6, ratio))
assert fixed < cost / 10 and ratio < 2.1
```
PRICE is a labelled USD-per-million-tokens constant and CACHED is an assumed discount on cached tokens; neither is any provider's rate. repro/COST-01.py prints the intermediate cases.

## Detection
Compute `input_tokens` per turn from the usage field on every response and plot it against the turn index; a straight rising line is the signature, and the area under it is the bill. Alert on cost per completed task, not on total spend, with the run length attached: if p95 cost per task rises while task mix is constant, the long tail of run lengths is what moved. A direct test is to run the same scripted task at n and 2n turns and assert that the token ratio is below a bound you chose, such as 2.5; the unmitigated ratio is about 4. Log `cached_tokens / input_tokens` too, because a cache you think you have and do not is a separate cause of the same invoice (COST-02).

## The fix
Bound the context that is resent. The repro combines three things, and the order of importance is not the one most teams expect.
1. A cap that compacts when the prompt crosses a budget is what changes the growth from quadratic to linear: with it, doubling the turns costs 2.03 times, and without it a cache alone leaves 3.52 times.
2. A prefix cache cuts the constant: the uncapped 60-turn run drops from 1,464,000 to 189,600 token-equivalents at the assumed 0.10 factor, which is 7.7 times, but the curve stays quadratic.
3. Masking old tool results with stubs shrinks each entry, and it should be done in batches (every 10 turns in the repro), because masking an entry rewrites bytes inside the cached prefix. Masking on every turn leaves the 60-turn cost at 165,432, only 13% below the cache alone; masking every 10 turns gives 108,720 before the cap, and 97,320 with it.
```python
if prompt_tokens > BUDGET:
    history = [summary(history[:-KEEP])] + history[-KEEP:]
```
Telling the model to "be concise" trims the t, not the n, so it moves the constant at best.

## How it still bites
Every compaction and every masking pass changes the prefix, so the cache hit rate sawtooths and the cheapest-looking policy on paper bills more than expected when passes run often; measure cached-token share per turn after you add masking, not before. Masking and summarizing also destroy information the model may need 20 turns later, so the saving is purchased with a quality risk that no cost dashboard shows (see CTX-02 for what a lossy compaction drops).
