# Agent Failure Atlas

A field guide to how production AI agents actually fail, with a runnable reproduction for every failure.

Each of the 41 entries names one failure, shows the symptom you would see in a trace, explains the mechanism and the assumption that breaks, gives a reproduction you can run in under a second, and ends with a detection signal and the smallest correct fix. Every reproduction is standard-library Python that runs offline and deterministically, and where a real failure needs a model, the model is stubbed and the entry says what the stub assumes. The last section of each entry, "How it still bites", records what the fix does not cover.

## Start here

- **My agent loops or never finishes**: start at [PLAN-01](atlas/PLAN-01.md), then PLAN-05 if each step succeeds but the run ends up somewhere wrong.
- **My agent is expensive and slow**: start at [COST-01](atlas/COST-01.md) for the quadratic bill and [CTX-04](atlas/CTX-04.md) for latency and the context limit. COST-02 is next if the cache hit rate is near zero.
- **My agent did something I did not authorize**: start at [SEC-01](atlas/SEC-01.md), then SEC-02 (whose permissions the agent used) and TOOL-06 (how it came to hold them).

Anything else: search the entries, or follow the symptom table in [docs/how-to-use.md](docs/how-to-use.md).

## Using the CLI

It needs Python 3.9 or later and nothing else. It works from any directory and never writes files.

```
python3 atlas.py list                         # every entry
python3 atlas.py list --category CTX          # one category
python3 atlas.py list --severity critical     # one severity
python3 atlas.py show CTX-03                  # one entry, rendered
python3 atlas.py search 'duplicate charge'    # ranked substring search
python3 atlas.py repro CTX-03                 # run the reproduction, show its exit code
python3 atlas.py check                        # validate the whole repository
```

## Index

Severity is the blast radius if it happens: critical means irreversible or external harm, high means wrong results or an outage, medium means wasted money or time. See [docs/taxonomy.md](docs/taxonomy.md) for why the categories are separate.

### Plan and decomposition (PLAN)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| PLAN-01 | high | [The agent repeats the same tool call forever because nothing in its loop measures progress](atlas/PLAN-01.md) | Run ends at max_turns with dozens of identical tool calls returning identical results |
| PLAN-02 | high | [The goal drifts because each step restates it from the previous step's paraphrase](atlas/PLAN-02.md) | A late action violates a constraint the user gave in the first message, and the agent's stated goal no longer mentions it |
| PLAN-03 | critical | [Recursive decomposition has no depth or budget and the task tree explodes](atlas/PLAN-03.md) | One user request spawns thousands of subtasks; queue depth and provider 429s climb while every node reports success |
| PLAN-04 | medium | [Parallel subagents lose each other's edits through read-modify-write on a shared artifact](atlas/PLAN-04.md) | Merged report is missing findings from some subagents although each subagent's trace says its write succeeded |
| PLAN-05 | high | [The agent executes a stale plan after a step's result invalidates the later steps](atlas/PLAN-05.md) | Every step of a multi-step run succeeds, but the later steps acted on an object the first step showed was the wrong one |
| PLAN-06 | medium | [The agent declares success on a goal whose success criterion cannot be checked](atlas/PLAN-06.md) | Agent reports the task done, the diff is cosmetic or empty of effect, and the metric the user cared about has not moved |

### Tool use and actions (TOOL)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| TOOL-01 | high | [A renamed field upstream turns into a silent zero in the agent's answer](atlas/TOOL-01.md) | Agent confidently reports a total of $0.00 for orders that the upstream API shows as non-zero |
| TOOL-02 | critical | [The model invents a plausible value for a required argument it does not have](atlas/TOOL-02.md) | A mutating tool call succeeds on a record the user never mentioned, using an id that appears nowhere in the conversation |
| TOOL-03 | high | [A tool returns an empty list on a swallowed error and the agent concludes the thing does not exist](atlas/TOOL-03.md) | Duplicate records created for customers that already exist, right after an auth or quota error that never appears in the agent trace |
| TOOL-04 | critical | [The agent retries a non-idempotent tool and double-charges the customer](atlas/TOOL-04.md) | Duplicate side effects after a timeout or a 500; two charges, two emails, two tickets |
| TOOL-05 | high | [A tool timeout is treated as failure while the original call is still running and completes](atlas/TOOL-05.md) | A customer is refunded to the card and also given store credit; the trace shows one failed call and one successful fallback |
| TOOL-06 | critical | [Permission scopes only ever accumulate across a session until the agent holds more than any task needed](atlas/TOOL-06.md) | A read-only task's token ends the session holding write and admin scopes, and a destructive call succeeds without ever returning a 403 |
| TOOL-07 | high | [The agent calls tools in the wrong order because a prerequisite is nowhere in the tool contract](atlas/TOOL-07.md) | Every tool call returns ok, the agent reports the release shipped, and the service is crash-looping against a schema that was never migrated |
| TOOL-08 | high | [A batch tool returns top-level ok while 3 of 10 items failed and the agent reports full success](atlas/TOOL-08.md) | The agent reports all records updated; a later reader finds a fraction of them unchanged, with no error anywhere in the run |

### Context (CTX)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| CTX-01 | high | [A constraint placed in the middle of a long context is ignored](atlas/CTX-01.md) | The agent violates a rule that is verifiably present in the prompt, only on runs where a large tool output sits above or below it |
| CTX-02 | critical | [Compaction drops the standing constraint because the summarizer keeps recent content](atlas/CTX-02.md) | After a long session the agent breaks a rule the user stated once early on, immediately after a "context compacted" event |
| CTX-03 | high | [One huge tool output pushes the system prompt out of the window](atlas/CTX-03.md) | Right after a large log or file is pasted or fetched, the agent forgets its persona, output format and safety rules |
| CTX-04 | medium | [Append-only history makes every turn slower until the run hits the context limit](atlas/CTX-04.md) | Per-turn latency climbs steadily through a long run, then the call fails with a context-length error although no single message was large |
| CTX-05 | medium | [Two versions of the same file sit in context and the edit is written against the stale one](atlas/CTX-05.md) | An edit fails with old_string not found, or succeeds and silently reverts a change the agent made a few turns earlier |
| CTX-06 | high | [A rolling summary keeps a fact as current long after it stopped being true](atlas/CTX-06.md) | The agent acts on a value that was corrected many turns ago, and the summary it was working from contains only the old value |

### Memory and state (MEM)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| MEM-01 | high | [Writing a memory every turn fills the top-k with paraphrases of one fact](atlas/MEM-01.md) | The agent forgets a safety-relevant fact it was told once, while the memory store holds dozens of near-identical preference notes |
| MEM-02 | high | [A keyword-stuffed document wins retrieval for every query and displaces the correct answer](atlas/MEM-02.md) | One document id appears as the top hit for unrelated queries and the answers cite it while the right runbook is never retrieved |
| MEM-03 | high | [A fact that was true two years ago outranks the correction because nothing ever expires or supersedes](atlas/MEM-03.md) | The agent keeps using a customer's old address, plan or contact after the customer corrected it; the correction exists in the store but never ranks first |
| MEM-04 | critical | [A response cache keyed by prompt text alone serves tenant A's answer to tenant B](atlas/MEM-04.md) | A user sees another tenant's numbers, policy or document contents in an answer, and the model call count for that request is zero |
| MEM-05 | high | [The agent acts on remembered state that no longer matches the world](atlas/MEM-05.md) | A write lands on a record someone else changed after the agent last looked, silently reopening, overwriting or reassigning it |

### Verification and evals (VERIFY)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| VERIFY-01 | high | [The agent grades its own work with the same misreading that produced it](atlas/VERIFY-01.md) | Every self-written test is green and the agent reports the work verified, but the output is off by one at the boundary the spec was ambiguous about |
| VERIFY-02 | high | [The tests pass because the code special-cases the tests](atlas/VERIFY-02.md) | CI is green after the agent's final change, and the same function returns wrong answers on any input the tests did not contain |
| VERIFY-03 | medium | [Eval examples leak into the prompt and inflate the score](atlas/VERIFY-03.md) | The eval score jumps to near-perfect after a prompt or retrieval change, and live quality does not move |
| VERIFY-04 | medium | [The judge prefers whichever answer it sees first](atlas/VERIFY-04.md) | The pairwise win rate changes when you swap which system is listed first, and identical outputs do not split 50/50 |
| VERIFY-05 | medium | [The success metric rewards length so the agent learns to be verbose](atlas/VERIFY-05.md) | The eval score rises release over release while answers get longer and reviewers report padding and wrong details |

### Security (SEC)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| SEC-01 | critical | [Instructions inside a tool result are obeyed because the loop does not separate data from commands](atlas/SEC-01.md) | An email, comment or HTTP POST nobody asked for shows up in the audit log right after the agent read an external ticket, page or email |
| SEC-02 | critical | [The agent acts with its own service account's permissions instead of the requesting user's](atlas/SEC-02.md) | A user gets another user's document by asking for it, and the data-layer audit log shows only agent-svc as the reader |
| SEC-03 | high | [A path check that looks right lets file tools escape the sandbox](atlas/SEC-03.md) | read_file returns contents of a file outside the workspace while the log line says the path passed the sandbox check |
| SEC-04 | high | [Private data leaves through a rendered image URL or link](atlas/SEC-04.md) | An attacker-controlled host receives a GET with the user's secret in the query string seconds after an answer renders, with no click |
| SEC-05 | high | [Secrets reach logs and traces through tool-call arguments the redactor does not recognize](atlas/SEC-05.md) | A credential is found in the trace store in base64 or percent-encoded form although a redaction filter is deployed and its scans report clean |

### Operations (OPS)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| OPS-01 | high | [An incident cannot be reproduced because the run left no replayable record](atlas/OPS-01.md) | The postmortem reruns the failing task, the agent takes a different path and succeeds, and nobody can say what happened the first time |
| OPS-02 | high | [Per-run budgets pass while the fleet overspends because the budget check is not atomic](atlas/OPS-02.md) | Every run's budget guard logs "ok" and the daily spend cap is still blown, by a multiple of the limit, within a minute of a traffic burst |
| OPS-03 | critical | [Layered retries multiply load on a degraded dependency until it cannot recover](atlas/OPS-03.md) | A dependency that was merely slow goes down hard, request rate to it is many times the user-facing rate, and it can stay down after the original fault clears |
| OPS-04 | high | [A floating model alias changes the model under you and the prompt regresses with no deploy](atlas/OPS-04.md) | Parse errors or quality drop begin at a clean timestamp with no commit, deploy or config change in your history |

### Economics (COST)

| ID | Severity | Title | Symptom |
| --- | --- | --- | --- |
| COST-01 | high | [Resending the full history every turn makes total input tokens grow quadratically](atlas/COST-01.md) | Cost per run grows with the square of run length; a run twice as long costs about four times as much, and the invoice outruns usage growth |
| COST-02 | medium | [A timestamp at the top of the system prompt defeats the prefix cache on every request](atlas/COST-02.md) | Cached-token share is near zero despite a system prompt and tool list that have not changed, so every request pays full input price and full prefill |

## How to read an entry

Every entry has the same six sections in the same order.

- **What you see**: the log lines and user-visible effects, so you can match it against your own trace.
- **Why it happens**: the mechanism and the exact assumption that breaks.
- **Minimal reproduction**: a short program that isolates the mechanism, followed by a pointer to the fuller version in repro/.
- **Detection**: a signal you can wire up today, such as a metric, a query, an assertion or a test.
- **The fix**: the smallest correct change, with the structural fix preferred over a prompt instruction and the reason why.
- **How it still bites**: the residual risk after the fix. If you read only one section, read this one.

The front matter carries id, title, category, severity, frequency, symptom, stage and tags. The frequency values mean: common, you will meet it within the first months; occasional, you will meet it at scale or with a specific design; rare, it needs an unusual combination or an adversary.

## Contributing

Add an entry for a failure you have been paged for. A good entry is a distinct mechanism, not a new symptom of an existing one: if the fix lives in the same place as an existing entry's fix, extend that entry instead. The skeleton, the section rules and the reproduction rules are in [docs/entry-template.md](docs/entry-template.md). Before opening a pull request, run `python3 check.py` and `python3 check.py --assemble`; the first validates every entry and runs every reproduction, and the second regenerates ATLAS.md, the single-page version of all entries. A reproduction that needs an API key, the network or a wall-clock race will not be merged. Numbers in an entry must come from its reproduction or from arithmetic shown in the entry, and any real incident you cite goes in [docs/citations.md](docs/citations.md) with a link and a note.

## Layout

| Path | Contents |
| --- | --- |
| atlas/ | One markdown file per entry, named by id |
| repro/ | One runnable Python file per entry, same id |
| ATLAS.md | Every entry on one page, generated by check.py --assemble |
| atlas.py | The CLI |
| check.py | Validator and assembler |
| docs/ | Taxonomy, triage workflow, entry template, citations |

## What this is not

It is not a benchmark, a catalogue of model quirks, or a list of rules to follow; it records failures in the code and systems around the model, and it shows a stubbed model whenever a real one would make the run nondeterministic. A stub proves a mechanism, not a rate, so none of the entries tell you how often a particular model will misbehave.
