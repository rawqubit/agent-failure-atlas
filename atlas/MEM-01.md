---
id: MEM-01
title: Writing a memory every turn fills the top-k with paraphrases of one fact
category: memory
severity: high
frequency: common
symptom: The agent forgets a safety-relevant fact it was told once, while the memory store holds dozens of near-identical preference notes
stage: state-write
tags: memory, retrieval, deduplication, top-k
---

## What you see
The user said "severe peanut allergy" in turn 2. Forty turns later the agent recommends a satay dish, and the memory dump shows eleven rows, ten of which are variants of "user preference concise answers". In the repro, the allergy row exists in the store, and a top-5 query for `user preference allergy` returns five paraphrases of the style preference and not the allergy. The store looks healthy by every volume metric: writes succeed, retrieval returns k rows, latency is flat.

## Why it happens
A write hook that fires on every turn ("extract memories from this exchange") has no model of what is already stored, so a fact the user keeps demonstrating gets written again each time, worded slightly differently. Similarity search treats paraphrases as near-identical points, so they score almost the same against any query and arrive as a block. Top-k assumes the k slots hold k distinct pieces of evidence; with ten copies of one fact, k=5 slots hold one piece of evidence. The unique fact loses on rank, not on relevance: the retriever never decided the allergy was unimportant, it ran out of slots. Because the duplicates all come from the same recurring topic, the more often the user repeats a preference, the more slots it takes, which is the opposite of what an importance signal should do.

## Minimal reproduction
```python
def toks(s):
    return set(s.lower().split())

def sim(a, b):
    return len(a & b) / len(a | b)

class Memory:
    def __init__(self, dedupe=None):
        self.items, self.dedupe = [], dedupe
    def write(self, text):
        t = toks(text)
        if self.dedupe and any(sim(t, m[1]) >= self.dedupe for m in self.items):
            return
        self.items.append((text, t))
    def top_k(self, query, k=5):
        q = toks(query)
        return [m[0] for m in sorted(self.items, key=lambda m: -sim(q, m[1]))[:k]]

notes = ["severe peanut allergy"] + [
    "user preference " + s for s in ["concise answers", "short concise answers", "brief answers",
    "concise replies", "no long answers", "answers concise please", "concise answers only",
    "short answers", "keep answers concise", "concise answers again"]]
for dedupe in (None, 0.4):
    mem = Memory(dedupe)
    for n in notes:
        mem.write(n)
    hit = "severe peanut allergy" in mem.top_k("user preference allergy")
    print("FAILURE:" if not hit else "FIXED:", "dedupe=%s stored=%d allergy in top-5: %s"
          % (dedupe, len(mem.items), hit))
```
The retrieval here is token-overlap (Jaccard), a stand-in for embedding similarity; the mechanism is the same because paraphrases score alike against any query. repro/MEM-01.py adds a read-time MMR variant and the retraction case described under "How it still bites".

## Detection
Track the duplicate ratio of the store: for each new write, the maximum similarity to an existing row, logged as a histogram; a mass above your merge threshold means the writer is re-emitting known facts. Run a top-k diversity probe on a sample of real queries: the mean pairwise similarity inside the returned k rows, and alert when it stays above your write-dedupe threshold. For safety-class facts (allergies, permissions, hard constraints), keep a golden test that writes the fact, then writes fifty unrelated preference paraphrases, and asserts the fact is still in the top-k of its query.

## The fix
Decide at write time whether a memory is new. Compare the candidate against stored rows and, above a similarity threshold, merge into the existing row (bump a count and a last-seen time) instead of inserting. Gate writes on salience too: a memory that restates a preference already stored is not worth a row. At read time, select with maximal marginal relevance so one cluster cannot take every slot. Write-time dedupe is the structural fix because it keeps the store small and the index cheap; MMR alone leaves the rows in place and only hides the problem from one query path.
```python
if any(sim(t, m.tokens) >= 0.4 for m in rows):
    best.count += 1
    best.last_seen = now
else:
    rows.append(Memory(text, t, count=1, last_seen=now))
```

## How it still bites
Similarity-based dedupe cannot see negation or correction: in the repro, "user is no longer allergic to peanuts" scores 0.71 against "user is allergic to peanuts", so a merge keeps the old row and drops the retraction. Whatever merge rule you pick needs to treat contradicting values as an update (see MEM-03), not as a duplicate. A threshold tuned on preference chatter will also be wrong for structured facts, where two rows that differ in one number are different facts.
