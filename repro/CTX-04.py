"""CTX-04: an append-only history makes every turn slower until the context limit kills the run.

Token counts and the latency model are labelled constants, not measurements.
"""
LIMIT = 200_000
SYSTEM, MODEL_OUT, TOOL_OUT = 2_000, 200, 1_500
STUB, KEEP = 20, 5
PREFILL_MS_PER_TOKEN = 0.05


def prompt_tokens(n, mask):
    prior = n - 1
    kept = min(prior, KEEP) if mask else prior
    return SYSTEM + prior * MODEL_OUT + kept * TOOL_OUT + (prior - kept) * STUB


def first_overflow(mask, horizon=2_000):
    for n in range(1, horizon + 1):
        if prompt_tokens(n, mask) > LIMIT:
            return n
    return None


def latency_ms(n, mask):
    return prompt_tokens(n, mask) * PREFILL_MS_PER_TOKEN


per_turn_new = MODEL_OUT + TOOL_OUT
assert per_turn_new == 1_700
dies = first_overflow(mask=False)
assert dies == 118
print(
    f"FAILURE: each turn adds only {per_turn_new} tokens, yet turn 1 prefill = {latency_ms(1, False):.0f} ms, "
    f"turn 100 = {latency_ms(100, False):.0f} ms, and turn {dies} overflows the {LIMIT} window"
)

assert first_overflow(mask=True, horizon=300) is None
dies_masked = first_overflow(mask=True)
assert dies_masked == 868
ratio = prompt_tokens(300, False) / prompt_tokens(300, True)
print(
    f"FIXED: masking old tool results keeps the last {KEEP} verbatim; turn 300 prompt = {prompt_tokens(300, True)} tokens "
    f"({latency_ms(300, True):.0f} ms) vs {prompt_tokens(300, False)} that the unmasked history would need ({ratio:.1f}x)"
)
print(f"RESIDUAL: masking only flattens the slope; the masked run still overflows at turn {dies_masked}")


class ContextBudgetExceeded(Exception):
    pass


def check_budget(n, mask, limit=LIMIT):
    t = prompt_tokens(n, mask)
    if t > limit:
        raise ContextBudgetExceeded(f"turn {n}: {t} > {limit}, compact or stop before the call")


try:
    check_budget(dies, mask=False)
except ContextBudgetExceeded as e:
    print("FIXED: pre-call budget check fails early and by name:", e)
else:
    raise AssertionError("budget check did not fire")
