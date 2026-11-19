---
id: MEM-03
title: A fact that was true two years ago outranks the correction because nothing ever expires or supersedes
category: memory
severity: high
frequency: common
symptom: The agent keeps using a customer's old address, plan or contact after the customer corrected it; the correction exists in the store but never ranks first
stage: state-write
tags: memory, staleness, supersession, ranking
---

## What you see
A user moved and said so. The store now has both rows: "shipping_address = 12 Oak St" from 800 days ago and "shipping_address = 9 Pine Ave" from yesterday. A parcel goes to Oak Street. In the repro, the old row wins top-1 for "what is the user's shipping address" because it has been read 40 times and the correction has been read zero times.

## Why it happens
The store is append-only and scores rows by similarity plus a usage term (access count, a common stand-in for importance). Both rows describe the same entity and attribute, so their similarity to the query is identical, and the usage term decides. Usage is a feedback loop: a row that is retrieved gets its counter bumped, which makes it more likely to be retrieved again, and a correction starts with a counter of zero against a rival that has had two years to accumulate. The broken assumption is that two rows about the same attribute can coexist and the retriever will pick the current one; nothing in the data says which one is current, so the score picks the one that is popular.

## Minimal reproduction
```python
import math

class Store:
    def __init__(self, supersede):
        self.rows, self.supersede = [], supersede
    def write(self, entity, attr, value, day):
        if self.supersede:
            self.rows = [r for r in self.rows if (r["e"], r["a"]) != (entity, attr)]
        self.rows.append({"e": entity, "a": attr, "v": value, "day": day, "reads": 0})
    def get(self, entity, attr):
        hits = [r for r in self.rows if (r["e"], r["a"]) == (entity, attr)]
        best = max(hits, key=lambda r: math.log1p(r["reads"]))
        best["reads"] += 1
        return best["v"]

for supersede in (False, True):
    s = Store(supersede)
    s.write("user", "shipping_address", "12 Oak St", day=0)
    for _ in range(40):
        s.get("user", "shipping_address")
    s.write("user", "shipping_address", "9 Pine Ave", day=799)
    got = s.get("user", "shipping_address")
    print("FIXED:" if got == "9 Pine Ave" else "FAILURE:", "supersede=%s answer=%s rows=%d"
          % (supersede, got, len(s.rows)))
```
Here retrieval is reduced to a key lookup with a usage tie-break so the mechanism is visible without an embedding model. repro/MEM-03.py uses a similarity-plus-usage score, keeps history instead of deleting, and covers the key-mismatch case from "How it still bites".

## Detection
Query the store for live rows that share (entity, attribute) and differ in value: `SELECT entity, attribute, COUNT(DISTINCT value) FROM facts WHERE valid_to IS NULL GROUP BY 1, 2 HAVING COUNT(DISTINCT value) > 1` should return zero rows for single-valued attributes, and any row it returns is a live contradiction. Log the age of the winning row at read time per fact class; an address or plan row served at an age well past that class's churn rate is a stale read. In tests, write a value, read it repeatedly, write a correction, and assert the next read returns the correction.

## The fix
Give every fact a key of (entity, attribute) and make a write to an existing key close the previous row (set `valid_to`) in the same transaction as the insert, so exactly one live row exists per single-valued key. Keep the closed row as history, because "what was the address on the date of that order" is a real question, but exclude it from live retrieval. Add a TTL per fact class (a mood or location expires in hours, a legal name never does) and put recency into the score so unkeyed facts degrade too; when retrieval does return two live rows with different values, surface the conflict to the model rather than choosing silently. Supersession is the structural fix: a recency term alone is fragile, because it is just another weight: at 0.5 per year of age the penalty for a one-year gap is 0.5, which a usage bonus of 0.1 * ln(1 + reads) matches at about 150 reads.
```python
cur.execute("UPDATE facts SET valid_to=? WHERE entity=? AND attr=? AND valid_to IS NULL", (now, e, a))
cur.execute("INSERT INTO facts(entity, attr, value, valid_from) VALUES (?,?,?,?)", (e, a, v, now))
```

## How it still bites
Supersession only fires when the new write produces the same key, and keys are chosen by an extractor model: in the repro a correction written as `ship_to_address` does not close `shipping_address`, both rows stay live, and the old one still wins. Constrain the extractor to a closed attribute vocabulary and reject writes with unknown keys. Also, when the user says "ship it to my office this once", the right write is an event scoped to one order, not an overwrite of the default address.
