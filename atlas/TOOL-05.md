---
id: TOOL-05
title: A tool timeout is treated as failure while the original call is still running and completes
category: tool-use
severity: high
frequency: common
symptom: A customer is refunded to the card and also given store credit; the trace shows one failed call and one successful fallback
stage: tool-execution
tags: timeouts, unknown-outcome, fallback, orphaned-work
---

## What you see
The trace has `refund_to_card` ending in a client-side timeout, followed by `issue_store_credit` returning 200, and the agent tells the customer "the card refund failed, so I credited your account". Some time later the gateway's own log shows `refund committed` for the same order. The ledger holds a 50.00 card refund and a 50.00 credit for one 50.00 order, and the retry-safety work from TOOL-04 does not help because the agent never retried the call.

## Why it happens
A client timeout is a statement about the client's patience, not about the server's state. The tool wrapper collapses three different situations into one exception: the work never started, the work is still running, and the work finished but the response was lost. The agent's fallback logic assumes the first, that a timeout means the primary path did not happen, so taking a different path is safe. Abandoning the wait does not cancel anything: the worker has no idea the client left, and when it reaches its commit point the primary effect lands next to the fallback's effect. The model reinforces the error because the tool result it sees is `failed`, and a plan that says "if refund fails, issue credit" is the obvious thing to follow.

## Minimal reproduction
```python
class Gateway:
    def __init__(self, commit_at, respond_at):
        self.t, self.commit_at, self.respond_at = 0, commit_at, respond_at
        self.state, self.ledger = "pending", []
    def tick(self, n):
        for _ in range(n):
            self.t += 1
            if self.state == "pending" and self.t == self.commit_at:
                self.state = "done"
                self.ledger.append("card refund 50")
    def cancel(self):
        if self.state == "pending":
            self.state = "cancelled"
        return self.state

def handle(gw, safe, timeout=3):
    gw.tick(timeout)
    if gw.t >= gw.respond_at:
        return
    if safe and gw.cancel() == "done":
        return
    gw.ledger.append("store credit 50")

def run(commit_at, respond_at, safe):
    gw = Gateway(commit_at, respond_at)
    handle(gw, safe)
    gw.tick(10)
    return gw.ledger

for name, c, r in [("slow worker", 5, 5), ("lost response", 2, 6)]:
    ledger = run(c, r, safe=False)
    assert len(ledger) == 2
    print("FAILURE:", name, "-> naive timeout ledger:", ledger)
    ledger = run(c, r, safe=True)
    assert len(ledger) == 1
    print("FIXED:", name, "-> status check first, ledger:", ledger)
```
The clock is a tick counter, so there are no threads and no race; repro/TOOL-05.py prints the verdict string for each case as well.

## Detection
Reconcile by business key, not by call: a nightly query for orders with more than one entry across `refund` and `credit` ledger tables whose sum exceeds the order total catches the outcome. In traces, flag any run where a tool span ended with a client-side timeout and a different mutating tool ran afterwards in the same trace without an intervening status or get call for the original operation id. In tests, build a gateway fake with two knobs, the tick where it commits and the tick where the response becomes readable, and assert the ledger holds exactly one effect for every combination of the two; the repro's two cases are the corners of that grid.

## The fix
A timeout means the outcome is unknown, and the code path for unknown is different from the one for failure. The operation gets an id before the first byte is sent (client-generated, so it exists even when the response never arrives). After a timeout the adapter asks for the operation's status; if it is terminal, act on that. If it is still pending, send a cancel and act only on the cancel's confirmed state. If the status is still unknown after that, escalate to a human or park the task, because a fallback is a bet on an answer you do not have.
```python
state = gw.cancel()          # returns the state it ended in
if state == "done":          # it committed before we could stop it
    return "refunded"
```
Putting "check before falling back" in the prompt is weaker than putting it in the adapter: the model has no status tool unless you build one, and a timeout error that reads like a failure invites the wrong branch.

## How it still bites
The cancel is itself a request that can time out, so the fix needs the same unknown-outcome handling one level down, and a gateway with no cancel endpoint or no per-operation status leaves you able to wait, not to decide. The sharper case is a primary operation with a commit point that cannot be cancelled once started; there the only safe fallback is one that is conditional on the primary's final state, such as issuing the credit only after the gateway reports `failed` or `cancelled`.
