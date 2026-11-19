---
id: OPS-04
title: A floating model alias changes the model under you and the prompt regresses with no deploy
category: operations
severity: high
frequency: occasional
symptom: Parse errors or quality drop begin at a clean timestamp with no commit, deploy or config change in your history
stage: deployment
tags: model-versioning, aliases, regression, canary
---

## What you see
At 09:12 the `json_parse_error` rate goes from 0 to 100 percent on a classifier endpoint. The git log for the service shows nothing since Tuesday, the deploy history is empty, and the config still says `model: acme-latest`. The raw responses are the same JSON as before, now wrapped in a markdown code fence.

## Why it happens
A floating alias like `-latest` is a pointer the provider owns, and your configuration treats it as a constant. When the provider re-points it to a newer snapshot, every request from every environment changes behaviour at the same instant, while your source, your prompt and your tests are byte-identical. The new snapshot is not wrong, only different: a fence around JSON, a changed refusal wording, a different default verbosity. Your code encoded an unwritten assumption about that behaviour in a strict parser or a string match, and the assumption was only ever true of one snapshot. Because the change arrives through a pointer rather than through your pipeline, none of your usual controls (review, CI, staged rollout) sees it.

## Minimal reproduction
The provider is a stub with fictional model ids; the only modelled difference between the two snapshots is the code fence.
```python
import json

ALIASES = {"acme-latest": "acme-2025-03"}

def provider(model, prompt):
    resolved = ALIASES.get(model, model)
    body = json.dumps({"sentiment": "positive"})
    if resolved >= "acme-2025-09":
        body = "```json\n" + body + "\n```"
    return {"model": resolved, "text": body}

def errors(model, n=20):
    bad = 0
    for _ in range(n):
        try:
            json.loads(provider(model, "classify")["text"])
        except json.JSONDecodeError:
            bad += 1
    return bad

assert errors("acme-latest") == 0
ALIASES["acme-latest"] = "acme-2025-09"
print(f"FAILURE: no deploy, no code change; {errors('acme-latest')}/20 requests now fail json.loads")
assert errors("acme-latest") == 20

assert errors("acme-2025-03") == 0
resp = provider("acme-latest", "classify")
assert resp["model"] != "acme-2025-03"
print("FIXED: pinned snapshot id: 0/20 errors; canary sees resolved id", resp["model"], "differ from last seen")
```
The same code, plus an explicit fence-tolerant parse step with a counter, is in repro/OPS-04.py.

## Detection
Log the resolved model id from every response (the `model` field the provider returns, not the string you sent) as a dimension on every metric, and alert when a new value appears for a given endpoint; assert `resolved != requested` to catch gateways that echo the alias back. Run a golden-set canary, 20 to 50 fixed inputs with checkable outputs (parse succeeds, required keys exist, label matches), on a schedule and immediately whenever the resolved id changes, and page on the pass rate, not on the average score. Group parse errors by resolved id: a clean step at one boundary identifies the cause in one query.

## The fix
Pin dated snapshot ids in config, so the model changes only through a commit, with the golden set as the CI gate on that commit. Log the resolved id on every response, and make any deviation from the pinned id an alert, because proxies and routers can substitute models too. If you must tolerate a format variant, do it in one named parse step (strip exactly one code fence, then parse strictly, and count each strip) so tolerance is visible and not scattered through the code.
```python
MODEL = "acme-2025-03"
assert resp["model"] == MODEL, f"served {resp['model']}, pinned {MODEL}"
```
The alternative, tolerating every variant in every consumer, hides drift until it crosses a line the parser cannot cover.

## How it still bites
A pinned snapshot is retired on the provider's schedule, so pinning turns a silent regression into a dated forced migration that tends to land in a week nobody planned for; store the retirement date next to the pin and alert 30 days ahead. The resolved id is also only as trustworthy as the layer reporting it, so keep the scheduled canary running even when the id has not changed.
