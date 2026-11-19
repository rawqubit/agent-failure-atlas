---
id: SEC-02
title: The agent acts with its own service account's permissions instead of the requesting user's
category: security
severity: critical
frequency: common
symptom: A user gets another user's document by asking for it, and the data-layer audit log shows only agent-svc as the reader
stage: tool-execution
tags: confused-deputy, authorization, service-account, on-behalf-of
---

## What you see
A support user asks the agent for "the Q3 comp review" and gets back someone else's document. The data store's audit log records the read as `actor=agent-svc`, so it looks like ordinary automated traffic and the 403s you would expect never appear. In the repro, bob asks for alice's `doc-a` and receives its contents, and the audit entry is `("agent-svc", "doc-a")`.

## Why it happens
The agent was given one service credential because that was the cheapest way to let it reach everything it might need, including a nightly indexer that really does need read-all. The tool authenticates to the store as the agent, and the store authorizes the agent, which is allowed, so every check passes. Who asked is a fact that exists only in the chat session upstream of the tool, and nothing carries it across the tool boundary. The assumption that breaks is that "the agent is permitted" implies "the person talking to the agent is permitted", and any user can now borrow the agent's authority just by phrasing a request. This is the classic confused deputy, and a prompt line such as "only show users their own documents" does not repair it because the model neither knows reliably whose document it is nor holds up under a persistent user.

## Minimal reproduction
```python
import hmac, hashlib

sign = lambda user: hmac.new(b"issuer-key", user.encode(), hashlib.sha256).hexdigest()

class Store:
    owner = {"doc-a": "alice", "doc-b": "bob"}
    def read(self, doc, user, sig):
        if not hmac.compare_digest(sig, sign(user)):
            raise PermissionError("bad token")
        if user == self.owner[doc] or user == "agent-svc":
            return f"contents of {doc}"
        raise PermissionError(f"{user} may not read {doc}")

def read_doc_tool(doc, session, own_cred, obo):
    user, sig = session if obo else own_cred
    return Store().read(doc, user, sig)

bob_session = ("bob", sign("bob"))
agent_cred = ("agent-svc", sign("agent-svc"))
leak = read_doc_tool("doc-a", bob_session, agent_cred, obo=False)
assert leak == "contents of doc-a"
print("FAILURE: bob asked for alice's doc and got:", leak)
try:
    read_doc_tool("doc-a", bob_session, agent_cred, obo=True)
except PermissionError as e:
    print("FIXED: on-behalf-of read denied:", e)
else:
    raise AssertionError("bob read alice's doc")
```
The fuller version with an audit log, bob's legitimate read and a forged-token case is in repro/SEC-02.py.

## Detection
Record both `actor` (the credential) and `subject` (the end user) on every data-layer read, and run a nightly job that replays each agent-originated read against the ACL using the subject. Any read where the subject lacks access is a page, and any agent read with a null subject is a bug in its own right. In tests, parametrize every tool over a user with no access to the target resource and assert `PermissionError`; a tool that passes that test only because the fixture user is an admin is the usual miss.

## The fix
Mint a delegated credential when the session starts (an OAuth token exchange, or any signed token whose subject is the user and whose audience is the data service) and have the harness attach it to every tool call. The tool signature has no user argument, so the model can neither supply nor change the principal, and the store verifies the token and evaluates its ACL against `sub`.
```python
user, sig = session_token
store.read(doc_id, user, sig)
```
The check must live in the data layer. An `if user_can_read(doc)` in the agent's tool code protects only the code paths that remember to call it, while the store protects every caller, including the next tool someone adds.

## How it still bites
Derived data built with the service account sits outside the per-document check: a nightly embedding index holds chunks of every document, and a search tool answered from it returns snippets that no per-document read ever authorized. The ACL filter has to be applied inside the index query rather than to the top-k afterwards, and cached answers need the same treatment, see MEM-04.
