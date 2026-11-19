# Entry template

Copy this into atlas/<ID>.md and create repro/<ID>.py. Run `python3 check.py --ids <ID>` until it passes, then `python3 check.py --assemble`.

Prefixes and ranges: PLAN, TOOL, CTX, MEM, VERIFY, SEC, OPS, COST. A new entry takes the next free number in its category. Update the category range in check.py (the CATEGORIES table) and the entry-count check in the same pull request, and add the README index row.

## File skeleton

```
---
id: CTX-NN
title: One sentence that names the failure, not the topic
category: context
severity: high
frequency: occasional
symptom: What the on-call sees, in one line
stage: context-assembly
tags: two, to, five, lowercase, tags
---

## What you see
## Why it happens
## Minimal reproduction
## Detection
## The fix
## How it still bites
```

Front matter rules: keys exactly as shown and in that order, one line each, no nested values, no emoji. severity is critical, high, or medium. frequency is common, occasional, or rare. category is the slug from docs/taxonomy.md.

## Section rules

- **What you see**: 2-4 sentences of concrete log lines, numbers, user-visible effects.
- **Why it happens**: 3-6 sentences. The mechanism and the exact assumption that breaks. No blame.
- **Minimal reproduction**: one fenced python block of at most 40 lines that runs on its own, followed by one sentence pointing at repro/<ID>.py.
- **Detection**: a metric, query, log pattern, assertion, or test. Name the signal.
- **The fix**: the smallest correct change. Prefer the structural fix and say why the prompt version is weaker.
- **How it still bites**: 1-3 sentences on the residual risk after the fix.

## Repro rules

- Python 3.9+, standard library only, offline, deterministic, under 5 seconds, exit code 0.
- Print a line starting with FAILURE showing the failure with numbers, then a line starting with FIXED showing the fix working. Use assert so the script fails if the mechanism is not demonstrated.
- If the real failure needs a model, stub it and state in the entry what the stub assumes. A stub models a measured property; it does not prove anything about a specific real model.
- Never read an API key. Never touch the network. Write files only inside a temporary directory.

## Evidence rules

Numbers in an entry come from the repro or from arithmetic the entry shows. Do not describe a real incident unless you can cite it in docs/citations.md with a link and a one-line note.
