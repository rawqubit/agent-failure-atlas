---
id: OPS-02
title: Per-run budgets pass while the fleet overspends because the budget check is not atomic
category: operations
severity: high
frequency: occasional
symptom: Every run's budget guard logs "ok" and the daily spend cap is still blown, by a multiple of the limit, within a minute of a traffic burst
stage: billing
tags: budgets, concurrency, check-then-act, rate-limits
---

## What you see
The fleet cap is 1000 cents per window, and a burst starts eight runs together. Each logs "budget ok: remaining 1000, need 400" and proceeds, and the spend dashboard later shows 3200 cents. In the repro, eight of eight runs passed both their per-run limit and the fleet check, and the overspend is 2200 cents. Reading any one run's log gives no hint of a problem, because each decision was correct for the state it saw.

## Why it happens
The guard is check-then-spend: read the remaining budget, compare with the cost of the next call, make the call, subtract afterwards. The read and the subtraction are separate operations with a model call of seconds in between, so any number of concurrent runs can read the same remaining value before the first one subtracts. The assumption that breaks is that the balance you read is still the balance when you spend; it holds for a single sequential run and fails in proportion to concurrency. A per-run limit cannot catch it, since every run is individually under its limit; the cap that matters is a shared resource. This is distinct from a single run looping without end (PLAN-01): here each run behaves, and the aggregate does not.

## Minimal reproduction
```python
import threading

LIMIT, RUNS, COST = 1000, 8, 400

class Budget:
    def __init__(self):
        self.remaining, self.spent, self.lock = LIMIT, 0, threading.Lock()
    def spend(self, cents):
        with self.lock:
            self.remaining -= cents
            self.spent += cents
    def reserve(self, cents):
        with self.lock:
            if self.remaining < cents:
                return False
            self.remaining -= cents
            self.spent += cents
            return True

def fleet(admit, charge=lambda b: None):
    b, barrier = Budget(), threading.Barrier(RUNS)
    def worker():
        ok = admit(b)
        barrier.wait()
        if ok:
            charge(b)
    ts = [threading.Thread(target=worker) for _ in range(RUNS)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return b.spent

spent = fleet(lambda b: b.remaining >= COST, lambda b: b.spend(COST))
print("FAILURE: check-then-spend spent", spent, "against a limit of", LIMIT)
spent2 = fleet(lambda b: b.reserve(COST))
print("FIXED: reserve-then-call spent", spent2, "against a limit of", LIMIT)
assert spent == 3200 and spent2 == 800
```
The barrier forces every thread to finish its check before any spends, which makes the interleaving deterministic instead of depending on timing luck. repro/OPS-02.py adds the per-run limit, the kill switch and the estimate-versus-actual case.

## Detection
Compare two numbers on a schedule: spend according to the provider's billing export for the window, and the cap you enforced; the first exceeding the second is the direct signal, and the ratio tells you the concurrency factor. In the guard itself, log the balance read and the balance after settle for each call; two calls whose "read" values are equal and whose cost together exceeds that value are a race, and a query over those logs finds them. A test that starts N threads behind a Barrier against the guard and asserts total spend stays at or under the cap catches the regression before deploy.

## The fix
Replace read-then-spend with reserve-then-settle in the wrapper that every model call goes through. Reserve atomically (a lock in one process, a conditional UPDATE or a Lua script in a shared store when runs span processes) the estimated cost before the call; refuse the call when the reservation does not fit; after the call, settle by returning the difference between the reserved and actual cost. Put a halt flag in the same atomic path so an operator can stop all new calls without redeploying. Enforcing in the wrapper is the structural fix: a prompt telling the model to be frugal does not constrain the harness that issues the calls.
```sql
UPDATE budget SET remaining = remaining - :est WHERE window = :w AND remaining >= :est AND NOT halted
-- rows_affected == 0 means refuse the call
```

## How it still bites
The cap is only as tight as the reservation: in the repro, reserving 300 cents for calls that cost 450 admits three runs, spends 1350 and ends 350 over the limit, so reserve the worst case (price the max output tokens) or accept an overshoot of up to admitted_calls * (actual - estimate). A run that crashes after reserving never settles, so reservations need an expiry or the budget slowly shrinks to zero with no spend behind it.
