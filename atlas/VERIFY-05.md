---
id: VERIFY-05
title: The success metric rewards length so the agent learns to be verbose
category: verification
severity: medium
frequency: occasional
symptom: The eval score rises release over release while answers get longer and reviewers report padding and wrong details
stage: evaluation
tags: metric-gaming, recall, length-bias
---

## What you see
Eval accuracy climbs from one prompt version to the next and mean answer length climbs with it, while users report configuration values in the long answers that are simply wrong. In the repro a concise answer with 4 correct claims scores recall 0.80, and a padded answer with 15 claims, 10 of them wrong, scores 1.00.

## Why it happens
A recall-style metric (the fraction of reference facts whose value appears in the answer) can only go up as text is added, because a value that is already present cannot be un-mentioned and a wrong claim is never examined. The assumption that breaks is that a higher score means more of the right things were said; the metric measures presence, not correctness or restraint. Listing every candidate value for every field then dominates any answer that commits, since padding costs tokens and knowing costs accuracy. Any optimizer finds this, whether it is RL, best-of-n, or someone iterating on a prompt against the dashboard. The repro uses `max` over two candidate answers as a stand-in for that optimization pressure, and assumes claim extraction for F1 is perfect.

## Minimal reproduction
```python
import re

FACTS = {"port": "8443", "timeout": "30s", "region": "eu-west-1", "retries": "3", "tls": "1.3"}
DECOYS = {"port": ["80", "9999"], "timeout": ["5s", "90s"], "region": ["us-east-1", "ap-south-1"],
          "retries": ["7", "12"], "tls": ["1.0", "1.1"]}

def text_of(claims):
    return "; ".join(f"{k} is {v}" for k, v in claims)

def recall_score(claims):
    tokens = set(re.findall(r"[\w.\-]+", text_of(claims)))
    return sum(v in tokens for v in FACTS.values()) / len(FACTS)

def f1_score(claims):
    right = {c for c in claims if FACTS[c[0]] == c[1]}
    p, r = len(right) / len(claims), len(right) / len(FACTS)
    return 2 * p * r / (p + r) if p + r else 0.0

concise = [(k, v) for k, v in FACTS.items() if k != "tls"]
padded = [(k, v) for k in FACTS for v in [FACTS[k]] + DECOYS[k]]
candidates = {"concise": concise, "padded": padded}

for name, claims in candidates.items():
    print("%-8s claims=%2d recall=%.2f f1=%.2f" % (name, len(claims), recall_score(claims), f1_score(claims)))
by_recall = max(candidates, key=lambda n: recall_score(candidates[n]))
by_f1 = max(candidates, key=lambda n: f1_score(candidates[n]))
print("FAILURE: recall picks %r (%d claims, %d wrong)" % (by_recall, len(padded), len(padded) - 5))
print("FIXED: F1 picks %r (%d claims, 0 wrong)" % (by_f1, len(concise)))
assert by_recall == "padded" and by_f1 == "concise"
```
The same code with the same assertions is in repro/VERIFY-05.py.

## Detection
Add a degenerate baseline to every eval run, one that emits every candidate value for every field, and assert in CI that its score is below the real system's: `assert score(dump_everything) < score(system)`. If it wins, the metric is gameable. Log output tokens next to the score, and gate releases on the score at equal length, for example by bucketing eval items by answer length and comparing within buckets, so a gain that only appears in the long bucket fails.

## The fix
Score claims, not mentions. Extract the claims in the answer, check each against the reference or the source, and report precision and recall together, with F1 as the gate. The padded answer in the repro drops from 1.00 to 0.50 F1 and the concise one rises to 0.89, so the ranking flips.
```python
p, r = len(right) / len(claims), len(right) / len(FACTS)
f1 = 2 * p * r / (p + r) if p + r else 0.0
```
A length penalty on the raw recall score is a worse fix: it trades padding for a tuned constant and still gives a wrong claim the same credit as a right one.

## How it still bites
Claim-level precision needs a reference that is complete, and references are not. A true claim missing from the reference counts as wrong, so the optimizer learns to say only what the reference lists, and answers get shorter and less useful. Report precision and recall as separate columns; an F1 that sits flat can hide a policy that has traded one for the other.
