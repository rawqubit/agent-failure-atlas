"""COST-01: resending the whole history each turn bills t*n*(n+1)/2 input tokens, and the usual mitigations change the constant before they change the order.

PRICE and CACHED are labelled assumptions for arithmetic, not any provider's rates: PRICE is USD per 1M uncached input tokens,
CACHED is the fraction of that price charged for tokens served from a prefix cache. Output tokens and the system prompt are ignored.
Each turn adds 800 tokens: 100 of model text and 700 of tool result. A masked tool result leaves a 20-token stub (120 total).
"""

PRICE, CACHED = 3.00, 0.10
SIZE = {"full": 800, "stub": 120, "sum": 500}


def run(n_turns, cache=False, stride=0, cap=0, keep=3):
    hist, prev, tokens, equiv = [], [], 0, 0.0
    for n in range(1, n_turns + 1):
        hist.append((n, "full"))
        if stride and n % stride == 0:
            hist = [(k, v if v != "full" or i >= len(hist) - keep else "stub") for i, (k, v) in enumerate(hist)]
        if cap and sum(SIZE[v] for _, v in hist) > cap:
            hist = [(n, "sum")] + hist[-keep:]
        size = [SIZE[v] for _, v in hist]
        hit = 0
        while cache and hit < min(len(prev), len(hist)) and prev[hit] == hist[hit]:
            hit += 1
        tokens += sum(size)
        equiv += CACHED * sum(size[:hit]) + sum(size[hit:])
        prev = list(hist)
    return tokens, equiv


def usd(equiv):
    return equiv * PRICE / 1e6


T, N = 800, 60
naive, naive_eq = run(N)
assert naive == T * N * (N + 1) // 2 == 1_464_000
assert T * N == 48_000
print("FAILURE: %d turns of %d tokens bill %d input tokens ($%.2f) vs %d if only deltas were sent (%.1fx)"
      % (N, T, naive, usd(naive_eq), T * N, naive / (T * N)))

_, cached = run(N, cache=True)
assert cached == 189_600
_, cached2 = run(2 * N, cache=True)
_, naive2 = run(2 * N)
print("cached prefix: %d token-equivalents ($%.2f); doubling turns multiplies cost by %.2f (uncached: %.2f)"
      % (cached, usd(cached), cached2 / cached, naive2 / naive))
assert cached2 / cached > 3.4

_, every_turn = run(N, cache=True, stride=1)
print("mask every turn + cache: %d (%.0f%% below cache alone): each mask rewrites an entry inside the cached prefix"
      % (every_turn, 100 * (1 - every_turn / cached)))
assert every_turn > 0.85 * cached

_, batched = run(N, cache=True, stride=10)
print("mask every 10 turns + cache, no cap: %d" % batched)
assert batched == 108_720
_, fixed = run(N, cache=True, stride=10, cap=6000)
_, fixed2 = run(2 * N, cache=True, stride=10, cap=6000)
_, fixed4 = run(4 * N, cache=True, stride=10, cap=6000)
print("FIXED: batched masking every 10 turns + 6000-token cap + cache: %d ($%.2f), %.1fx below naive; "
      "120 turns costs %.2fx, 240 turns %.2fx" % (fixed, usd(fixed), naive_eq / fixed, fixed2 / fixed, fixed4 / fixed))
assert fixed < naive_eq / 10 and fixed < cached / 1.8
assert fixed2 / fixed < 2.1 and fixed4 / fixed < 4.2
