---
id: SEC-03
title: A path check that looks right lets file tools escape the sandbox
category: security
severity: high
frequency: occasional
symptom: read_file returns contents of a file outside the workspace while the log line says the path passed the sandbox check
stage: tool-execution
tags: path-traversal, sandbox, symlink, file-tools
---

## What you see
`read_file("docs/key.txt")` returns the contents of a file that lives outside the workspace, and the log line says `path ok` with a path under the sandbox root. The logged string is the one the check saw, not the file the kernel opened. In the repro the `startswith` check lets 2 of 3 escapes through (a sibling directory named `sandbox-evil` and a symlink named `docs`) and blocks only `../../etc/passwd`, the case most test suites cover.

## Why it happens
The check is a string operation and the access is a filesystem operation, and the two disagree in three places. `startswith` compares characters, not path components, so `/tmp/sandbox-evil` begins with `/tmp/sandbox`. `abspath` collapses `..` lexically without consulting the filesystem, so a symlink inside the sandbox stays a directory entry that the kernel follows to anywhere; the agent can create one itself through a write or shell tool, or a cloned repository can ship one. The root can be a symlink as well (a mounted volume, a `/tmp` that is a link), so a comparison that resolves only one side rejects legitimate paths. The assumption that breaks is that the path string that was checked names the file that `open()` will reach.

## Minimal reproduction
```python
import os, tempfile

def naive_ok(root, rel):
    return os.path.abspath(os.path.join(root, rel)).startswith(root)

def safe_ok(root, rel):
    real = os.path.realpath(os.path.join(root, rel))
    return os.path.commonpath([os.path.realpath(root), real]) == os.path.realpath(root)

with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "sandbox")
    for d in ("sandbox", "sandbox-evil", "outside"):
        os.mkdir(os.path.join(tmp, d))
    os.symlink(os.path.join(tmp, "outside"), os.path.join(root, "docs"))
    attacks = ["../sandbox-evil/key.txt", "docs/key.txt", "../../etc/passwd"]
    naive = [a for a in attacks if naive_ok(root, a)]
    assert naive == attacks[:2]
    print("FAILURE: naive check allowed", naive, "and only blocked", attacks[2])
    safe = [a for a in attacks if safe_ok(root, a)]
    assert safe == [] and safe_ok(root, "notes/todo.txt")
    print("FIXED: realpath+commonpath allowed", safe, "and still allows notes/todo.txt")
```
The full version reads real files through both checkers and also covers in-sandbox symlinks, a symlinked root, and O_NOFOLLOW; it is in repro/SEC-03.py.

## Detection
Write the test with a real directory tree rather than string fixtures: a sibling directory sharing the root's prefix, a symlink inside the root that points outside it, and a file behind each, then assert that every file tool (read, write, list, glob, delete) refuses all of them. At runtime log `os.path.realpath` of every opened path next to the requested path and alert when the resolved path is not under `realpath(root)`. Also flag creation of any symlink in the workspace whose target resolves outside it, since that is the setup step for the escape.

## The fix
Resolve first, then compare whole path components on the resolved values, and open the resolved path without following a final symlink.
```python
real_root = os.path.realpath(root)
real = os.path.realpath(os.path.join(root, rel))
if os.path.commonpath([real_root, real]) != real_root:
    raise PermissionError(rel)
fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW)
```
`commonpath` works on components, so `sandbox-evil` no longer matches `sandbox`, and `realpath` on both sides makes links irrelevant. In the repro, an in-sandbox symlink and a symlinked root still work. This is defence in depth; a container or mount namespace that contains only the workspace removes the class, because the escaping path then has nothing to reach.

## How it still bites
Check and open are two separate syscalls, so an agent that can write files can swap a directory component for a symlink between them; `O_NOFOLLOW` covers only the final component, and closing the rest means opening component by component with `dir_fd`. The check also protects only the tools that call it: the same agent's shell tool runs `cat ../secrets` without ever touching your path logic.
