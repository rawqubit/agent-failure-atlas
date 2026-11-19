"""TOOL-02: the model has no order_id, so it fills the schema's example; the validator accepts it."""
import re

ORDERS = {
    "ord_1001": {"owner": "cust_9", "cents": 12000},
    "ord_2044": {"owner": "cust_2", "cents": 4900},
}
PATTERN = r"^ord_\d{4}$"
EXAMPLE = "ord_1001"


def stub_model_fill():
    return EXAMPLE


def validate(order_id):
    return re.match(PATTERN, order_id) is not None


def refund_naive(order_id):
    assert validate(order_id)
    ORDERS[order_id]["refunded"] = True
    return ORDERS[order_id]["owner"]


class Session:
    def __init__(self, user):
        self.user, self.handles, self.refunds = user, {}, []

    def list_orders(self):
        for oid, o in ORDERS.items():
            if o["owner"] == self.user:
                self.handles["h%d" % (len(self.handles) + 1)] = oid
        return list(self.handles)

    def refund(self, handle):
        if handle not in self.handles:
            return {"error": "unknown handle %r: call list_orders or ask_user" % handle}
        self.refunds.append(self.handles[handle])
        return {"ok": True}


def provenance_ok(value, conversation):
    return any(value in message for message in conversation)


CONVERSATION = ["user (cust_2): please refund my last order"]
order_id = stub_model_fill()
assert validate(order_id) and not provenance_ok(order_id, CONVERSATION)
owner = refund_naive(order_id)
assert owner == "cust_9"
print("FAILURE: schema validation passed %r; refunded an order owned by %s for caller cust_2" % (order_id, owner))

session = Session("cust_2")
reply = session.refund(stub_model_fill())
assert "error" in reply and session.refunds == []
action = "ask_user" if "ask_user" in reply["error"] else "retry"
print("FIXED: fabricated id rejected (%s); model falls back to %s; refunds: %s" % (reply["error"], action, session.refunds))

handles = session.list_orders()
assert session.refund(handles[0]) == {"ok": True} and session.refunds == ["ord_2044"]
print("FIXED: handle from list_orders accepted, refunded %s (owned by cust_2)" % session.refunds)
