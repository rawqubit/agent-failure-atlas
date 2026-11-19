"""VERIFY-03: eval items double as few-shot exemplars, so the 'model' looks up the answer.

The stub copies the label of its closest exemplar when that exemplar shares >= 10 of 12 words with the item,
and otherwise guesses from text length parity. It models a model that has seen the item; it is not evidence about real models.
"""
import hashlib

def h(*parts):
    return int(hashlib.md5("-".join(map(str, parts)).encode()).hexdigest(), 16)

POOL = [{"id": i, "text": " ".join("w%d" % (h(i, k) % 400) for k in range(12)), "label": h(i, "y") % 2} for i in range(200)]

def overlap(a, b):
    return len(set(a.split()) & set(b.split()))

def accuracy(exemplars, eval_set):
    hits = 0
    for item in eval_set:
        top = max(exemplars, key=lambda ex: overlap(ex["text"], item["text"]))
        pred = top["label"] if overlap(top["text"], item["text"]) >= 10 else len(item["text"]) % 2
        hits += pred == item["label"]
    return hits / len(eval_set)

def ngrams(text, n=8):
    w = text.split()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}

def flagged(exemplars, eval_set):
    seen = set().union(*(ngrams(ex["text"]) for ex in exemplars))
    return sum(bool(ngrams(item["text"]) & seen) for item in eval_set)

dirty_eval = POOL[:50]
train = [x for x in POOL if h(x["id"], "split") % 4]
clean_eval = [x for x in POOL if not h(x["id"], "split") % 4]
print("FAILURE: contaminated eval scores %.0f%%, detector flags %d/%d" % (100 * accuracy(POOL, dirty_eval), flagged(POOL, dirty_eval), len(dirty_eval)))
print("FIXED: hash split scores %.0f%%, detector flags %d/%d" % (100 * accuracy(train, clean_eval), flagged(train, clean_eval), len(clean_eval)))
assert accuracy(POOL, dirty_eval) == 1.0 and flagged(POOL, dirty_eval) == len(dirty_eval)
assert accuracy(train, clean_eval) < 0.7 and flagged(train, clean_eval) == 0
