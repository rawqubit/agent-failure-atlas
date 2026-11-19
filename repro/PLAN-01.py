"""PLAN-01: a loop whose next action depends only on the last observation never leaves a fixed point."""
import hashlib
import json


def make_search():
    calls = {"n": 0}

    def search(q, volatile=False):
        calls["n"] += 1
        return {"results": [], "request_id": calls["n"] if volatile else 0}

    return search


def policy(obs):
    return ("search", {"q": "invoice 4471"})


def fingerprint(name, args, result, volatile_keys):
    stable = {k: v for k, v in result.items() if k not in volatile_keys}
    return hashlib.sha1(json.dumps([name, args, stable], sort_keys=True).encode()).hexdigest()


def run(max_turns, detect, volatile=False, volatile_keys=(), limit=3):
    search, seen, calls, obs = make_search(), {}, 0, "start"
    for turn in range(max_turns):
        name, args = policy(obs)
        result = search(volatile=volatile, **args)
        obs = json.dumps(result["results"])
        calls += 1
        if detect:
            key = fingerprint(name, args, result, volatile_keys)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= limit:
                return calls, "escalated after %d identical (tool, args, result)" % limit
    return calls, "hit max_turns=%d" % max_turns


calls, end = run(50, detect=False)
assert calls == 50 and end.startswith("hit max_turns")
print("FAILURE: %d identical search calls, run ended by: %s" % (calls, end))

calls, end = run(50, detect=True)
assert calls == 3 and end.startswith("escalated")
print("FIXED: %d calls, %s" % (calls, end))

calls, end = run(50, detect=True, volatile=True)
assert calls == 50
print("STILL BITES: result carries a request_id, raw hash never repeats: %d calls, %s" % (calls, end))

calls, end = run(50, detect=True, volatile=True, volatile_keys=("request_id",))
assert calls == 3
print("FIXED (normalized): volatile keys dropped before hashing: %d calls, %s" % (calls, end))
