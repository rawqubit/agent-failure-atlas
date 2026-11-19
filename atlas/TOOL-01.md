---
id: TOOL-01
title: A renamed field upstream turns into a silent zero in the agent's answer
category: tool-use
severity: high
frequency: occasional
symptom: Agent confidently reports a total of $0.00 for orders that the upstream API shows as non-zero
stage: tool-execution
tags: schema-drift, tool-contracts, defaults
---

## What you see
Support starts getting "your assistant says my order was free" reports. The agent's answer reads "Order ord_77 total: $0.00" while the raw API response in the trace carries `"amount_cents": 4900`. No exception, no warning, no retry; every call returned 200 and the answer was formatted correctly.

## Why it happens
Upstream renamed `total_cents` to `amount_cents`. The tool description in the agent's prompt, which is a cached copy of the contract, still advertises the old name, and nothing ties the two together. The adapter then does `payload.get("total_cents", 0)`, which encodes the assumption that a missing key means zero. That is right for an optional counter and wrong for a required amount, and it has a worse property: zero is a valid-looking value, so neither the formatter nor the model can tell "the amount is zero" from "the field was not there". The model reports what it was given. The repro needs no model; the failure is complete before the model sees the value.

## Minimal reproduction
```python
ADVERTISED = {"required": ["id", "total_cents", "currency"]}
LIVE = {"id": "ord_77", "amount_cents": 4900, "currency": "usd"}

class SchemaDrift(Exception):
    pass

def total_lenient(payload):
    return payload.get("total_cents", 0)

def parse_strict(payload, schema):
    missing = [k for k in schema["required"] if k not in payload]
    unadvertised = [k for k in payload if k not in schema["required"]]
    if missing:
        raise SchemaDrift("missing %s, unadvertised %s" % (missing, unadvertised))
    return payload

answer = "Order %s total: $%.2f" % (LIVE["id"], total_lenient(LIVE) / 100)
assert answer.endswith("$0.00")
print("FAILURE: payload has amount_cents=4900, agent answers: %s" % answer)

try:
    parse_strict(LIVE, ADVERTISED)
except SchemaDrift as e:
    print("FIXED: strict parse fails closed: SchemaDrift(%s)" % e)
else:
    raise AssertionError("strict parse accepted a payload missing total_cents")
```
The fuller version, with the CI contract test and a unit-drift case, is in repro/TOOL-01.py.

## Detection
Hash the sorted key set of every tool response and log it as `payload_keyset`; alert the first time a hash appears that was not seen in the previous 7 days, per tool. In CI, run a contract test that calls each tool against a sandbox or recorded live sample and diffs its keys against the schema embedded in the prompt: `missing = advertised - live` and `unadvertised = live - advertised` must both be empty. Grep the adapters for `.get(` with a numeric default on any field the answer depends on.

## The fix
Required fields have no defaults. Parse tool responses into a typed structure where a missing required key raises an error naming the key, and have the adapter return that error to the model as a tool failure ("contract mismatch: total_cents missing"), so the agent says it cannot answer instead of reporting a zero. Generate the prompt's tool description from the same schema object the parser uses, so the repo cannot hold two versions. Instructing the model to "double-check suspicious totals" is a band-aid, since $0.00 looks plausible and the model never saw the real payload.
```python
missing = [k for k in schema["required"] if k not in payload]
if missing:
    raise SchemaDrift(missing)
```

## How it still bites
Shape checks do not see meaning: if upstream keeps `total_cents` but switches it to dollars, the repro shows 49.0 passing the strict parse and the agent reporting a wildly wrong total. Marking fields `Optional` "to be safe" in the schema quietly recreates the silent default, and validators that ignore unknown keys will never tell you that a new `refunded_cents` field exists that the answer should have included.
