---
id: TOOL-03
title: A tool returns an empty list on a swallowed error and the agent concludes the thing does not exist
category: tool-use
severity: high
frequency: common
symptom: Duplicate records created for customers that already exist, right after an auth or quota error that never appears in the agent trace
stage: tool-execution
tags: error-handling, empty-results, adapters, duplicates
---

## What you see
The agent runs `search_customers(email="ana@example.com")`, the span is green with `results: []`, and the next span is `create_customer` for the same email. The CRM now holds two Ana rows, and the damage shows up later, when notes and orders attach to different rows for the same person. The upstream access log, which the agent never sees, shows a 401 for the search call at the same timestamp, and the create call went to a different service with a different, still valid credential.

## Why it happens
A search has two ways to return nothing: the query matched zero rows, or the query never ran. The adapter that wraps the search client has a `try/except Exception: return []` that was added so a flaky index would not crash the loop, and it collapses both cases into one value. The agent's logic, in code or in the model's head, is "no results means absent, so create". That inference is only valid when emptiness is a fact about the world, and the adapter has made it a fact about the transport. The model cannot repair this: nothing in the string `[]` or "No results found" tells it which kind of empty it received, and it has no reason to doubt a tool that reported success.

## Minimal reproduction
```python
class CRM:
    def __init__(self, index_key):
        self.index_key = index_key
        self.rows = [{"id": 1, "email": "ana@example.com"}]
    def search(self, email):
        if self.index_key != "valid":
            raise PermissionError("401 index key revoked")
        return [r for r in self.rows if r["email"] == email]
    def create(self, email):
        self.rows.append({"id": len(self.rows) + 1, "email": email})

def search_swallow(crm, email):
    try:
        return {"results": crm.search(email)}
    except Exception:
        return {"results": []}

def search_strict(crm, email):
    try:
        return {"status": "ok", "results": crm.search(email)}
    except PermissionError as e:
        return {"status": "error", "error": str(e), "results": None}

def agent(crm, search, email):
    out = search(crm, email)
    if out.get("status") == "error":
        return "cannot verify: " + out["error"]
    if not out["results"]:
        crm.create(email)
        return "created"
    return "found existing"

crm = CRM("revoked")
verdict = agent(crm, search_swallow, "ana@example.com")
assert len(crm.rows) == 2
print("FAILURE: agent said", repr(verdict), "-> rows", [r["email"] for r in crm.rows])
crm = CRM("revoked")
verdict = agent(crm, search_strict, "ana@example.com")
assert len(crm.rows) == 1
print("FIXED:", verdict, "| rows:", len(crm.rows))
```
The fuller version in repro/TOOL-03.py adds the genuinely-empty case, which must still create, and an AST lint that finds the swallowing handler.

## Detection
Join tool spans with upstream access logs: any tool span with an empty result whose upstream request returned 401, 403, 429 or 5xx is a swallowed error, and the count should be zero. As a cheap early signal, chart the empty-result rate per tool; a step change to near 100% that lines up with a credential rotation or an upstream deploy is this bug. In CI, run every tool adapter against a fault-injecting client that raises on every call and assert the adapter output never equals its own empty-success shape. A lint that flags `except` handlers whose body returns a literal `[]`, `{}`, `None` or `""` catches the cause at review time; the repro does this with about ten lines of `ast`.

## The fix
Give the tool contract three outcomes, not two: `ok` with items (possibly zero), `error` with a typed reason, and optionally `partial`. The adapter may translate exceptions, but it never catches and returns a default. The loop treats `error` as "I do not know", which means no create, no "not found" in the final answer, and a surfaced failure or an escalation.
```python
except PermissionError as e:
    return {"status": "error", "error": str(e), "results": None}
```
Setting `results` to `None` instead of `[]` on error is deliberate: code that forgets to check `status` then fails with a TypeError rather than quietly treating the value as empty. Telling the model in the prompt to "double check before creating" is a band-aid, because the model sees the same `[]` the second time.

## How it still bites
Some upstreams produce the lie themselves: a search API with row-level security returns 200 and `[]` when the caller lacks permission on the matching rows, so there is no exception for the adapter to propagate and the typed contract has nothing to carry. The write path should therefore not rely on "search found nothing" at all; a unique constraint on email turns the duplicate create into a rejected call even when every read-side signal is wrong.
