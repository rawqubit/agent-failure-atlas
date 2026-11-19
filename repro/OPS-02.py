"""OPS-02: check-then-spend on a shared fleet budget overspends; atomic reserve-before-call holds the limit."""
import threading

FLEET_LIMIT = 1000
PER_RUN_LIMIT = 500
RUNS = 8


class Budget:
    def __init__(self, limit):
        self.remaining, self.spent, self.lock, self.halted = limit, 0, threading.Lock(), False

    def read(self):
        return self.remaining

    def spend(self, cents):
        with self.lock:
            self.remaining -= cents
            self.spent += cents

    def reserve(self, cents):
        with self.lock:
            if self.halted or self.remaining < cents:
                return False
            self.remaining -= cents
            return True

    def settle(self, reserved, actual):
        with self.lock:
            self.remaining += reserved - actual
            self.spent += actual


def fleet(worker):
    barrier = threading.Barrier(RUNS)
    results = []
    threads = [threading.Thread(target=lambda: results.append(worker(barrier))) for _ in range(RUNS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def run_naive(estimate, actual):
    budget = Budget(FLEET_LIMIT)

    def worker(barrier):
        per_run_ok = actual <= PER_RUN_LIMIT
        fleet_ok = budget.read() >= estimate
        barrier.wait()
        if per_run_ok and fleet_ok:
            budget.spend(actual)
            return True
        return False

    return budget, fleet(worker)


def run_reserved(estimate, actual):
    budget = Budget(FLEET_LIMIT)

    def worker(barrier):
        got = budget.reserve(estimate)
        barrier.wait()
        if got:
            budget.settle(estimate, actual)
        return got

    return budget, fleet(worker)


budget, ok = run_naive(estimate=400, actual=400)
assert sum(ok) == RUNS and budget.spent == 3200 > FLEET_LIMIT
print("FAILURE: %d of %d runs passed their own checks; fleet spent %d cents against a limit of %d (overspend %d)"
      % (sum(ok), RUNS, budget.spent, FLEET_LIMIT, budget.spent - FLEET_LIMIT))

budget, ok = run_reserved(estimate=400, actual=400)
assert sum(ok) == 2 and budget.spent == 800 <= FLEET_LIMIT
print("FIXED: reserve-before-call admitted %d runs, spent %d of %d, %d runs refused"
      % (sum(ok), budget.spent, FLEET_LIMIT, RUNS - sum(ok)))

budget = Budget(FLEET_LIMIT)
budget.halted = True
assert not budget.reserve(1)
print("FIXED: kill switch (halted=True) refuses every new reservation at the call wrapper")

budget, ok = run_reserved(estimate=300, actual=450)
assert sum(ok) == 3 and budget.spent == 1350 > FLEET_LIMIT
print("RESIDUAL: reserved on a 300 cent estimate but calls cost 450: %d admitted, reserved %d, spent %d; "
      "%d over the limit, because each call exceeded its reservation by %d"
      % (sum(ok), sum(ok) * 300, budget.spent, budget.spent - FLEET_LIMIT, 450 - 300))

budget, ok = run_reserved(estimate=450, actual=450)
assert sum(ok) == 2 and budget.spent == 900 <= FLEET_LIMIT
print("FIXED: reserving the worst case (max_tokens priced) %d admitted %d, spent %d" % (450, sum(ok), budget.spent))
