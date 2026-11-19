"""CTX-06: a rolling summary keeps 'deploy branch = release-4' after turn 60 changed it to release-5.

The summarizer is a STUB with one modelled property: it carries the previous summary forward as
established and skips a new statement about a topic the summary already covers (a concise summary does
not repeat itself). The extractor is the same regex in both variants; only the storage differs.
"""
import re

FACT = re.compile(r"the (deploy branch) is (?:now )?(release-\d+)")
NOISE = "ran the tests, nothing to report"
turns = [(t, NOISE) for t in range(1, 71)]
turns[2] = (3, "the deploy branch is release-4")
turns[59] = (60, "heads up, the deploy branch is now release-5")


def extract(text):
    m = FACT.search(text)
    return (m.group(1), m.group(2)) if m else None


def roll(prev, window):
    out = list(prev)
    for turn, text in window:
        fact = extract(text)
        if fact and not any(fact[0] in line for line in out):
            out.append(f"{fact[0]} = {fact[1]}")
    return out


summary = []
for i in range(0, 70, 10):
    summary = roll(summary, turns[i : i + 10])
assert summary == ["deploy branch = release-4"]
print(f"FAILURE: after 7 rolls the summary says {summary[0]!r}; turn 60 said release-5; the next deploy would target the wrong branch")


def ledger_update(ledger, turns, observed_at="2026-11-19"):
    for turn, text in turns:
        fact = extract(text)
        if not fact:
            continue
        key, value = fact
        if key not in ledger or turn > ledger[key][1]:
            ledger[key] = (value, turn, observed_at)
    return ledger


def render(ledger):
    return [f"{k} = {v} (turn {t}, observed {o})" for k, (v, t, o) in sorted(ledger.items())]


ledger = {}
for i in range(0, 70, 10):
    ledger_update(ledger, turns[i : i + 10])
summary = render(ledger)
assert summary == ["deploy branch = release-5 (turn 60, observed 2026-11-19)"]
reordered = ledger_update({}, list(reversed(turns)))
assert render(reordered) == summary
print("FIXED: facts keyed with (value, source turn, observed_at); summary rendered from the ledger:", summary[0])
