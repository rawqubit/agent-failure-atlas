"""TOOL-06: granting scopes on every 403 and never releasing them leaves a read-only task holding write and admin."""

NEEDS = {
    "list_tickets": "tickets:read",
    "get_audit_log": "audit:read",
    "tag_ticket": "tickets:write",
    "list_users": "admin:users",
    "delete_ticket": "tickets:write",
}
CALLS = ["list_tickets", "get_audit_log", "tag_ticket", "list_users", "delete_ticket"]


class Broker:
    def __init__(self, auto_grant):
        self.auto_grant, self.now, self.escalations = auto_grant, 0, []

    def mint(self, scopes, ttl):
        return {"scopes": set(scopes), "expires": self.now + ttl}

    def request(self, token, scope, human_ok=False):
        self.escalations.append(scope)
        if self.auto_grant or human_ok:
            token["scopes"].add(scope)
            return True
        return False


def run_task(broker, token):
    done, denied = [], []
    for call in CALLS:
        scope = NEEDS[call]
        if token["expires"] <= broker.now:
            denied.append(call)
        elif scope in token["scopes"] or broker.request(token, scope):
            done.append(call)
        else:
            denied.append(call)
    return done, denied


broker = Broker(auto_grant=True)
token = broker.mint({"tickets:read"}, ttl=100)
done, denied = run_task(broker, token)
assert token["scopes"] == {"tickets:read", "audit:read", "tickets:write", "admin:users"}
assert "delete_ticket" in done and broker.escalations == ["audit:read", "tickets:write", "admin:users"]
print("FAILURE: read-only task ended holding", sorted(token["scopes"]), "| delete_ticket allowed:", "delete_ticket" in done)
second = run_task(broker, token)[0]
assert "delete_ticket" in second
print("FAILURE: the next task reuses the token and deletes without any 403:", "delete_ticket" in second)

broker = Broker(auto_grant=False)
token = broker.mint({"tickets:read"}, ttl=100)
done, denied = run_task(broker, token)
assert token["scopes"] == {"tickets:read"} and done == ["list_tickets"] and "delete_ticket" in denied
print("FIXED: token scopes", sorted(token["scopes"]), "| done:", done, "| denied:", denied)

broker.now = 100
assert run_task(broker, token)[0] == []
print("FIXED: after the ttl the same token does nothing; the next task mints a fresh one from its own declaration")
