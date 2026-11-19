---
id: PLAN-04
title: Parallel subagents lose each other's edits through read-modify-write on a shared artifact
category: planning
severity: medium
frequency: occasional
symptom: Merged report is missing findings from some subagents although each subagent's trace says its write succeeded
stage: state-write
tags: parallelism, subagents, lost-update, shared-state
---

## What you see
An orchestrator fans out three research subagents that all append to `notes.md`. The final report cites findings from one of them. Each subagent's trace ends with "appended finding to notes.md: ok", the file's version counter advanced three times, and the file contains a single finding.

## Why it happens
Every worker does the same three things: read the whole artifact, spend a model call deciding what to add, write the whole artifact back. A plain write is a blind overwrite, so anything another worker wrote between this worker's read and its write is erased without an error. Fan-out guarantees the overlap: parallel workers start from the same snapshot and run model calls of similar length, and the longer the call, the wider the window. The last writer wins and the others' work disappears. The repro does not rely on thread timing; it interleaves three generators in a fixed order (all read, then all write), which is one valid schedule among many that real concurrency produces.

## Minimal reproduction
```python
class Conflict(Exception): pass

class Store:
    def __init__(self): self.doc, self.version = [], 0
    def read(self): return list(self.doc), self.version
    def write(self, doc, expect=None):
        if expect is not None and expect != self.version: raise Conflict
        self.doc, self.version = doc, self.version + 1

def worker(store, name, cas):
    while True:
        doc, version = store.read()
        yield
        try:
            store.write(doc + ["finding from " + name], version if cas else None)
            return
        except Conflict:
            continue

def run(names, cas):
    store = Store()
    pending = [worker(store, n, cas) for n in names]
    while pending:
        for w in list(pending):
            try: next(w)
            except StopIteration: pending.remove(w)
    return store.doc

doc = run("ABC", cas=False)
assert len(doc) == 1
print("FAILURE: 3 workers wrote, notes hold %d: %s" % (len(doc), doc))
doc = run("ABC", cas=True)
assert len(doc) == 3
print("FIXED: compare-and-swap with re-read, notes hold %d: %s" % (len(doc), doc))
```
The same two runs with version counters printed are in repro/PLAN-04.py.

## Detection
Make every worker return a unique contribution id, and after the join assert that the set of ids found in the artifact equals the set of ids the workers reported: `expected - found` must be empty, and any leftover is a lost update. In logs, compare the number of successful writes to the artifact against the number of distinct contribution ids it contains; a gap is the signature. A test that runs N workers under a fixed read-all-then-write-all schedule catches the bug without any real concurrency.

## The fix
Remove the shared whole-document write. The smallest correct change is optimistic concurrency: the write carries the version it read, the store rejects it on mismatch, and the worker re-reads and recomputes its change on the fresh snapshot. If the data allows it, the structural fix is better: give each worker its own file or section (partitioned ownership) or an append-only log, and have the orchestrator merge after the join. Telling workers in the prompt to "re-read before writing" is a band-aid, since the race is between the re-read and the write.
```python
doc, version = store.read()
store.write(apply_change(doc), expect=version)
```

## How it still bites
Compare-and-swap makes the overwrite loud, but a retry that blindly re-applies the old edit still acts on a decision made against a stale snapshot; the worker has to redo its reasoning on the fresh read, which costs another model call. And append-only merging is only syntactic: two workers can each append a valid finding that contradicts the other ("use Postgres", "use SQLite"), and no store-level mechanism notices.
