---
id: TOOL-06
title: Permission scopes only ever accumulate across a session until the agent holds more than any task needed
category: tool-use
severity: critical
frequency: occasional
symptom: A read-only task's token ends the session holding write and admin scopes, and a destructive call succeeds without ever returning a 403
stage: tool-execution
tags: permissions, oauth-scopes, least-privilege, credentials
---

## What you see
The audit log for one session shows the same token id used for every call, and its scope list has grown: `tickets:read` at the start, then `+audit:read`, `+tickets:write` and `+admin:users` as each tool returned a 403. The task was "summarize open tickets". No human saw any of the three grants. Late in the run the model calls `delete_ticket` on a ticket it misread as spam, and the call succeeds on the first try, with no 403 in the trace to hint that a permission check was ever in play.

## Why it happens
The harness has a helpful rule: when a tool returns 403, request the missing scope from the broker and retry, so a long task does not stall on a permission it can obtain. That is a ratchet. Each grant is added to a single session token and nothing ever removes one, so the token's power is the union of every 403 the model ever provoked, and the model provokes them freely because every tool in the registry looks callable. The broken assumption is that a scope request expresses a need of the task. It expresses the model's curiosity or a wrong guess, and the broker, which only sees "agent asks for X", cannot tell the difference. Once `tickets:write` is on the token, the later destructive call is authorized without any request at all, so the one signal that could have been reviewed is never emitted.

## Minimal reproduction
```python
NEEDS = {"list_tickets": "tickets:read", "get_audit_log": "audit:read",
         "tag_ticket": "tickets:write", "list_users": "admin:users",
         "delete_ticket": "tickets:write"}

class Broker:
    def __init__(self, auto_grant):
        self.auto_grant, self.requests = auto_grant, []
    def request(self, token, scope):
        self.requests.append(scope)
        if self.auto_grant:
            token.add(scope)
        return self.auto_grant

def run_task(broker, declared):
    token, done = set(declared), []
    for call, scope in NEEDS.items():
        if scope in token or broker.request(token, scope):
            done.append(call)
    return token, done

broker = Broker(auto_grant=True)
token, done = run_task(broker, {"tickets:read"})
assert "delete_ticket" in done and "admin:users" in token
print("FAILURE: read-only task holds", sorted(token), "| requests:", broker.requests, "| delete allowed")
broker = Broker(auto_grant=False)
token, done = run_task(broker, {"tickets:read"})
assert token == {"tickets:read"} and "delete_ticket" not in done
print("FIXED: token", sorted(token), "| done:", done, "| requests needing a human:", broker.requests)
```
repro/TOOL-06.py adds a TTL and shows the next task inheriting the inflated token.

## Detection
Diff the scopes a token holds at its last use against the scopes the task declared at start; any non-empty difference is the finding, and the query is one `GROUP BY token_id` over the broker's grant log. Count escalation requests per task and alert on the first one that is auto-granted rather than human-approved. A cheap test: run every task type against a broker that denies all escalations and check that the task still completes, because a task that cannot finish without escalating has an under-declared scope that you want to know about at review time rather than in an audit. Also check scope-per-token across two consecutive tasks: they must not share a token id.

## The fix
Mint a token per task from the scopes that task declared when it was created, with a short TTL, and never extend it in place. Escalation is deny-by-default: the broker returns the 403 to the model as an ordinary error, and a grant requires an out-of-band human approval that names the scope and the task. The structural point is that the declaration lives in the task definition, which a person reviewed, and not in the session, which the model steers.
```python
token = broker.mint(task.declared_scopes, ttl=task.max_seconds)
```
An instruction like "only request scopes you truly need" does not help, since the harness, not the model, does the requesting and the model has no accurate picture of what it needs.

## How it still bites
Declared scopes are coarse, so a task that legitimately needs `tickets:write` to tag one ticket also gets the ability to delete every ticket; per-task tokens bound the union over time but not the breadth inside one scope. The pressure then moves to approvals: if a human sees an escalation prompt on every other task they start approving by reflex, and the approval loop quietly rebuilds the accumulation with a person's click in the middle.
