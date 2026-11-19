---
id: TOOL-02
title: The model invents a plausible value for a required argument it does not have
category: tool-use
severity: critical
frequency: occasional
symptom: A mutating tool call succeeds on a record the user never mentioned, using an id that appears nowhere in the conversation
stage: model-call
tags: hallucinated-arguments, validation, identifiers
---

## What you see
A user writes "refund my last order" and the agent calls `refund(order_id="ord_1001")`. The call returns 200, the agent says "Done, your order has been refunded", and the customer who actually owns `ord_1001` writes in a day later. Searching the conversation for `ord_1001` finds it in no user message and no tool result; it appears only in the tool schema's example field.

## Why it happens
The schema says `order_id` is a required string matching `^ord_\d{4}$` and shows an example. The model has no order id, and the example is the only well-formed id in view, so a stub that copies it is the simplest model of what goes wrong. Schema validation passes because the value is well-formed, and the backend accepts it because it exists, so every layer that could object has checked the shape and none has checked the origin. Format validity says nothing about whether the value was ever given to the agent. The stub in the repro copies the example into the missing argument; it models that copy behaviour, and does not show how often real models do it.

## Minimal reproduction
```python
import re
ORDERS = {"ord_1001": {"owner": "cust_9"}, "ord_2044": {"owner": "cust_2"}}
EXAMPLE = "ord_1001"

def model_fill():
    return EXAMPLE

def validate(order_id):
    return re.match(r"^ord_\d{4}$", order_id) is not None

def refund_naive(order_id):
    assert validate(order_id)
    return ORDERS[order_id]["owner"]

class Session:
    def __init__(self, user):
        self.user, self.handles = user, {}
    def list_orders(self):
        for oid, o in ORDERS.items():
            if o["owner"] == self.user:
                self.handles["h%d" % (len(self.handles) + 1)] = oid
        return list(self.handles)
    def refund(self, handle):
        if handle not in self.handles:
            return "error: unknown handle, call list_orders or ask_user"
        return self.handles[handle]

owner = refund_naive(model_fill())
assert owner == "cust_9"
print("FAILURE: valid-looking id %r refunded an order owned by %s for caller cust_2" % (model_fill(), owner))
s = Session("cust_2")
reply = s.refund(model_fill())
assert reply.startswith("error")
print("FIXED: fabricated id rejected: %s" % reply)
assert s.refund(s.list_orders()[0]) == "ord_2044"
print("FIXED: handle from list_orders resolves to ord_2044, owned by the caller")
```
The fuller version, with the provenance check and the refund ledger, is in repro/TOOL-02.py.

## Detection
Add a provenance assertion at the tool boundary: for every id-typed argument, the exact string must occur in the user's messages or in an earlier tool result in the same run. Compute it in the trace pipeline as `unprovenanced_id_args` per tool and alert on any non-zero value for a mutating tool; the repro's check flags `ord_1001` because the conversation never contains it. A cheap test is to call each mutating tool with the user message stripped of ids and assert the model asks instead of calling.

## The fix
Make ids unforgeable by construction. Tools that return records return opaque handles (`h1`, `h2`) registered in the session, mutating tools accept only handles, and a handle not in the session registry is rejected with an error that names the recovery path. Give the model a first-class `ask_user` tool so that "I don't have this" has a legal move. Keep the data-layer ownership check as well: a handle could still be bound to a record the caller should not touch. Removing the example from the schema or adding "never guess ids" to the prompt is a band-aid: it lowers the rate without making an invented value impossible.
```python
def refund(self, handle):
    if handle not in self.handles:
        return "error: unknown handle, call list_orders or ask_user"
```

## How it still bites
Handles turn fabrication into selection: with ten valid handles and "refund my last order", the model picks one, every candidate passes every check, and it may pick the wrong one. For mutating calls, resolve "last" in a tool (`get_latest_order`) rather than in the model, and show the human-readable record in a confirmation step before the write.
