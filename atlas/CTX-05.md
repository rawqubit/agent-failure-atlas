---
id: CTX-05
title: Two versions of the same file sit in context and the edit is written against the stale one
category: context
severity: medium
frequency: common
symptom: An edit fails with old_string not found, or succeeds and silently reverts a change the agent made a few turns earlier
stage: tool-execution
tags: stale-context, file-editing, versioning, coding-agents
---

## What you see
Turn 3 reads `config.ini`. Turn 7 changes `retries = 3` to `retries = 5`. At turn 12 the agent edits the same file: first a `str_replace` that returns `ERROR: old_string not found`, then a `write_file` that returns ok. The diff at the end of the run shows `retries = 3` again, and the test that depended on 5 fails with no edit in the history that mentions reverting it.

## Why it happens
The harness treats every tool result as an immutable fact about the world, but a file read is a snapshot that stops being true the moment anything writes the file. Both snapshots stay in context, with equal standing and no marker saying which is current. When the model composes an old_string or a whole-file rewrite, it copies from one of them, and nothing makes it the newer one. Copying from the stale read gives a str_replace that misses, which is the loud case. The quiet case follows: after the miss, a common recovery is to rewrite the whole file, and a whole-file write built from a stale copy overwrites every change made since, including the agent's own.

## Minimal reproduction
The model is a stub that builds its edit from the first read of the file in context and falls back to rewriting the whole file when str_replace misses; real models may copy from either snapshot.
```python
class Editor:
    def __init__(self, text):
        self.text = text
    def str_replace(self, old, new):
        if self.text.count(old) != 1:
            return "ERROR: old_string not found"
        self.text = self.text.replace(old, new)
        return "ok"
    def write_file(self, text):
        self.text = text
        return "ok"

def model_set_timeout(context, ed):
    old = "\n".join(context[0].splitlines()[1:3])
    if ed.str_replace(old, old.replace("30", "10")) != "ok":
        ed.write_file(context[0].replace("timeout = 30", "timeout = 10"))

def session(refresh):
    ed = Editor("host = a\ntimeout = 30\nretries = 3\n")
    context = [ed.text]
    ed.str_replace("retries = 3", "retries = 5")
    return ed, [ed.text] if refresh else context

ed, ctx = session(refresh=False)
model_set_timeout(ctx, ed)
assert "retries = 3" in ed.text
print("FAILURE: stale read -> str_replace missed -> write_file reverted retries 5 -> 3, no error")

ed, ctx = session(refresh=True)
model_set_timeout(ctx, ed)
assert ed.text == "host = a\ntimeout = 10\nretries = 5\n"
print("FIXED: reads of a modified path replaced by the latest version; retries stays 5")
```
The same code, with a third case where a base digest makes a stale write_file fail, is in repro/CTX-05.py.

## Detection
Track file versions in the harness: for each path, record a content hash at every read and every write, and log `stale_read_used` whenever an edit or write is issued while the newest read of that path is older than the newest write. Count `str_replace` misses per run; two misses on one path in a window of ten turns is the signature of this failure, because the model is guessing at content it no longer has. A replay test also catches it: script a read, an edit, and a second edit that quotes the first read, and assert the final file still contains the first edit.

## The fix
Fix the context and fix the tool, because either alone leaves a hole. In context, when a path is written, replace every earlier read result for it with the current content (or a stub that says the content moved on), so the model has one version to copy from. In the tool, make `write_file` take the content hash the model last saw and reject a mismatch with the diff between that version and the current file; make `str_replace` misses return the current region around the nearest match instead of a bare error.
```python
def write_file(self, text, base):
    if base != self.digest():
        return f"ERROR: file changed since you read it ({base} -> {self.digest()}); re-read"
```
Rejecting is the correct default because the model cannot tell from inside its own context that the version it holds is old.

## How it still bites
The context fix only sees writes the harness performed. A formatter on save, a test run that regenerates a snapshot file, a shell tool running `sed`, or another agent in the same checkout all change the file without touching your read cache, so the base-hash check is the only thing that catches them, and it works only if every write path carries the hash. The model's own earlier messages also quote file content in plain text, and no invalidation pass reaches those quotes.
