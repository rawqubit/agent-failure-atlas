---
id: TOOL-08
title: A batch tool returns top-level ok while 3 of 10 items failed and the agent reports full success
category: tool-use
severity: high
frequency: common
symptom: The agent reports all records updated; a later reader finds a fraction of them unchanged, with no error anywhere in the run
stage: tool-execution
tags: batch-apis, partial-failure, adapters, status-codes
---

## What you see
`bulk_update` returns HTTP 200 and `{"status": "ok", "results": [...]}`. The agent says "updated 10 of 10 records". Inside `results`, ids 3, 6 and 9 carry `status: 409` because those rows were locked by another job, so 7 were changed and 3 were not. The first sign is a customer or a downstream report that still shows the old values.

## Why it happens
The tool is not lying. A batch endpoint has two layers of status: the request layer ("I parsed it and processed it") and the item layer ("this row was applied"); the top-level `ok` answers the first question and the item statuses answer the second. The adapter, or the model reading raw JSON, checks the field that is easiest to find, and the count it reports is the length of `results`, which is the number of items processed, not the number applied. The broken assumption is that one boolean can summarize a collection. The same trap lives in HTTP 207 multi-status responses and in cloud APIs that return a 200 with a `failures` array that is easy to skip. It differs from TOOL-03: there the tool hid the error, here the tool reported it and the consumer did not read it.

## Minimal reproduction
```python
class PartialSuccess(Exception):
    def __init__(self, succeeded, failed):
        super().__init__("failed: %s" % failed)
        self.succeeded, self.failed = succeeded, failed

def bulk_update(ids, locked):
    return {"status": "ok", "results": [{"id": i, "status": 409 if i in locked else 200} for i in ids]}

def naive_adapter(resp):
    return {"updated": len(resp["results"])} if resp["status"] == "ok" else {"updated": 0}

def strict_adapter(resp):
    ok = [r["id"] for r in resp["results"] if 200 <= r["status"] < 300]
    bad = [r["id"] for r in resp["results"] if not 200 <= r["status"] < 300]
    if bad:
        raise PartialSuccess(ok, bad)
    return {"updated": len(ok)}

def agent(adapter, resp, total):
    try:
        return "updated %d of %d" % (adapter(resp)["updated"], total)
    except PartialSuccess as e:
        return "updated %d of %d; failed ids %s" % (len(e.succeeded), total, e.failed)

ids = list(range(1, 11))
resp = bulk_update(ids, locked={3, 6, 9})
said = agent(naive_adapter, resp, len(ids))
assert said == "updated 10 of 10"
print("FAILURE: top-level", resp["status"], "-> agent reported:", said, "| applied:", sum(r["status"] == 200 for r in resp["results"]))
said = agent(strict_adapter, resp, len(ids))
assert "failed ids [3, 6, 9]" in said
print("FIXED:", said)
```
The full version in repro/TOOL-08.py also checks that a clean batch still reports 10 of 10.

## Detection
For every batch tool, assert in tests that the adapter's reported success count equals the number of items whose own status is in the success range, using a fixture where some items fail; the repro's `10 of 10` against 7 applied is exactly the case that test catches. In production, log `items_total`, `items_ok` and `items_failed` on every batch span and alert on `items_failed > 0` together with a final message that contains no failure language. A read-back check is the independent signal: after a bulk write, sample a few ids and compare against the intended value, and treat any mismatch as an incident regardless of what the response said.

## The fix
Reduce the per-item results to a ledger inside the adapter, before anything reaches the model, and make a mixed outcome an exception. The agent receives either a clean success or a `PartialSuccess` that carries the succeeded and failed ids, and it must handle that branch explicitly: retry only the failed ids, skip them with a stated reason, or report the split.
```python
if bad:
    raise PartialSuccess(ok, bad)
```
Doing this in the adapter matters because it removes the choice: a prompt instruction to "check each item" asks the model to do a loop over an array that it may only skim, while a typed exception cannot be skimmed.

## How it still bites
The failed ids need a path that does not loop: a 409 from a lock may clear in a minute, but a 422 for invalid data never will, so a retry-the-failed branch that does not classify failures turns this into PLAN-01. Large batches add a second residual: with thousands of items the failed-id list is too large to hand to the model, so the ledger has to live in storage and the model gets a count plus a handle to page through it.
