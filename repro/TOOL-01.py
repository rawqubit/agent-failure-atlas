"""TOOL-01: upstream renames total_cents to amount_cents; a lenient .get turns it into a silent zero."""
ADVERTISED = {"required": ["id", "total_cents", "currency"]}
LIVE = {"id": "ord_77", "amount_cents": 4900, "currency": "usd"}


class SchemaDrift(Exception):
    pass


def total_lenient(payload):
    return payload.get("total_cents", 0)


def parse_strict(payload, schema):
    missing = [k for k in schema["required"] if k not in payload]
    unadvertised = [k for k in payload if k not in schema["required"]]
    if missing:
        raise SchemaDrift("missing %s, unadvertised %s" % (missing, unadvertised))
    return payload


def contract_test(live_sample, schema):
    missing = sorted(set(schema["required"]) - set(live_sample))
    unadvertised = sorted(set(live_sample) - set(schema["required"]))
    return missing, unadvertised


answer = "Order %s total: $%.2f" % (LIVE["id"], total_lenient(LIVE) / 100)
assert answer.endswith("$0.00") and LIVE["amount_cents"] == 4900
print("FAILURE: payload holds amount_cents=4900, agent answers: %s" % answer)

try:
    parse_strict(LIVE, ADVERTISED)
except SchemaDrift as e:
    print("FIXED: strict parse refuses the payload: SchemaDrift(%s)" % e)
else:
    raise AssertionError("strict parse accepted a payload missing total_cents")

missing, unadvertised = contract_test(LIVE, ADVERTISED)
assert missing == ["total_cents"] and unadvertised == ["amount_cents"]
print("FIXED: contract test fails in CI before any user asks: missing=%s unadvertised=%s" % (missing, unadvertised))

DRIFTED_UNIT = {"id": "ord_77", "total_cents": 49.0, "currency": "usd"}
parse_strict(DRIFTED_UNIT, ADVERTISED)
print("STILL BITES: same key, dollars instead of cents, strict parse passes: total_cents=%s" % DRIFTED_UNIT["total_cents"])
