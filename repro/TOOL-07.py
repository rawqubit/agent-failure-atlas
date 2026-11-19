"""TOOL-07: the order deploy-after-migrate exists only in a runbook, so the tool server accepts deploy first and ships a crash-looping release.

The model is a stub: it calls tools in registry order (deploy first, because the task verb is 'ship') and, when a tool
returns a structured precondition error naming a missing tool, calls that tool and retries. It is not evidence about real models.
"""


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
            return {"error": "precondition_failed", "missing": "run_migration",
                    "hint": "call run_migration, then deploy"}
        self.health = "healthy" if self.migrated else "crashloop: column orders.currency does not exist"
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
assert server.calls == ["deploy", "run_migration"] and server.migrated
assert server.health.startswith("crashloop")
print("FAILURE: every call returned ok, order", server.calls, "-> health:", server.health)

server = ReleaseServer(enforce=True)
stub_model(server, ["deploy", "run_migration"])
assert server.calls == ["deploy", "run_migration", "deploy"]
assert server.health == "healthy"
print("FIXED: order", server.calls, "-> health:", server.health)
