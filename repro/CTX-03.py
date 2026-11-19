"""CTX-03: one huge tool result makes oldest-first truncation evict the system prompt.

Tokens are approximated as whitespace-separated words. The window is 100k to keep the numbers small.
"""
WINDOW = 100_000


def tokens(m):
    return len(m["text"].split())


def msg(role, n, tag="x"):
    return {"role": role, "text": " ".join([tag] * n)}


def build():
    return (
        [msg("system", 1500, "RULES")]
        + [msg("user" if i % 2 == 0 else "assistant", 1000) for i in range(12)]
        + [msg("tool", 90_000, "LOG"), msg("user", 50)]
    )


def truncate_oldest(msgs):
    msgs = list(msgs)
    while sum(map(tokens, msgs)) > WINDOW:
        msgs.pop(0)
    return msgs


def clip(m, cap):
    w = m["text"].split()
    if m["role"] != "tool" or len(w) <= cap:
        return m
    mark = f"[... {len(w) - cap} tokens cut; call fetch_log(offset) for more ...]"
    return {**m, "text": " ".join(w[: cap // 2] + [mark] + w[-(cap // 2):])}


def truncate_safe(msgs, cap=2_000):
    msgs = [clip(m, cap) for m in msgs]
    while sum(map(tokens, msgs)) > WINDOW:
        victim = next(m for m in msgs if m["role"] != "system")
        msgs.remove(victim)
    return msgs


msgs = build()
total = sum(map(tokens, msgs))
kept = truncate_oldest(msgs)
dropped = len(msgs) - len(kept)
assert kept[0]["role"] != "system" and not any(m["role"] == "system" for m in kept)
print(f"FAILURE: {total} tokens > {WINDOW}; oldest-first eviction dropped {dropped} messages including the system prompt")

safe = truncate_safe(msgs)
assert safe[0]["role"] == "system" and len(safe) == len(msgs)
tool = next(m for m in safe if m["role"] == "tool")
assert "fetch_log(offset)" in tool["text"] and tokens(tool) < 2_100
print(f"FIXED: {sum(map(tokens, safe))} tokens, nothing evicted, tool result clipped 90000 -> {tokens(tool)} with a fetch pointer")

pinned_only = [msg("system", 1500, "RULES")] + [msg("user", 60_000)] * 3
safe = truncate_safe(pinned_only)
assert safe[0]["role"] == "system" and sum(map(tokens, safe)) <= WINDOW
print("FIXED: with a flood of user messages the system prompt still stays; only non-pinned messages go")
