"""OPS-03: retries at three layers multiply load on a failing dependency; one layer plus a budget does not."""
import random

REQUESTS = 100
HEALTHY_CAPACITY = 1000


class Unavailable(Exception):
    pass


class Dependency:
    def __init__(self):
        self.calls = 0

    def call(self):
        self.calls += 1
        raise Unavailable("503")


def retrying(fn, attempts):
    def wrapped():
        last = None
        for _ in range(attempts):
            try:
                return fn()
            except Unavailable as e:
                last = e
        raise last
    return wrapped


def stack(dep, sdk, tool, agent):
    return retrying(retrying(retrying(dep.call, sdk), tool), agent)


def drive(entry):
    failed = 0
    for _ in range(REQUESTS):
        try:
            entry()
        except Unavailable:
            failed += 1
    return failed


class RetryBudget:
    def __init__(self, ratio=0.10):
        self.ratio, self.requests, self.retries = ratio, 0, 0

    def allow_retry(self):
        if self.retries < self.ratio * self.requests:
            self.retries += 1
            return True
        return False


class Breaker:
    def __init__(self, threshold=5):
        self.threshold, self.failures = threshold, 0

    def call(self, fn):
        if self.failures >= self.threshold:
            raise Unavailable("circuit open")
        try:
            return fn()
        except Unavailable:
            self.failures += 1
            raise


def budgeted(fn, attempts, budget):
    def wrapped():
        budget.requests += 1
        for n in range(attempts):
            try:
                return fn()
            except Unavailable:
                if n == attempts - 1 or not budget.allow_retry():
                    raise
    return wrapped


dep = Dependency()
drive(stack(dep, 3, 3, 3))
assert dep.calls == REQUESTS * 27
print("FAILURE: %d logical requests became %d dependency calls (%dx); healthy capacity %d/window, offered load %.1fx of it"
      % (REQUESTS, dep.calls, dep.calls // REQUESTS, HEALTHY_CAPACITY, dep.calls / HEALTHY_CAPACITY))

dep = Dependency()
drive(stack(dep, 1, 1, 3))
assert dep.calls == REQUESTS * 3
print("FIXED (retries at one layer): %d calls (%dx)" % (dep.calls, dep.calls // REQUESTS))

dep, budget = Dependency(), RetryBudget(0.10)
drive(budgeted(dep.call, 3, budget))
assert dep.calls <= REQUESTS * 1.1 + 1
print("FIXED (one layer + 10%% retry budget): %d calls for %d requests, %d retries" % (dep.calls, REQUESTS, budget.retries))

dep, breaker = Dependency(), Breaker(5)
failed = drive(lambda: breaker.call(dep.call))
assert dep.calls == 5 and failed == REQUESTS
print("FIXED (circuit breaker, threshold 5): %d calls reached the dependency, %d requests failed fast" % (dep.calls, failed))


def retry_times(clients, waves, jitter, seed=7):
    rng = random.Random(seed)
    times = []
    for _ in range(clients):
        t = 0
        for n in range(waves):
            cap = 100 * 2 ** n
            t += rng.uniform(0, cap) if jitter else cap
            times.append(int(t) // 10)
    return times


def peak(times):
    return max(times.count(b) for b in set(times))


sync_peak, jit_peak = peak(retry_times(100, 1, False)), peak(retry_times(100, 1, True))
assert sync_peak == 100 and jit_peak < 25
print("FIXED (full jitter): peak retries in one 10 ms bucket for 100 clients, first retry wave: %d without jitter, %d with" % (sync_peak, jit_peak))

dep, budget = Dependency(), RetryBudget(0.10)
tool = budgeted(dep.call, 3, budget)
drive(retrying(tool, 3))
assert dep.calls > REQUESTS * 2.5
print("RESIDUAL: model re-issuing the failed tool call is a new request to the budgeted client: %d calls for %d requests, budget saw %d requests"
      % (dep.calls, REQUESTS, budget.requests))
