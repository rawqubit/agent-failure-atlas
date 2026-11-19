"""TOOL-08: the batch tool is truthful (per-item statuses) but the adapter reads only the top-level status."""


class PartialSuccess(Exception):
    def __init__(self, succeeded, failed):
        super().__init__("%d of %d items failed: %s" % (len(failed), len(succeeded) + len(failed), failed))
        self.succeeded, self.failed = succeeded, failed


def bulk_update(ids, locked):
    results = [{"id": i, "status": 409 if i in locked else 200} for i in ids]
    return {"status": "ok", "results": results}


def naive_adapter(resp):
    return {"updated": len(resp["results"])} if resp["status"] == "ok" else {"updated": 0}


def strict_adapter(resp):
    ok = [r["id"] for r in resp["results"] if 200 <= r["status"] < 300]
    bad = [r["id"] for r in resp["results"] if not 200 <= r["status"] < 300]
    if bad:
        raise PartialSuccess(ok, bad)
    return {"updated": len(ok)}


def agent(adapter, resp, total):
    try:
        out = adapter(resp)
    except PartialSuccess as e:
        return "updated %d of %d; failed ids %s" % (len(e.succeeded), total, e.failed)
    return "updated %d of %d" % (out["updated"], total)


ids = list(range(1, 11))
resp = bulk_update(ids, locked={3, 6, 9})
assert resp["status"] == "ok"
said = agent(naive_adapter, resp, len(ids))
assert said == "updated 10 of 10"
print("FAILURE: top-level status ok, agent reported:", said, "| actually applied:", sum(r["status"] == 200 for r in resp["results"]))

said = agent(strict_adapter, resp, len(ids))
assert said == "updated 7 of 10; failed ids [3, 6, 9]"
print("FIXED:", said)

clean = bulk_update(ids, locked=set())
assert agent(strict_adapter, clean, len(ids)) == "updated 10 of 10"
print("FIXED: a fully successful batch still reports 10 of 10")
