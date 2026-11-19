---
id: OPS-03
title: Layered retries multiply load on a degraded dependency until it cannot recover
category: operations
severity: critical
frequency: common
symptom: A dependency that was merely slow goes down hard, request rate to it is many times the user-facing rate, and it can stay down after the original fault clears
stage: tool-execution
tags: retries, amplification, backoff, circuit-breaker
---

## What you see
A search backend starts returning 503s for thirty seconds. User traffic is flat at 100 requests per window, but the backend's request graph shows 2700 per window. In the repro, 100 logical requests produce 2700 calls, which is 2.7 times the capacity of 1000 calls per window that the repro assumes for the dependency. If overload is what keeps the dependency failing, the retry traffic sustains it after the original fault ends; the repro counts calls and does not simulate that recovery.

## Why it happens
Each layer in the stack added a retry loop for its own good reason: the HTTP SDK retries 3 times, the tool wrapper retries 3 times around the SDK, and the agent loop retries the whole tool call 3 times. A retry loop assumes it is the only one; none can see the others. Failures multiply, so the worst case is 3 x 3 x 3 = 27 calls per logical request, and all of it arrives within milliseconds when attempts are immediate or backoff has no jitter, since every client fails at the same instant. The result is a load that peaks exactly when the dependency has the least capacity, and synchronized retry waves can keep it above capacity after the root cause is gone.

## Minimal reproduction
```python
class Unavailable(Exception):
    pass

class Dependency:
    calls = 0
    def call(self):
        self.calls += 1
        raise Unavailable

class Budget:
    requests = retries = 0
    def allow(self):
        ok = self.retries < 0.1 * self.requests
        self.retries += ok
        return ok

def retrying(fn, attempts, budget=None):
    def wrapped():
        if budget:
            budget.requests += 1
        for n in range(attempts):
            try:
                return fn()
            except Unavailable:
                if n == attempts - 1 or (budget and not budget.allow()):
                    raise
    return wrapped

def drive(entry):
    for _ in range(100):
        try: entry()
        except Unavailable: pass

dep = Dependency()
drive(retrying(retrying(retrying(dep.call, 3), 3), 3))
print("FAILURE: 100 requests became", dep.calls, "calls")
dep = Dependency()
drive(retrying(dep.call, 3, Budget()))
print("FIXED: one layer with a 10% retry budget:", dep.calls, "calls")
```
The dependency here fails every call, which is the worst case and a synchronous model of immediate retries; the capacity figure is a labelled constant in the repro file, not a measurement. repro/OPS-03.py adds a circuit breaker, a jitter comparison and the residual case below.

## Detection
Watch the amplification ratio: dependency requests divided by the upstream requests that caused them, from the dependency's own access log against the agent's request counter. A healthy ratio sits near 1.0 plus the true error rate; a ratio above 2 during an error spike is retry stacking, and the stack depth shows in the ratio (3, 9, 27). Tag every outbound call with an attempt number and a layer name in the log, then query for traces where one root request has more than one attempt label at different layers. A fault-injection test that makes the dependency fail every call and asserts total calls per request stays under a fixed bound catches stacking before an outage does.

## The fix
Put retries in exactly one layer, the one that knows the operation is safe to repeat (see TOOL-04), and set the others to a single attempt. At that layer, bound retries with a budget: allow a retry only while retries are under 10% of requests, which in the repro holds 100 requests to 110 calls against 2700 before. Use exponential backoff with full jitter (a random delay between zero and the backoff cap) so clients do not return in waves; in the repro the first retry wave peaks at 13 per 10 ms bucket with jitter and 100 without. Add a circuit breaker so a dependency that is plainly down gets 5 probing calls instead of every request. Pass a deadline or a no-retry flag downward so inner layers stop when the outer one has given up. Collapsing to one layer is the structural step; the budget and breaker make the one remaining layer safe.
```python
sdk = Client(max_retries=0)
tool = Tool(sdk, max_retries=0)
agent.call_tool = budgeted(tool.run, attempts=3, budget=shared_budget)
```

## How it still bites
The model is a retry layer you cannot configure: after a tool error it may call the same tool again with the same arguments, and a client-side retry budget counts that as a fresh request: in repro/OPS-03.py, with a 10% budget on the client and three model-driven re-issues on top, 100 requests still cause 330 calls, because the budget saw 300 requests and each earned its own first attempt. Treat a repeated identical call after an error as a retry in the agent loop's accounting, and return errors that tell the model not to retry (a permanent-failure flag or a retry-after hint) rather than leaving it to guess. Callers of your own service also retry, and nothing you configure inside the stack limits them.
