"""CTX-01: a constraint in the middle of a long context loses to a task instruction at the end.

The model is a STUB. Its pull for each instruction is strength * weight(position), where weight is
U-shaped: 1.0 at either edge, falling with distance to the nearest edge down to a floor. That models
position-dependent recall; it does not prove anything about any real model.
"""


def weight(pos, total, span=12000):
    return max(0.2, 1 - min(pos, total - pos) / span)


def decide(context):
    pull, total, pos = {"keep": 0.0, "delete": 0.0}, sum(n for n, *_ in context), 0
    for n, kind, strength in context:
        if kind:
            pull[kind] += strength * weight(pos + n / 2, total)
        pos += n
    return max(pull, key=pull.get)


def build(constraint_at, chunks=40, restate=False):
    ctx = [(500, None, 0)] * chunks
    ctx.insert(constraint_at, (50, "keep", 1.0))
    if restate:
        ctx.append((50, "keep", 1.0))
    return ctx + [(50, "delete", 0.6)]


losing = []
for at in range(0, 41, 5):
    outcome = decide(build(at))
    print(f"constraint at {at / 40:4.0%} of a 20k-token context -> {outcome}")
    if outcome == "delete":
        losing.append(at)

assert decide(build(0)) == "keep" and decide(build(40)) == "keep"
assert losing == [10, 15, 20, 25, 30]
print(f"FAILURE: constraint ignored at {len(losing)} of 9 positions (25% to 75%); only the outer eighth on each side holds")

assert decide(build(20, restate=True)) == "keep"
assert decide(build(3, chunks=6)) == "keep"
assert decide(build(0, restate=True)) == "keep"
print("FIXED: restated after the haystack, or haystack cut to 3k tokens, or pinned first: constraint wins at 50%")
