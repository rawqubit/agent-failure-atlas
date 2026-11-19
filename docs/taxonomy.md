# Taxonomy

The atlas has 41 entries in eight categories. The split is not by technology (prompts, tools, vector stores) but by where the fix has to live and who owns it. If two failures have the same fix in the same place, they are one entry; if they look alike but break in different code, they are two.

## The eight categories

| Prefix | Category | The question it answers | Where the fix lives |
| --- | --- | --- | --- |
| PLAN | planning | Is the agent pursuing the right thing, and does it know when to stop or change course? | The control loop: step budgets, postconditions, acceptance predicates |
| TOOL | tool-use | Did the action the agent took do what the agent believes it did? | The tool boundary: contracts, adapters, idempotency, preconditions |
| CTX | context | What did the model actually see on this call? | Prompt assembly: ordering, compaction, truncation, dedupe |
| MEM | memory | What persists between calls and runs, and is it still true and still yours? | The store: write policy, ranking, expiry, tenancy, versioned writes |
| VERIFY | verification | How do you know the work is right? | The evaluation harness: oracles, held-out data, judges, metrics |
| SEC | security | What can an adversary make the agent do or leak? | Capability design: authorization, taint, egress, redaction |
| OPS | operations | Can you run it, debug it, and bound its blast radius? | Runtime: budgets, retries, replay, pinning |
| COST | economics | What does it cost per task, and why does that number surprise you? | Prompt structure and caching, billing arithmetic |

## Why they are separate

**PLAN versus TOOL.** A plan failure is a bad decision with all tools working: PLAN-01 loops on perfectly healthy calls. A tool failure is a correct decision whose execution did not mean what the agent assumed: TOOL-03 is a sound plan fed an empty list that meant "error". The fix for the first is a progress detector in the loop; the fix for the second is a stricter contract at the adapter. Merging them hides that you fix them in different files.

**CTX versus MEM.** Context is volatile and rebuilt every call; memory is durable and outlives the run. CTX-06 (a stale rolling summary) is repaired by changing how the summary is built. MEM-03 (a fact that never expires) is repaired in the store's write path. The same stale fact can appear in both places, and the repair in one does not repair the other.

**CTX versus COST.** CTX-04 and COST-01 share a cause, an append-only history, and differ in what you observe. CTX-04 is the hard failure: latency climbs each turn and the run dies at the context limit. COST-01 is the bill: the total number of input tokens is quadratic in the number of turns long before any limit is reached. Teams with large windows see only the second.

**TOOL versus SEC.** TOOL-06 (scope accumulation) is an agent that was never attacked but ends a task over-privileged because the harness granted escalations and never revoked them. SEC-02 (confused deputy) is authorization checked against the wrong principal. Both are permission problems; the first is about lifetime of a grant, the second about whose identity is checked.

**MEM versus SEC.** MEM-02 (retrieval poisoning) is about rank: one document wins retrieval for every query. SEC-01 (indirect injection) is about obedience: text inside a result is treated as a command. A poisoned ranking can deliver an injection, but the two are fixed differently, by scoring and trust tiers in one case and by capability gating in the other.

**VERIFY versus everything.** Every other category can be hidden by weak verification, so verification failures are kept apart: they are the reason the other failures reach production.

## Pairs that look alike

| Pair | Same symptom | What differs at the failure site |
| --- | --- | --- |
| TOOL-04 and TOOL-05 | Duplicate side effects | TOOL-04 retries the same call after a lost response. TOOL-05 takes a different path after a timeout while the first call is still running. |
| TOOL-03 and TOOL-08 | Agent reports success wrongly | TOOL-03: the tool's output is false (empty on error). TOOL-08: the output is true and the consumer reads only its summary. |
| PLAN-04 and TOOL-07 | Wrong order of effects | PLAN-04: concurrent workers overwrite a shared artifact. TOOL-07: a single caller lacks a prerequisite the contract never states. |
| CTX-02 and CTX-06 | Old constraint or fact wrong after summarizing | CTX-02 loses a constraint. CTX-06 keeps a fact after it stopped being true. |
| PLAN-01 and OPS-02 | Runaway spend | PLAN-01 is one run looping. OPS-02 is many well-behaved runs overspending a shared budget through a non-atomic check. |
| SEC-01 and SEC-04 | Data leaves after an injection | SEC-01 is how the instruction got in. SEC-04 is the channel the data leaves by, which works regardless of how the instruction arrived. |

## Fields

**severity** is the blast radius when it happens, not how interesting it is. critical: irreversible or external harm (money, data disclosure, destructive action). high: wrong results users see, or a production outage. medium: wasted money or time, degraded quality that is caught eventually.

**frequency** is how often teams running agents in production meet it. common: expect it within the first months. occasional: you will meet it at scale or with a specific design. rare: needs an unusual combination or an adversary.

**stage** is where in the pipeline the failure becomes visible: planning, context-assembly, model-call, tool-execution, state-write, evaluation, deployment, billing.
