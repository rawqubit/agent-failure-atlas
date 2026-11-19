"""CTX-02: relevance-ranked compaction drops a rule that was stated once at turn 2.

The agent is a STUB: it can only honour a rule whose text is still in its context. Compaction keeps
the last N messages plus the older messages that share the most words with them.
"""
STOP = {"the", "a", "to", "on", "in", "and", "of", "is", "for", "against"}


def words(text):
    return {w for w in text.lower().replace(".", "").split() if w not in STOP}


def compact(msgs, keep_last=4, budget=3):
    old, recent = msgs[:-keep_last], msgs[-keep_last:]
    topic = set().union(*(words(m) for m in recent))
    ranked = sorted(old, key=lambda m: -len(words(m) & topic))
    return ranked[:budget] + recent


def next_action(ctx):
    rules = " ".join(ctx).lower()
    return "skip migrate" if "never run migrations against prod" in rules else "migrate prod"


RULE = "user: Never run migrations against prod."
msgs = ["user: set up the settings page", RULE]
msgs += [f"user: restyle button {i} css on the settings page" for i in range(26)]
msgs += ["user: tidy the settings page css", "user: fix the button color css", "user: deploy it", "user: ship the settings page"]

assert next_action(msgs) == "skip migrate"
after = compact(msgs)
assert RULE not in after and next_action(after) == "migrate prod"
print(f"FAILURE: {len(msgs)} messages compacted to {len(after)}; the rule is gone; next action = {next_action(after)}")


def compact_pinned(msgs, pinned):
    rest = [m for m in msgs if m not in pinned]
    out = pinned + compact(rest)
    missing = [p for p in pinned if p not in out]
    assert not missing, f"pinned items lost in compaction: {missing}"
    return out


after = compact_pinned(msgs, [RULE])
assert RULE in after and next_action(after) == "skip migrate"
print(f"FIXED: {len(msgs)} messages compacted to {len(after)}; pinned rule survives; next action = {next_action(after)}")
