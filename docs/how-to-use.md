# How to use the atlas

The atlas is organized for the moment you are paged: you have a symptom, not a diagnosis. Start from what you observe.

## The workflow

1. **Write down the symptom in one sentence, with a number.** "The run made 214 tool calls and finished nothing" finds an entry; "the agent is bad" does not.
2. **Find candidates.** Either scan the symptom column of the README index, or search:
   ```
   python3 atlas.py search 'duplicate'
   python3 atlas.py list --category CTX
   python3 atlas.py list --severity critical
   ```
3. **Read What you see and Why it happens for the top two candidates.** Pick by mechanism, not by title. If the log lines in What you see do not resemble yours, the mechanism probably does not apply.
4. **Run the repro** with `python3 atlas.py repro <ID>` to see the mechanism fail with numbers, and compare its trace shape to yours. The repro is the shortest proof that the cause is real.
5. **Wire the Detection signal before you apply the fix.** A fix with no signal is a belief. The signal tells you whether the problem is rarer than you thought, and whether it comes back.
6. **Apply The fix, then read How it still bites.** The residual is what the next incident will look like.

## Symptom to entry

| What you observe | Start with |
| --- | --- |
| Same tool call repeated many times, run never finishes | PLAN-01, then PLAN-05 |
| Agent did something adjacent to what was asked | PLAN-02, CTX-02 |
| Task count or latency explodes on complex requests | PLAN-03, OPS-02 |
| Two workers produce a result missing one's changes | PLAN-04 |
| Agent says done and the result is wrong or unverifiable | PLAN-06, VERIFY-01, VERIFY-02 |
| Duplicate charges, emails, tickets | TOOL-04, TOOL-05 |
| A value is zero or null after an upstream change | TOOL-01 |
| Calls to real records the user never named | TOOL-02 |
| Agent says "not found" for things that exist | TOOL-03 |
| Deploy-style actions fail in a fixed order | TOOL-07 |
| Agent reports success, some items silently did not apply | TOOL-08 |
| Agent ignores a rule that is in the prompt | CTX-01, CTX-02, CTX-03 |
| Latency grows with each turn, run dies at turn N | CTX-04, then COST-01 |
| Edits fail or revert earlier edits | CTX-05 |
| Agent uses a fact that was true last week | CTX-06, MEM-03, MEM-05 |
| Memory recalls the same thing ten times and misses a new fact | MEM-01 |
| One document appears in every answer | MEM-02 |
| User sees another customer's data | MEM-04, SEC-02 |
| Evals are great and production is not | VERIFY-03, VERIFY-04, VERIFY-05 |
| Agent obeyed text it read in a page, email, or ticket | SEC-01, SEC-04 |
| Agent read or wrote outside its working directory | SEC-03 |
| A credential appears in a trace or log | SEC-05 |
| You cannot reproduce last night's failure | OPS-01 |
| Behavior changed and nothing was deployed | OPS-04 |
| A degraded dependency never recovers | OPS-03 |
| Bill is high and the cache hit rate is near zero | COST-02, COST-01 |
| Agent holds more permissions than the task needed | TOOL-06 |

## When nothing matches

Failures in agents are usually two entries stacked: a trigger and an amplifier. A TOOL-05 timeout becomes a duplicate charge only because there is no TOOL-04 idempotency key. Read the neighbors listed in docs/taxonomy.md under "Pairs that look alike" before concluding the atlas has nothing.

## Using entries in review

Each Detection section is written to be turned into a test or an alert. A reasonable pre-launch pass is to take every entry whose stage matches a component you are building, and check whether you could answer: if this happened tonight, which of my signals would fire?
