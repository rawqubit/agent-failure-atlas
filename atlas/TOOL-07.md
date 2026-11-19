---
id: TOOL-07
title: The agent calls tools in the wrong order because a prerequisite is nowhere in the tool contract
category: tool-use
severity: high
frequency: common
symptom: Every tool call returns ok, the agent reports the release shipped, and the service is crash-looping against a schema that was never migrated
stage: tool-execution
tags: tool-contracts, preconditions, ordering, state-machines
---

## What you see
The trace is clean: `deploy` returns `{"ok": true, "status": "accepted"}`, `run_migration` returns `{"ok": true}`, and the agent writes "release shipped". The health endpoint says `crashloop: column orders.currency does not exist`, and it says so because the migration ran after the new code had already started booting. Nobody sees an error until the on-call opens the service dashboard, and the agent's transcript contains no failure to search for.

## Why it happens
The order "migrate, then deploy" is real, but it lives in a runbook and in the system prompt, not in the tools. From the model's side each tool is an independent verb with a description, and the registry lists `deploy` first and the task says "ship the release", so `deploy` is the natural first call. The server accepts any call in any state: `deploy` is asynchronous and returns `accepted` without checking what the code needs from the database, so the wrong order produces a success response. That is what makes the failure quiet: a precondition that is checked nowhere cannot be reported anywhere. Prompt-level ordering instructions compete with every other instruction in a long context, and nothing enforces them at the moment of the call.

## Minimal reproduction
```python
class ReleaseServer:
    def __init__(self, enforce):
        self.enforce, self.migrated, self.health, self.calls = enforce, False, None, []
    def run_migration(self):
        self.calls.append("run_migration")
        self.migrated = True
        return {"ok": True}
    def deploy(self):
        self.calls.append("deploy")
        if self.enforce and not self.migrated:
            return {"error": "precondition_failed", "missing": "run_migration"}
        self.health = "healthy" if self.migrated else "crashloop: orders.currency missing"
        return {"ok": True, "status": "accepted"}

def stub_model(server, tools):
    pending, done = list(tools), set()
    while pending:
        name = pending.pop(0)
        if name in done:
            continue
        result = getattr(server, name)()
        if "missing" in result:
            pending[:0] = [result["missing"], name]
        else:
            done.add(name)

server = ReleaseServer(enforce=False)
stub_model(server, ["deploy", "run_migration"])
assert server.health.startswith("crashloop")
print("FAILURE: calls", server.calls, "all returned ok -> health:", server.health)
server = ReleaseServer(enforce=True)
stub_model(server, ["deploy", "run_migration"])
assert server.health == "healthy"
print("FIXED: calls", server.calls, "-> health:", server.health)
```
The model is a stub that calls tools in registry order and follows a structured precondition error; it demonstrates the server side of the mechanism and says nothing about how real models order calls. The full version is repro/TOOL-07.py.

## Detection
Replay your agent's tool-call sequences against a table of required orderings and count violations: for every pair `(A before B)` in the table, any trace where B appears without a prior successful A in the same run is a hit. Add a post-condition check to the tools that return `accepted`: a `deploy` span should be followed by a health read, and a task whose last observed health is not `healthy` must not end in a success message. In pre-release tests, run the agent with the tool list shuffled several times and assert the end state is identical; an agent that only works with one registry order is relying on an ordering you have not written down.

## The fix
Move the ordering into the tool server as a state machine. Each tool declares the states it may run in, and a call in the wrong state is rejected with an error that names the missing prerequisite and the tool that satisfies it. The rejection costs one extra round trip and the model's recovery is mechanical, because the error contains the next action.
```python
if not self.migrated:
    return {"error": "precondition_failed", "missing": "run_migration",
            "hint": "call run_migration, then deploy"}
```
The state has to be real server state, such as a recorded migration version, and not a flag the model can set by calling a tool; otherwise the state machine merely relocates the honor system.

## How it still bites
A precondition that the server cannot observe is still unenforceable: "the migration is backward compatible with the running version" or "the cache was warmed" has no field to check, so those orderings stay in docs and keep failing quietly. A second residual is staleness, where the precondition held when the check ran and stopped holding before the effect landed, such as a migration rolled back between the check and the deploy; the check and the action need to happen in one server-side transaction.
