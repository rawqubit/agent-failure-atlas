---
id: MEM-05
title: The agent acts on remembered state that no longer matches the world
category: memory
severity: high
frequency: common
symptom: A write lands on a record someone else changed after the agent last looked, silently reopening, overwriting or reassigning it
stage: tool-execution
tags: memory, stale-state, optimistic-concurrency, writes
---

## What you see
The agent's notes say "ticket 77: open, unassigned". A teammate resolved it twenty minutes ago. The agent claims the ticket and the store accepts the write, so the ticket now reads in_progress and assigned to the bot, and the teammate's resolution is gone from the live row. Nothing errored; the audit log shows one valid update by an authenticated caller.

## Why it happens
The agent keeps a belief about an external record (in a memory store, a scratchpad, or a cached tool result) and decides from the belief. Between the read and the write other actors act, and the write path is a blind put: it applies whatever the caller sends and carries no statement of what the caller thought it was overwriting. The broken assumption is that remembered state is still current, which is true only for state nobody else writes. This is a different failure from a summary that keeps text after the world moved (CTX-06) and from a ranker that prefers an old row (MEM-03); here the memory may be perfectly accurate about the past, and the damage is done by the write that trusts it.

## Minimal reproduction
```python
class PreconditionFailed(Exception):
    pass

class Store:
    def __init__(self):
        self.row = {"status": "open", "assignee": None, "version": 1}
    def put(self, fields, expect=None):
        if expect is not None and self.row["version"] != expect:
            raise PreconditionFailed("at version %d, expected %d" % (self.row["version"], expect))
        self.row.update(fields)
        self.row["version"] += 1

def attempt(guarded):
    store = Store()
    belief = dict(store.row)
    store.put({"status": "resolved", "assignee": "dana"})
    try:
        store.put({"status": "in_progress", "assignee": "agent"},
                  expect=belief["version"] if guarded else None)
    except PreconditionFailed as e:
        return store.row["status"], "refused: " + str(e)
    return store.row["status"], "wrote"

status, outcome = attempt(guarded=False)
assert status == "in_progress"
print("FAILURE: belief said open, store said resolved; blind put left status =", status)
status, outcome = attempt(guarded=True)
assert status == "resolved" and outcome.startswith("refused")
print("FIXED: guarded put", outcome, "; store status =", status)
```
repro/MEM-05.py adds the re-read step and the multi-record case described below.

## Detection
Log, on every mutating tool call, the version or etag the agent believed it was writing against next to the version the store held at commit time; the count of calls where the two differ (or where no expected version was sent at all) is the exposure metric, and any unguarded write to a record another actor can touch is a finding. Query for lost updates directly: rows whose history shows a transition that a later write reversed within minutes (resolved to in_progress by a different actor). In integration tests, mutate the record between the agent's read and its write and assert the write is rejected.

## The fix
Treat memory as a hint and make the write prove the hint. Every mutating call carries a precondition: an etag or version (If-Match), a compare-and-swap on the status field, or a conditional update. The store rejects a stale precondition with an error that names the current version, and the agent's loop handles that error by re-reading the record and re-deciding, not by retrying the same write. A prompt rule such as "check the ticket first" is not a substitute: the check and the write are two calls, and the race lives between them.
```python
store.put("ticket-77", {"status": "in_progress", "assignee": "agent"},
          expect={"ticket-77": belief["version"]})
```

## How it still bites
A precondition on the row being written does not cover beliefs about other rows: in repro/MEM-05.py the agent decommissions srv-b because memory says srv-a is up; srv-a goes down in the meantime, the write to srv-b carries a correct version for srv-b, and the fleet ends with both servers out. The precondition has to cover the read set (every record the decision depended on), which means the agent harness must track which reads fed which write. Separately, a refused write only helps if the agent re-reads before re-deciding; harnesses that auto-retry the same payload on a version conflict reintroduce the original bug with an extra round trip.
