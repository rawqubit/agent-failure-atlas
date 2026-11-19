---
id: SEC-05
title: Secrets reach logs and traces through tool-call arguments the redactor does not recognize
category: security
severity: high
frequency: common
symptom: A credential is found in the trace store in base64 or percent-encoded form although a redaction filter is deployed and its scans report clean
stage: state-write
tags: secrets, redaction, tracing, observability
---

## What you see
A security scan of the trace store finds `"Authorization": "Basic c3Zj..."` and `?key=sk_live_4fQ%2B9xLm%2FZv7TrB2cK8w%3D` in spans that the redaction filter had already processed. In the repro, three logged tool calls carry the same key: the pattern redactor catches the plain one and leaves the key recoverable in the other 2 of 3.

## Why it happens
The redactor is written against the shape of the token, `sk_live_` followed by a character class, which describes exactly one byte sequence. The trace stores the arguments after they have been transformed on the way to the wire. Percent-encoding turns `+`, `/` and `=` into `%2B`, `%2F`, `%3D`, and the character class stops at `%`, so only three tail characters match and the `{16,}` quantifier fails. Basic auth base64-encodes `svc:` plus the key, and because the 4-byte prefix shifts the alignment, the encoded key is a different character string from base64 of the key alone. A fix that adds base64 of the secret by itself still misses it; the value has to be encoded at all three alignments. The assumption that breaks is that a secret appears in logs in the form it has in the vault.

## Minimal reproduction
```python
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
```
The same code, plus the split-across-fields case, the reference-passing fix and a runtime-minted token, is in repro/SEC-05.py.

## Detection
Run an end-to-end test with a canary credential that is unique per run, collect everything the tracer, the logger and the error reporter wrote, and fail if any 8-character window of the canary appears in any of its encodings: plain, percent-encoded, and base64 at the three alignments. Windows catch the split case where the key is chunked across two arguments, which exact substring matching cannot. Run the same scan on a schedule over the trace store itself.

## The fix
Keep the secret out of the model's context. The model passes a handle, and the tool boundary resolves it; the trace then records the handle, and nothing the model can encode, split or paraphrase exists in it.
```python
model_args = {"url": url, "credential": "stripe_live"}
headers = {"Authorization": "Bearer " + registry[model_args["credential"]]}
```
Keep value-based redaction as the second layer at the writer, built from the real set of secrets in all encodings, as in the repro, where it leaves the key recoverable in 0 of 3 calls. Shape-based patterns catch only the forms their authors thought of; absence of the value is exact.

## How it still bites
Secrets minted at runtime, such as an OAuth access token from a token-exchange call or a signed URL, are not in the static set, so value redaction passes them through until something registers them; the repro shows the minted token surviving redaction. Injection at the tool boundary also moves the plaintext rather than removing it: HTTP client debug logs, exception messages that quote the request URL, and egress proxies still see the real value, and the canary has to cover those writers too.
