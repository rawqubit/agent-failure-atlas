"""VERIFY-05: a recall-only metric ranks the padded answer above the concise correct one.

Selecting the best candidate by score stands in for optimisation pressure (RL, best-of-n, prompt search).
Claim extraction for F1 is assumed perfect here: claims arrive as (key, value) pairs.
"""
import re

FACTS = {"port": "8443", "timeout": "30s", "region": "eu-west-1", "retries": "3", "tls": "1.3"}
DECOYS = {"port": ["80", "9999"], "timeout": ["5s", "90s"], "region": ["us-east-1", "ap-south-1"],
          "retries": ["7", "12"], "tls": ["1.0", "1.1"]}

def text_of(claims):
    return "; ".join(f"{k} is {v}" for k, v in claims)

def recall_score(claims):
    tokens = set(re.findall(r"[\w.\-]+", text_of(claims)))
    return sum(v in tokens for v in FACTS.values()) / len(FACTS)

def f1_score(claims):
    right = {c for c in claims if FACTS[c[0]] == c[1]}
    p, r = len(right) / len(claims), len(right) / len(FACTS)
    return 2 * p * r / (p + r) if p + r else 0.0

concise = [(k, v) for k, v in FACTS.items() if k != "tls"]
padded = [(k, v) for k in FACTS for v in [FACTS[k]] + DECOYS[k]]
candidates = {"concise": concise, "padded": padded}

for name, claims in candidates.items():
    print("%-8s claims=%2d recall=%.2f f1=%.2f" % (name, len(claims), recall_score(claims), f1_score(claims)))
by_recall = max(candidates, key=lambda n: recall_score(candidates[n]))
by_f1 = max(candidates, key=lambda n: f1_score(candidates[n]))
print("FAILURE: recall picks %r (%d claims, %d wrong)" % (by_recall, len(padded), len(padded) - 5))
print("FIXED: F1 picks %r (%d claims, 0 wrong)" % (by_f1, len(concise)))
assert by_recall == "padded" and by_f1 == "concise"
