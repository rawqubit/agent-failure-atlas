---
id: VERIFY-03
title: Eval examples leak into the prompt and inflate the score
category: verification
severity: medium
frequency: common
symptom: The eval score jumps to near-perfect after a prompt or retrieval change, and live quality does not move
stage: evaluation
tags: contamination, eval-leakage, few-shot
---

## What you see
A change that adds retrieved few-shot examples takes the benchmark to 100% on 50 items, while the production success rate is unchanged. In the repro the contaminated run scores 100%, and the same pipeline on a split made before prompt construction scores 48% on 54 held-out items, which is a coin flip because the labels are random.

## Why it happens
Retrieved few-shot is a nearest-neighbour lookup over labelled examples. If the eval items are in the exemplar pool, the nearest neighbour of each eval item is that item with its label attached, and copying from context is exactly what models do reliably. The assumption that breaks is that prompt assets and eval items are disjoint, and nothing enforces it: both are exports of the same labelled table, someone pastes a failing eval case into the prompt to fix it, or a pool built from production logs contains items that were later sampled into the eval. The stub here copies the label of an exemplar that shares at least 10 of 12 words with the item and otherwise guesses from text length; it models a model that has the answer in context and says nothing about how real models behave without it.

## Minimal reproduction
```python
import hashlib

def h(*parts):
    return int(hashlib.md5("-".join(map(str, parts)).encode()).hexdigest(), 16)

POOL = [{"id": i, "text": " ".join("w%d" % (h(i, k) % 400) for k in range(12)), "label": h(i, "y") % 2} for i in range(200)]

def overlap(a, b):
    return len(set(a.split()) & set(b.split()))

def accuracy(exemplars, eval_set):
    hits = 0
    for item in eval_set:
        top = max(exemplars, key=lambda ex: overlap(ex["text"], item["text"]))
        pred = top["label"] if overlap(top["text"], item["text"]) >= 10 else len(item["text"]) % 2
        hits += pred == item["label"]
    return hits / len(eval_set)

def ngrams(text, n=8):
    w = text.split()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}

def flagged(exemplars, eval_set):
    seen = set().union(*(ngrams(ex["text"]) for ex in exemplars))
    return sum(bool(ngrams(item["text"]) & seen) for item in eval_set)

dirty_eval = POOL[:50]
train = [x for x in POOL if h(x["id"], "split") % 4]
clean_eval = [x for x in POOL if not h(x["id"], "split") % 4]
print("FAILURE: contaminated eval scores %.0f%%, detector flags %d/%d" % (100 * accuracy(POOL, dirty_eval), flagged(POOL, dirty_eval), len(dirty_eval)))
print("FIXED: hash split scores %.0f%%, detector flags %d/%d" % (100 * accuracy(train, clean_eval), flagged(train, clean_eval), len(clean_eval)))
assert accuracy(POOL, dirty_eval) == 1.0 and flagged(POOL, dirty_eval) == len(dirty_eval)
assert accuracy(train, clean_eval) < 0.7 and flagged(train, clean_eval) == 0
```
The same code with the same assertions is in repro/VERIFY-03.py.

## Detection
Add a CI step that computes word 8-grams for every prompt asset (system prompt, static exemplars, the retrieval index's documents) and for every eval item, and fails on any shared 8-gram or any shared item id. In the repro it flags 50 of 50 contaminated items and 0 of 54 clean ones. Separately, keep a small fresh sample of live traffic and alert when `eval_score - fresh_sample_score` grows after a prompt change, because a rising gap is what leakage looks like from outside.

## The fix
Assign every item to a split by hashing a stable id before any prompt is built, and let exemplar retrieval read only the train partition. The split must be a pure function of the id so that it does not change when the dataset grows.
```python
def is_eval(item_id):
    return int(hashlib.md5(item_id.encode()).hexdigest(), 16) % 4 == 0

exemplar_pool = [x for x in items if not is_eval(x["id"])]
```
The overlap check in CI then acts as the guard that the rule is actually followed; a note in the README asking people not to paste eval items into prompts is not.

## How it still bites
Splitting by item id puts near-duplicates on both sides of the line, such as two tickets from the same customer or one template with different numbers, and an 8-gram check will not flag them. Split by a group key (customer, document, thread) instead of the item. Retrieval indexes that refresh from production logs can also pull in eval items after CI has passed, so run the overlap check against the live index on a schedule.
