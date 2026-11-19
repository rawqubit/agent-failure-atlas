---
id: MEM-04
title: A response cache keyed by prompt text alone serves tenant A's answer to tenant B
category: memory
severity: critical
frequency: occasional
symptom: A user sees another tenant's numbers, policy or document contents in an answer, and the model call count for that request is zero
stage: model-call
tags: caching, multi-tenancy, data-leak, access-control
---

## What you see
Two customers ask the same question, "refund policy", on the same afternoon. The second one is told "Refunds within 30 days", which is the first customer's policy; the second customer's own document says 14 days. The trace for the second request shows a cache hit and no retrieval span, so nothing in the logs looks like an authorization failure. In the repro, the leaked answer is byte-for-byte what the other tenant received.

## Why it happens
A response cache sits in front of the whole agent to save model calls, and its key is the text of the user's request because that is the only thing the cache layer sees. The answer, though, is a function of the request plus the data the agent retrieved on that user's behalf, which differs per tenant and per user. The assumption that breaks is that the question determines the answer. Retrieval, tool calls and permission filters all run after the key is computed, so a hit skips every access check the miss path would have applied. Prompt-level instructions such as "only use the current tenant's documents" cannot help, since on a hit the model is never invoked.

## Minimal reproduction
```python
import hashlib

POLICY = {"acme": "Refunds within 30 days.", "globex": "Refunds within 14 days."}

def key_prompt_only(tenant, question):
    return hashlib.sha256(question.encode()).hexdigest()

def key_scoped(tenant, question):
    return hashlib.sha256(f"{tenant}\x1f{question}".encode()).hexdigest()

def run(key_fn):
    cache = {}
    def ask(tenant, question):
        k = key_fn(tenant, question)
        if k not in cache:
            cache[k] = "Answer: " + POLICY[tenant]
        return cache[k]
    ask("acme", "refund policy")
    return ask("globex", "refund policy")

leak = run(key_prompt_only)
print("FAILURE: globex was told", repr(leak), "expected 14 days:", "14 days" in leak)
ok = run(key_scoped)
print("FIXED: globex was told", repr(ok))
assert "30 days" in leak and "14 days" in ok

tenants = ["acme", "globex", "initech"]
keys = {key_scoped(t, "refund policy") for t in tenants}
assert len(keys) == len(tenants)
print("FIXED: key-collision test, %d tenants -> %d distinct keys" % (len(tenants), len(keys)))
```
repro/MEM-04.py adds a user-level permission case inside one tenant, with a managers-only document, and the collision test over every principal and question.

## Detection
Write a collision test as part of the cache's unit tests: enumerate every (tenant, user role) pair you have in fixtures against a set of questions, compute each key, and assert no key is produced by principals in different tenants. In production, log the tenant id in the cache-hit span and the tenant id stored with the entry at write time; a hit where the two differ is a leak and should page, and a cache that stores no tenant on the entry cannot be audited at all. Run a canary: two synthetic tenants with distinct sentinel strings, asking the same question every few minutes, alert if either ever sees the other's sentinel.

## The fix
Build the key from everything the answer depends on: tenant id, the hash of the requesting principal's permission set, and the prompt. Better, compute the key after retrieval from the ids and versions of the documents actually fetched, so a document edit also invalidates the entry. Enforce tenant isolation in the data layer (per-tenant index or row-level filter) so a cache bug cannot widen access beyond what the miss path allows; the cache is an optimization and must not be the only place the rule exists. Scoping the key by hand is the structural part, because a prompt-level rule never runs on a hit.
```python
key = sha256("\x1f".join([tenant_id, acl_fingerprint(principal), prompt]).encode()).hexdigest()
```

## How it still bites
A tenant-scoped key is not enough when permissions vary inside the tenant: in the repro, with the key scoped to the tenant only, an employee receives the managers-only salary band that a manager's earlier question cached, so the key needs the principal's permission fingerprint and not just the tenant. Semantic caches that look up by embedding similarity have no exact key to scope, so the tenant and permission filter must be applied inside the nearest-neighbour search, not on the best match afterwards.
