---
id: TOOL-04
title: The agent retries a non-idempotent tool and double-charges the customer
category: tool-use
severity: critical
frequency: common
symptom: Duplicate side effects after a timeout or a 500; two charges, two emails, two tickets
stage: tool-execution
tags: idempotency, retries, side-effects
---

## What you see
Support gets a ticket: "I was charged twice for order 8841." The payment provider shows two captures for the same amount 31 seconds apart, and the agent trace shows one `charge_card` call that logged `ReadTimeout after 30s` followed by a second `charge_card` call with identical arguments that returned 200. The agent's final message to the user says "Your payment of $49.00 went through", which is true twice over.

## Why it happens
The retry wrapper assumes that an error means the operation did not happen. A read timeout or a 502 from a gateway only says the client did not receive a response; the payment service may have committed the charge a few milliseconds before the connection dropped. Retry logic that lives in the agent framework is generic, so it cannot know that `charge_card` mutates money while `get_order` does not. The model compounds it: given a tool error, it will often decide on its own to call the same tool again because that is the obvious recovery. Nothing in the call carries an identity for the intended operation, so the server has no way to tell a retry from a second purchase.

## Minimal reproduction
```python
import uuid

class PaymentAPI:
    def __init__(self):
        self.charges, self.seen = [], {}
    def charge(self, amount, idem_key=None):
        if idem_key and idem_key in self.seen:
            return self.seen[idem_key]
        self.charges.append(amount)
        result = {"charge_id": len(self.charges), "amount": amount}
        if idem_key:
            self.seen[idem_key] = result
        if len(self.charges) == 1:
            raise TimeoutError("response lost after commit")
        return result

def run(with_key):
    api = PaymentAPI()
    key = str(uuid.uuid4()) if with_key else None
    for attempt in range(2):
        try:
            return api, api.charge(4900, idem_key=key)
        except TimeoutError:
            continue

api, _ = run(with_key=False)
print("FAILURE: charges recorded without key:", api.charges)
api, _ = run(with_key=True)
print("FIXED: charges recorded with idempotency key:", api.charges)
```
The same code with assertions is in repro/TOOL-04.py.

## Detection
Alert on duplicate side effects keyed by business identity, not by request: a nightly query for `(customer_id, amount, order_id)` tuples with more than one successful `charge_card` span in the same trace is a zero-tolerance page. In tracing, flag any trace where the same mutating tool name appears twice with byte-identical arguments and the first span ended in a timeout or 5xx. In tests, wrap every mutating tool in a fault injector that commits and then raises, and assert the side-effect count stays at one.

## The fix
Make the operation idempotent at the tool boundary: the tool adapter generates one idempotency key per intended operation (derived from the run id plus the step id, never from the model's output), sends it on every attempt, and the server returns the stored result for a key it has already seen. Mark each tool `idempotent` or `mutating` in its registration and let the framework retry only the first kind automatically. A prompt that says "do not retry payments" is a band-aid: it depends on the model obeying and does not cover the framework's own retry layer.
```python
key = f"{run_id}:{step_id}"  # stable across retries, unrelated to model text
api.charge(4900, idem_key=key)
```

## How it still bites
Idempotency keys expire: a retry that arrives after the provider's key retention window (often 24 hours) is treated as new, which matters for agents that resume paused runs the next day. Downstream systems you call through the payment tool, such as the receipt email, are rarely keyed, so the charge is deduplicated while the customer still gets two emails.
