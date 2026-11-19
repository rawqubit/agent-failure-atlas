"""COST-02: prefix caching matches leading content block by block, so one per-request value early in the prompt voids every block after it.

The cache is a simulator: tokens are words, blocks are 16 tokens, and each block's key is a hash chained over every block before it.
This models exact-prefix matching; it does not model any provider's block size, retention or eviction.
"""
import hashlib
import random

BLOCK = 16
SYSTEM = ["rule%d" % i for i in range(400)]
TOOLS = {"tool%02d" % i: ["arg%d_%d" % (i, j) for j in range(40)] for i in range(12)}


def build(n, volatile_first, names, stamp=None):
    stamp = [stamp or "now=2026-11-19T10:00:%02dZ" % n]
    tools = [w for name in names for w in [name] + TOOLS[name]]
    history = ["turn%d_word%d" % (k, j) for k in range(n) for j in range(60)]
    body = SYSTEM + tools + history
    return stamp + body if volatile_first else body + stamp


def hit_rates(prompts):
    seen, hits, total, per_request = set(), 0, 0, []
    for words in prompts:
        h, run, missed = "", 0, False
        blocks = len(words) // BLOCK
        for b in range(blocks):
            h = hashlib.sha256((h + " ".join(words[b * BLOCK:(b + 1) * BLOCK])).encode()).hexdigest()
            if not missed and h in seen:
                run += 1
            else:
                missed = True
            seen.add(h)
        hits, total = hits + run, total + blocks
        per_request.append(run / blocks)
    return hits / total, per_request


N = range(1, 21)
rng = random.Random(7)

lead, _ = hit_rates([build(n, True, sorted(TOOLS)) for n in N])
assert lead == 0.0
print("FAILURE: timestamp as the first token, hit rate over 20 requests: %.1f%%" % (100 * lead))

unstable, _ = hit_rates([build(n, False, rng.sample(sorted(TOOLS), 12)) for n in N])
assert 0.2 < unstable < 0.35
print("FAILURE: timestamp last but tool list in a different order per request: %.1f%%" % (100 * unstable))

fixed, per_request = hit_rates([build(n, False, sorted(TOOLS)) for n in N])
assert fixed > 0.9 and min(per_request[1:]) > 0.85
print("FIXED: static first, tools sorted, timestamp last: %.1f%% (first request is cold)" % (100 * fixed))

daily, per_request = hit_rates([build(n, True, sorted(TOOLS), "date=2026-11-%02d" % (19 + n // 11)) for n in N])
assert per_request[10] == 0.0 and per_request[9] > 0.9
print("residual: a date-only header at the top hits %.1f%% overall, but request 11 (day rollover) hits %.0f%%"
      % (100 * daily, 100 * per_request[10]))
