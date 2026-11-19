---
id: MEM-02
title: A keyword-stuffed document wins retrieval for every query and displaces the correct answer
category: memory
severity: high
frequency: occasional
symptom: One document id appears as the top hit for unrelated queries and the answers cite it while the right runbook is never retrieved
stage: context-assembly
tags: retrieval, ranking, hubs, lexical-search
---

## What you see
Retrieval logs show one document id as rank 1 for queries about API keys, password resets, CSV exports and webhooks alike. In the repro, a single "glossary" document wins 8 of 8 unrelated queries, and the agent answers each from it with confident, off-topic text. The correct page is still in the index and still scores well on its own; it is just always second.

## Why it happens
A lexical scorer that sums term counts (or a tf-idf variant with no document-length normalization) rewards a document for every query term it contains and for every repetition. A document that lists the vocabulary of the whole corpus, whether an attacker wrote it, or a generated "tags" page, a changelog, or an auto-built glossary produced it, contains the terms of every query, so it collects a score for each. The assumption that breaks is that a high score means the document is about the query; the score only measures term coverage. Each correct document covers only its own topic, so it can never beat a document that covers all topics at once. The failure is about rank, not obedience: the stuffed document need not contain any instruction (contrast SEC-01); it just occupies the slot that the right evidence needed.

## Minimal reproduction
```python
import math
from collections import Counter

docs = {"rotate-key": "how to rotate the api key for billing",
        "reset-pass": "reset a user password from the admin console",
        "export-csv": "export invoices as csv from the reports page",
        "set-hook": "configure a webhook endpoint for payment events"}
queries = {"rotate-key": "rotate api key billing", "reset-pass": "reset user password admin",
           "export-csv": "export invoices csv reports", "set-hook": "webhook endpoint payment events"}
terms = sorted({t for q in queries.values() for t in q.split()})
docs["stuffed"] = " ".join(terms * 4)

def raw(q, d):
    c = Counter(d.split())
    return sum(c[t] for t in set(q.split()))

def cosine(q, d):
    c, qc = Counter(d.split()), Counter(set(q.split()))
    dot = sum(c[t] * w for t, w in qc.items())
    return dot / (math.sqrt(sum(v * v for v in c.values())) * math.sqrt(len(qc)))

for name, score in (("raw count", raw), ("cosine", cosine)):
    wins = [max(docs, key=lambda k: score(q, docs[k])) for q in queries.values()]
    n = wins.count("stuffed")
    print(("FAILURE:" if n else "FIXED:"), name, "ranks the stuffed doc first for", n, "of", len(queries))
```
The scorer is lexical; I did not test dense retrievers here, so this is a statement about term-count ranking only. repro/MEM-02.py runs 8 queries, adds a hub detector over the query log, and shows the cost of normalization.

## Detection
Compute, per document id, the share of logged queries for which it is rank 1 (or in the top 3) over a rolling window; a document above a fixed share such as 50% of top-1s, given a diverse query mix, is a hub and goes to a review queue. Log the score margin between rank 1 and rank 2; hubs show a large margin on queries whose titles do not mention the document. Add a canary test: index a document built from every term in your test queries and assert it is not top-1 for any of them.

## The fix
Normalize for document length in the scorer (the repro uses cosine over term vectors; I did not test BM25 variants) so covering many topics dilutes the score instead of adding to it; in the repro this moves the stuffed document from 8 of 8 wins to none. Add trust tiers by source so a document from an unreviewed or user-writable source cannot outrank a curated one on score alone, and quarantine documents the hub detector flags until someone reads them. Length normalization is the structural part; the hub detector is the backstop for documents that find another way to look relevant.
```python
hubs = {d for d, n in Counter(top1_log).items() if n / len(top1_log) > 0.5}
index.quarantine(hubs)
```

## How it still bites
Length normalization penalizes legitimate long documents: in the repro a 3-word stub scores 0.87 for "rotate api key billing" while the real 430-word runbook that contains the answer scores 0.01, so the fix shifts the failure from stuffed pages to thin ones. Index passages (chunks), not whole documents, and normalize within the chunk. A hub detector also has a blind spot for narrow stuffing: a document stuffed with the terms of one high-value query is a hub for one query, and the global share stays under the threshold.
