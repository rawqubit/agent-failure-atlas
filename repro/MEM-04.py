"""MEM-04: a response cache keyed by prompt text serves one tenant's answer to another."""
import hashlib

POLICY = {
    "acme": {"refund policy": "Refunds within 30 days.", "salary bands": "Managers only: L5 120-150k."},
    "globex": {"refund policy": "Refunds within 14 days.", "salary bands": "Managers only: L5 90-110k."},
}
ROLE = {("acme", "alice"): "manager", ("acme", "bob"): "employee", ("globex", "carol"): "employee"}


def retrieve(tenant, user, question):
    doc = POLICY[tenant][question]
    if doc.startswith("Managers only") and ROLE[(tenant, user)] != "manager":
        return None
    return doc


def h(*parts):
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


class Agent:
    def __init__(self, key_fn):
        self.cache, self.key_fn, self.model_calls = {}, key_fn, 0

    def answer(self, tenant, user, question):
        key = self.key_fn(tenant, user, question)
        if key in self.cache:
            return self.cache[key]
        context = retrieve(tenant, user, question)
        self.model_calls += 1
        reply = "I cannot find that." if context is None else "Answer: " + context
        self.cache[key] = reply
        return reply


def prompt_only(tenant, user, question):
    return h(question)


def tenant_only(tenant, user, question):
    return h(tenant, question)


def tenant_and_acl(tenant, user, question):
    return h(tenant, ROLE[(tenant, user)], question)


agent = Agent(prompt_only)
agent.answer("acme", "alice", "refund policy")
leak = agent.answer("globex", "carol", "refund policy")
assert leak == "Answer: Refunds within 30 days."
print("FAILURE: globex user got acme's answer from cache: %r (model calls: %d)" % (leak, agent.model_calls))

agent = Agent(tenant_only)
agent.answer("acme", "alice", "refund policy")
assert agent.answer("globex", "carol", "refund policy") == "Answer: Refunds within 14 days."
agent.answer("acme", "alice", "salary bands")
leak = agent.answer("acme", "bob", "salary bands")
assert leak == "Answer: Managers only: L5 120-150k."
print("RESIDUAL: tenant-keyed cache fixed the cross-tenant case, but acme employee bob got the managers-only answer: %r" % leak)

agent = Agent(tenant_and_acl)
agent.answer("acme", "alice", "refund policy")
assert agent.answer("globex", "carol", "refund policy") == "Answer: Refunds within 14 days."
agent.answer("acme", "alice", "salary bands")
assert agent.answer("acme", "bob", "salary bands") == "I cannot find that."
print("FIXED: key includes tenant and role; globex gets 14 days, bob is refused (model calls: %d)" % agent.model_calls)

principals = [(t, u) for (t, u) in ROLE]
questions = ["refund policy", "salary bands"]
seen = {}
for t, u in principals:
    for q in questions:
        k = tenant_and_acl(t, u, q)
        seen.setdefault(k, set()).add((t, u))
cross = [k for k, owners in seen.items() if len({t for t, _ in owners}) > 1]
assert cross == []
print("FIXED: key-collision test over %d principals x %d questions found %d cross-tenant collisions"
      % (len(principals), len(questions), len(cross)))
