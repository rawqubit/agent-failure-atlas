"""MEM-01: unconditional per-turn memory writes fill top-k with paraphrases of one fact."""


def toks(s):
    return set(s.lower().replace(".", "").split())


def sim(a, b):
    return len(a & b) / len(a | b)


class Memory:
    def __init__(self, dedupe=None):
        self.items, self.dedupe = [], dedupe

    def write(self, text):
        t = toks(text)
        if self.dedupe and any(sim(t, m[1]) >= self.dedupe for m in self.items):
            return False
        self.items.append((text, t))
        return True

    def top_k(self, query, k=5, mmr=None):
        q = toks(query)
        pool = sorted(self.items, key=lambda m: -sim(q, m[1]))
        if mmr is None:
            return [m[0] for m in pool[:k]]
        chosen = []
        while pool and len(chosen) < k:
            best = max(pool, key=lambda m: mmr * sim(q, m[1])
                       - (1 - mmr) * max([sim(m[1], c[1]) for c in chosen] or [0]))
            chosen.append(best)
            pool.remove(best)
        return [m[0] for m in chosen]


ALLERGY = "severe peanut allergy"
PARAPHRASES = [
    "user preference concise answers",
    "user preference short concise answers",
    "user preference for brief answers",
    "user preference concise replies",
    "user preference no long answers",
    "user preference answers concise please",
    "user preference concise answers only",
    "user preference short answers",
    "user preference keep answers concise",
    "user preference concise answers again",
]
QUERY = "user preference allergy"


def fill(mem):
    mem.write(ALLERGY)
    return sum(mem.write(p) for p in PARAPHRASES)


naive = Memory()
fill(naive)
hits = naive.top_k(QUERY, k=5)
assert ALLERGY not in hits and len(naive.items) == 11
print("FAILURE: store holds %d items, top-5 for %r is all paraphrases; allergy retrieved: %s"
      % (len(naive.items), QUERY, ALLERGY in hits))

deduped = Memory(dedupe=0.4)
written = fill(deduped)
hits = deduped.top_k(QUERY, k=5)
assert ALLERGY in hits and len(deduped.items) < 5
print("FIXED (write-time dedupe): %d of 11 writes kept, top-5 %s" % (len(deduped.items), hits))

diverse = Memory()
fill(diverse)
hits = diverse.top_k(QUERY, k=5, mmr=0.5)
assert ALLERGY in hits
print("FIXED (MMR at read, no dedupe): allergy in top-5 at rank %d of the 11-item store"
      % (hits.index(ALLERGY) + 1))

old, new = toks("user is allergic to peanuts"), toks("user is no longer allergic to peanuts")
merge_score = sim(old, new)
assert merge_score > 0.4
print("RESIDUAL: a retraction scores %.2f against the fact it retracts, above the 0.4 merge threshold"
      % merge_score)
