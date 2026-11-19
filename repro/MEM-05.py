"""MEM-05: the agent writes on remembered state; a version precondition makes stale beliefs fail loudly."""


class PreconditionFailed(Exception):
    pass


class Store:
    def __init__(self, data):
        self.data = {k: dict(v, version=1) for k, v in data.items()}

    def get(self, key):
        return dict(self.data[key])

    def put(self, key, fields, expect=None):
        for k, v in (expect or {}).items():
            if self.data[k]["version"] != v:
                raise PreconditionFailed("%s is at version %d, caller expected %d"
                                         % (k, self.data[k]["version"], v))
        self.data[key].update(fields)
        self.data[key]["version"] += 1


def teammate_resolves(store):
    store.put("ticket-77", {"status": "resolved", "assignee": "dana"})


def agent_claims(store, memory, guarded):
    belief = memory["ticket-77"]
    if belief["status"] != "open":
        return "skipped"
    expect = {"ticket-77": belief["version"]} if guarded else None
    try:
        store.put("ticket-77", {"status": "in_progress", "assignee": "agent"}, expect=expect)
    except PreconditionFailed as e:
        fresh = store.get("ticket-77")
        memory["ticket-77"] = fresh
        return "refused (%s); re-read status=%s" % (e, fresh["status"])
    return "wrote"


def fresh_world():
    store = Store({"ticket-77": {"status": "open", "assignee": None}})
    memory = {"ticket-77": store.get("ticket-77")}
    teammate_resolves(store)
    return store, memory


store, memory = fresh_world()
outcome = agent_claims(store, memory, guarded=False)
row = store.get("ticket-77")
assert outcome == "wrote" and row["status"] == "in_progress" and row["assignee"] == "agent"
print("FAILURE: memory said open (v1); store had resolved (v2); unguarded write set status=%s assignee=%s, dana's resolution is gone"
      % (row["status"], row["assignee"]))

store, memory = fresh_world()
outcome = agent_claims(store, memory, guarded=True)
row = store.get("ticket-77")
assert outcome.startswith("refused") and row["status"] == "resolved" and memory["ticket-77"]["version"] == 2
print("FIXED: %s; store still status=%s assignee=%s" % (outcome, row["status"], row["assignee"]))
assert agent_claims(store, memory, guarded=True) == "skipped"
print("FIXED: after the re-read the agent skips the claim")


def decommission_b(store, memory, expect_keys):
    if memory["srv-a"]["state"] != "up":
        return "skipped"
    expect = {k: memory[k]["version"] for k in expect_keys}
    store.put("srv-b", {"state": "decommissioned"}, expect=expect)
    return "wrote"


def fleet():
    store = Store({"srv-a": {"state": "up"}, "srv-b": {"state": "up"}})
    memory = {k: store.get(k) for k in ("srv-a", "srv-b")}
    store.put("srv-a", {"state": "down"})
    return store, memory


store, memory = fleet()
assert decommission_b(store, memory, ["srv-b"]) == "wrote"
states = {k: store.get(k)["state"] for k in ("srv-a", "srv-b")}
assert "up" not in states.values()
print("RESIDUAL: precondition on the written row only passed; fleet is now %s because the belief about srv-a was never checked" % states)

store, memory = fleet()
try:
    decommission_b(store, memory, ["srv-a", "srv-b"])
    raise SystemExit("expected PreconditionFailed")
except PreconditionFailed as e:
    print("FIXED: read-set precondition caught it: %s" % e)
