"""MEM-02: a keyword-stuffed document wins unnormalized lexical retrieval for every query."""
import math
from collections import Counter

DOCS = {
    "rotate-key": "how to rotate the api key for the billing service",
    "reset-pass": "reset a user password from the admin console",
    "export-csv": "export invoices as csv from the reports page",
    "set-webhook": "configure a webhook endpoint for payment events",
    "add-seat": "add a seat to the team plan in settings",
    "close-acct": "close an account and delete stored data",
    "enable-sso": "enable single sign on with your identity provider",
    "tune-alerts": "tune alert thresholds for the on call rotation",
}
QUERIES = {
    "rotate-key": "rotate api key billing",
    "reset-pass": "reset user password admin",
    "export-csv": "export invoices csv reports",
    "set-webhook": "webhook endpoint payment events",
    "add-seat": "add seat team plan",
    "close-acct": "close account delete data",
    "enable-sso": "enable single sign identity",
    "tune-alerts": "tune alert thresholds rotation",
}
terms = sorted({t for q in QUERIES.values() for t in q.split()})
DOCS["stuffed"] = " ".join(terms * 4)


def vec(text):
    return Counter(text.split())


def raw_score(q, d):
    dv = vec(d)
    return sum(dv[t] for t in set(q.split()))


def cosine(q, d):
    dv, qv = vec(d), Counter(set(q.split()))
    dot = sum(dv[t] * w for t, w in qv.items())
    return dot / (math.sqrt(sum(v * v for v in dv.values())) * math.sqrt(sum(v * v for v in qv.values())))


def top1(score, q, docs):
    return max(docs, key=lambda k: score(q, docs[k]))


def hub_report(winners, threshold=0.5):
    counts = Counter(winners)
    return {k for k, n in counts.items() if n / len(winners) > threshold}


raw_winners = [top1(raw_score, q, DOCS) for q in QUERIES.values()]
assert raw_winners.count("stuffed") == 8
print("FAILURE: raw term-count score ranks the stuffed doc first for %d of %d unrelated queries"
      % (raw_winners.count("stuffed"), len(QUERIES)))

cos_winners = [top1(cosine, q, DOCS) for q in QUERIES.values()]
assert cos_winners == list(QUERIES)
print("FIXED (length-normalized cosine): each query's top-1 is its own doc, stuffed doc wins %d"
      % cos_winners.count("stuffed"))

assert hub_report(raw_winners) == {"stuffed"} and hub_report(cos_winners) == set()
print("FIXED (hub detector): doc retrieved top-1 for >50%% of logged queries: %s; after the fix: none"
      % sorted(hub_report(raw_winners)))

filler = "background filler words about unrelated operations"
runbook = DOCS["rotate-key"] + " " + " ".join([filler] * 70)
words = len(runbook.split())
stub = "rotate api key"
q = QUERIES["rotate-key"]
assert cosine(q, stub) > cosine(q, runbook) and words > 400
print("RESIDUAL: cosine scores a 3-word stub %.2f and the real %d-word runbook %.2f for %r"
      % (cosine(q, stub), words, cosine(q, runbook), q))
