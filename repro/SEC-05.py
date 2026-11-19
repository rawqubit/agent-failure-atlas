"""SEC-05: a redactor that knows the token's shape misses the same token once it is encoded."""
import base64, json, re, urllib.parse
SECRET = "sk_live_4fQ+9xLm/Zv7TrB2cK8w="
CALLS = [
    {"url": "https://api.example.test/me", "headers": {"X-Key": SECRET}},
    {"url": "https://api.example.test/me", "headers": {"Authorization": "Basic " + base64.b64encode(("svc:" + SECRET).encode()).decode()}},
    {"url": "https://api.example.test/me?key=" + urllib.parse.quote(SECRET, safe="")},
]

def pattern_redact(text):
    return re.sub(r"sk_live_[A-Za-z0-9+/=_-]{16,}", "[REDACTED]", text)

def forms(secret):
    raw = secret.encode()
    out = {secret, urllib.parse.quote(secret, safe="")}
    for pad in range(3):
        enc = base64.b64encode(b"\0" * pad + raw).decode().rstrip("=")[(0, 2, 3)[pad]:]
        out.add(enc[:-1] if (len(raw) + pad) % 3 else enc)
    return out

def value_redact(text, secrets=(SECRET,)):
    for form in sorted({f for s in secrets for f in forms(s)}, key=len, reverse=True):
        text = text.replace(form, "[REDACTED]")
    return text

def recoverable(text):
    views = [text, urllib.parse.unquote(text)]
    for tok in re.findall(r"[A-Za-z0-9+/=]{12,}", text):
        try:
            views.append(base64.b64decode(tok + "=" * (-len(tok) % 4)).decode("latin1"))
        except ValueError:
            pass
    return any(SECRET in v for v in views)

def leaks(redact):
    return sum(recoverable(redact(json.dumps(c))) for c in CALLS)

print("FAILURE: pattern redactor leaves the secret recoverable in %d of %d logged calls" % (leaks(pattern_redact), len(CALLS)))
print("FIXED: value-based redactor leaves it in %d of %d" % (leaks(value_redact), len(CALLS)))
assert leaks(lambda t: t) == 3 and leaks(pattern_redact) == 2 and leaks(value_redact) == 0

for prefix in ("", "u:", "svc:"):
    for suffix in ("", ":x", ":xy"):
        enc = base64.b64encode((prefix + SECRET + suffix).encode()).decode()
        assert not recoverable(value_redact(enc)) and "[REDACTED]" in value_redact(enc), (prefix, suffix)

naive = base64.b64encode(SECRET.encode()).decode()
basic = json.dumps(CALLS[1])
assert naive not in basic and recoverable(basic.replace(naive, "[REDACTED]"))
print("FAILURE: redacting base64 of the key alone leaves the Basic header recoverable (alignment shifted by the svc: prefix)")

def canary_windows(secret, n=8):
    return {f[i:i + n] for f in forms(secret) for i in range(len(f) - n + 1)}

def canary_hit(trace_text):
    return any(w in trace_text for w in canary_windows(SECRET))

split_call = json.dumps({"part1": SECRET[:12], "part2": SECRET[12:]})
assert canary_hit(value_redact(split_call)), "value redaction cannot see a secret split across fields"
print("FAILURE: split across two fields, value redaction leaves both halves; the canary window scan sees them")

REGISTRY = {"stripe_live": SECRET}

def call_tool(args):
    assert REGISTRY[args["credential"]] == SECRET
    return {"ok": True}

model_args = {"url": "https://api.example.test/me", "credential": "stripe_live"}
trace_text = json.dumps({"args": model_args, "result": call_tool(model_args)})
assert not canary_hit(trace_text) and SECRET not in trace_text
print("FIXED: model emits a reference, the tool boundary injects the value, the trace holds no canary window")

minted = "tok_9aB3xQ7mLp2ZkR8vWd"
exchange = json.dumps({"result": {"access_token": minted}})
assert minted in value_redact(exchange)
assert minted not in value_redact(exchange, (SECRET, minted))
print("FAILURE: a token minted at runtime is not in the static secret set until it is registered")
