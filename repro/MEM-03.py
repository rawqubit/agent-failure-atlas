"""MEM-03: stale fact outranks its correction when retrieval scores similarity plus access count."""
import math

DAY = 1
NOW = 800 * DAY


def toks(s):
    return set(s.lower().replace("_", " ").split())


def sim(a, b):
    return len(a & b) / len(a | b)


class Store:
    def __init__(self, supersede=False, recency=0.0):
        self.rows, self.supersede, self.recency = [], supersede, recency

    def write(self, entity, attribute, value, day):
        if self.supersede:
            for r in self.rows:
                if (r["entity"], r["attribute"]) == (entity, attribute) and r["valid_to"] is None:
                    r["valid_to"] = day
        self.rows.append({"entity": entity, "attribute": attribute, "value": value, "day": day,
                          "access": 0, "valid_to": None})

    def search(self, query):
        q = toks(query)
        live = [r for r in self.rows if r["valid_to"] is None]
        def score(r):
            s = sim(q, toks(r["entity"] + " " + r["attribute"]))
            s += 0.1 * math.log1p(r["access"])
            s -= self.recency * (NOW - r["day"]) / 365
            return s
        ranked = sorted(live, key=score, reverse=True)
        ranked[0]["access"] += 1
        return ranked


def seed(store, old_attr="shipping_address", new_attr="shipping_address"):
    store.write("user", old_attr, "12 Oak St", day=0)
    for _ in range(40):
        store.search("user shipping address")
    store.write("user", new_attr, "9 Pine Ave", day=NOW - 1)


naive = Store()
seed(naive)
answer = naive.search("what is the user's shipping address")[0]
assert answer["value"] == "12 Oak St"
print("FAILURE: top-1 for the shipping address is %r, written %d days ago; correction written %d day ago has access=0"
      % (answer["value"], NOW - answer["day"], 1))

fixed = Store(supersede=True)
seed(fixed)
answer = fixed.search("what is the user's shipping address")[0]
live = [r["value"] for r in fixed.rows if r["valid_to"] is None]
assert answer["value"] == "9 Pine Ave" and live == ["9 Pine Ave"]
print("FIXED (supersede on write): top-1 is %r, live rows %s, history rows kept: %d"
      % (answer["value"], live, len(fixed.rows)))

scored = Store(recency=0.5)
seed(scored)
answer = scored.search("what is the user's shipping address")[0]
print("INFO (recency term only, 0.5 per year): top-1 is %r because 40 reads add %.2f and 800 days cost %.2f"
      % (answer["value"], 0.1 * math.log1p(40), 0.5 * 799 / 365))

drift = Store(supersede=True)
seed(drift, old_attr="shipping_address", new_attr="ship_to_address")
live = sorted(r["value"] for r in drift.rows if r["valid_to"] is None)
assert live == ["12 Oak St", "9 Pine Ave"]
top = drift.search("what is the user's shipping address")[0]["value"]
assert top == "12 Oak St"
print("RESIDUAL: new write used key 'ship_to_address', supersede did not fire, live rows are %s and top-1 is %r" % (live, top))
