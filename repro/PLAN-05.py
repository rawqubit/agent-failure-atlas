"""PLAN-05: a plan generated once keeps running after step 1 invalidates steps 2-4."""
TICKETS = {"1042": {"status": "closed-duplicate-of:1001"}, "1001": {"status": "open"}}


def make_plan(ticket, effects):
    return [
        ("lookup", lambda: TICKETS[ticket], lambda r: r["status"] == "open"),
        ("assign", lambda: effects.append(("assign", ticket)), lambda r: True),
        ("set_priority", lambda: effects.append(("set_priority", ticket)), lambda r: True),
        ("notify_customer", lambda: effects.append(("notify_customer", ticket)), lambda r: True),
    ]


def execute(ticket, validate):
    effects, plan, i, replans = [], None, 0, 0
    plan = make_plan(ticket, effects)
    while i < len(plan):
        name, fn, post = plan[i]
        result = fn()
        if validate and not post(result):
            replans += 1
            assert replans <= 2, "escalate to a human"
            status = result["status"]
            assert status.startswith("closed-duplicate-of:")
            ticket = status.split(":")[1]
            plan, i = make_plan(ticket, effects), 0
            continue
        i += 1
    return effects, replans


effects, _ = execute("1042", validate=False)
assert [t for _, t in effects] == ["1042"] * 3
print("FAILURE: ticket 1042 is a closed duplicate, executor still ran %d side effects on it: %s" % (len(effects), effects))

effects, replans = execute("1042", validate=True)
assert all(t == "1001" for _, t in effects) and len(effects) == 3 and replans == 1
print("FIXED: postcondition on step 1 failed, re-planned %d time, side effects on 1042: 0, on 1001: %d" % (replans, len(effects)))
