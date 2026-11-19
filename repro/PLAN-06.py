"""PLAN-06: 'make it faster' has no executable criterion, so a no-op change can be declared done."""


class Ops:
    n = 0


def slow(items, ops):
    seen, counts = [], {}
    for x in items:
        for s in seen:
            ops.n += 1
            if s == x:
                break
        else:
            seen.append(x)
        counts[x] = counts.get(x, 0) + 1
    return counts


def renamed(items, ops):
    uniq, tally = [], {}
    for item in items:
        for u in uniq:
            ops.n += 1
            if u == item:
                break
        else:
            uniq.append(item)
        tally[item] = tally.get(item, 0) + 1
    return tally


def cheat(items, ops):
    return {}


def real(items, ops):
    counts = {}
    for x in items:
        ops.n += 1
        counts[x] = counts.get(x, 0) + 1
    return counts


def measure(fn, items):
    ops = Ops()
    return fn(items, ops), ops.n


ITEMS = [i % 40 for i in range(200)]
baseline_out, baseline_ops = measure(slow, ITEMS)


def vague_done(candidate):
    return candidate is not slow


def accept(candidate):
    out, ops = measure(candidate, ITEMS)
    return out == baseline_out and ops <= baseline_ops // 2


for name, cand in [("renamed", renamed), ("cheat", cheat), ("real", real)]:
    print("%-8s vague criterion: %-5s predicate: %-5s ops %d -> %d" % (
        name, vague_done(cand), accept(cand), baseline_ops, measure(cand, ITEMS)[1]))

assert vague_done(renamed) and measure(renamed, ITEMS)[1] == baseline_ops
assert vague_done(cheat) and not accept(cheat)
print("FAILURE: no-op change declared done under 'make it faster': ops %d -> %d" % (baseline_ops, measure(renamed, ITEMS)[1]))

assert not accept(renamed) and not accept(cheat) and accept(real)
print("FIXED: predicate (same output, ops <= %d) rejects the no-op and the wrong-but-fast change, accepts the real one (ops %d)" % (baseline_ops // 2, measure(real, ITEMS)[1]))
