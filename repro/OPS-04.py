"""OPS-04: a floating model alias is re-pointed by the provider; same code, same prompt, new behaviour.

The provider is a STUB with fictional ids: the newer snapshot wraps JSON in a code fence, which is the
only modelled difference between the two snapshots.
"""
import json
import re

ALIASES = {"acme-latest": "acme-2025-03"}


def provider(model, prompt):
    resolved = ALIASES.get(model, model)
    body = json.dumps({"sentiment": "positive"})
    if resolved >= "acme-2025-09":
        body = "```json\n" + body + "\n```"
    return {"model": resolved, "text": body}


def parse_strict(text):
    return json.loads(text)


FENCE = re.compile(r"^```(?:json)?\n(.*)\n```$", re.S)
fence_stripped = 0


def parse_explicit(text):
    global fence_stripped
    m = FENCE.match(text.strip())
    if m:
        fence_stripped += 1
        text = m.group(1)
    return json.loads(text)


def errors(model, parse, n=20):
    bad = 0
    for _ in range(n):
        try:
            parse(provider(model, "classify")["text"])
        except json.JSONDecodeError:
            bad += 1
    return bad


GOLDEN = {"sentiment": "positive"}
assert errors("acme-latest", parse_strict) == 0
ALIASES["acme-latest"] = "acme-2025-09"
bad = errors("acme-latest", parse_strict)
assert bad == 20
print(f"FAILURE: no deploy, no code change; after the alias flip {bad}/20 requests fail parse_strict")

assert errors("acme-2025-03", parse_strict) == 0
print("FIXED: pinned dated snapshot 'acme-2025-03' still returns bare JSON: 0/20 parse errors")

last_seen = "acme-2025-03"
resp = provider("acme-latest", "classify")
changed = resp["model"] != last_seen
assert changed
print(f"FIXED: canary logs resolved id {resp['model']!r} != last seen {last_seen!r}: page before users do")

assert errors("acme-latest", parse_explicit) == 0 and fence_stripped == 20
counted = fence_stripped
assert parse_explicit(resp["text"]) == GOLDEN
print(f"FIXED: explicit fence-tolerant parse step: 0/20 errors, fence_stripped counter = {counted} (visible, not silent)")
