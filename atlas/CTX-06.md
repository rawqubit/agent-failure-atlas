---
id: CTX-06
title: A rolling summary keeps a fact as current long after it stopped being true
category: context
severity: high
frequency: occasional
symptom: The agent acts on a value that was corrected many turns ago, and the summary it was working from contains only the old value
stage: context-assembly
tags: summarization, stale-facts, provenance, rolling-summary
---

## What you see
At turn 60 the user says the deploy branch is now `release-5`. At turn 70 the agent pushes to `release-4`. The summary block in the prompt reads "deploy branch = release-4", it has been re-generated seven times since turn 3, and nothing in it says when the value was observed or that it was ever contested.

## Why it happens
A rolling summary is rewritten from the previous summary plus the newest turns, so older lines are treated as established and each new turn is only a candidate for inclusion. A concise summarizer is also asked not to repeat itself: when a new message talks about a topic the summary already covers, the new message reads as redundant and is skipped. The correction therefore loses to the old line for a structural reason, not a random one, since it is the newer evidence that gets filtered. The facts are plain strings, so there is no timestamp, source or key from which anyone could tell which of two lines about the deploy branch wins. Repeated regeneration also launders the claim: by the seventh pass the old value has no visible origin and reads like ground truth.

## Minimal reproduction
The summarizer is a stub that carries the previous summary forward and skips a new statement about a topic the summary already covers; the extractor is the same regex in both variants.
```python
import re

FACT = re.compile(r"the (deploy branch) is (?:now )?(release-\d+)")
turns = [(t, "ran the tests, nothing to report") for t in range(1, 71)]
turns[2] = (3, "the deploy branch is release-4")
turns[59] = (60, "heads up, the deploy branch is now release-5")

def extract(text):
    m = FACT.search(text)
    return (m.group(1), m.group(2)) if m else None

def roll(prev, window):
    out = list(prev)
    for turn, text in window:
        fact = extract(text)
        if fact and not any(fact[0] in line for line in out):
            out.append(f"{fact[0]} = {fact[1]}")
    return out

summary = []
for i in range(0, 70, 10):
    summary = roll(summary, turns[i : i + 10])
assert summary == ["deploy branch = release-4"]
print("FAILURE: after 7 rolls the summary says", summary[0], "but turn 60 said release-5")

ledger = {}
for turn, text in turns:
    fact = extract(text)
    if fact and (fact[0] not in ledger or turn > ledger[fact[0]][1]):
        ledger[fact[0]] = (fact[1], turn, "2026-11-19")
summary = [f"{k} = {v} (turn {t}, observed {o})" for k, (v, t, o) in ledger.items()]
assert summary == ["deploy branch = release-5 (turn 60, observed 2026-11-19)"]
print("FIXED: ledger keyed by fact, newer turn replaces older:", summary[0])
```
The same code, with the ledger also fed in reverse order, is in repro/CTX-06.py.

## Detection
Write a regression test for supersession: feed a synthetic transcript that states a fact, adds fifty turns of noise, then corrects the fact, run your real summarizer, and assert the summary contains the new value and not the old. Run it on every change to the summarizer prompt or model. In production, log each fact's `age_turns` when it is rendered into a prompt and alert when a fact older than your threshold is used as the argument of a side-effecting tool call; a branch name that is 67 turns old and goes into `git push` deserves a re-check.

## The fix
Stop summarizing summaries. Keep a fact ledger where each entry is `(key, value, source_turn, observed_at)`; a new observation of the same key replaces the old one only if its source turn is later, and the prompt's summary block is rendered from the ledger on every call. The previous summary is then an output, never an input, so errors cannot compound across passes. Rendering the provenance, "(turn 60, observed 2026-11-19)", lets the model and a human judge freshness, which a bare string never can. This differs from CTX-02, where a fact vanishes: here the wrong fact stays and looks current.

## How it still bites
The ledger needs the same key for the same fact, and an extractor model will call it "deploy branch" in one turn and "release branch" or "branch we ship from" in the next, so supersession silently fails and two live entries coexist. It also only knows what was said: a value that changed in the world without anyone mentioning it stays "current" forever, which is the persistent-store version of the problem, handled with write preconditions in MEM-05.
