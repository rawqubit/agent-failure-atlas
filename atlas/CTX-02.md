---
id: CTX-02
title: Compaction drops the standing constraint because the summarizer keeps recent content
category: context
severity: critical
frequency: common
symptom: After a long session the agent breaks a rule the user stated once early on, immediately after a "context compacted" event
stage: context-assembly
tags: compaction, summarization, constraints, long-sessions
---

## What you see
The log shows `compaction: 32 messages -> 7` at turn 34, and the next tool call is `run_migrations --env prod`. The user's message from turn 2, "Never run migrations against prod", is in the full transcript on disk but not in the compacted context. When asked why, the agent answers truthfully that it saw no such rule.

## Why it happens
Compaction has to decide what to keep, and every cheap policy it can use measures something other than "is this a standing rule". Keep-last-N keeps recency; a summarizer asked for the gist of a thread about CSS keeps the CSS; a relevance ranker keeps what overlaps the current topic. A constraint is stated once, in a sentence that shares almost no words with the work happening forty turns later, so it scores low on every one of those axes. The assumption that breaks is that importance and salience are the same thing: a rule matters most at the moment it is not being discussed, which is the moment it gets pruned. The deploy step that eventually needs the rule arrives with a context that contains no trace of it, and a model can only honour what is in its context.

## Minimal reproduction
The agent is a stub that honours a rule only if its text is still in context; compaction keeps the last four messages plus the older messages that share the most words with them.
```python
STOP = {"the", "a", "to", "on", "in", "and", "of", "is", "for", "against"}

def words(text):
    return {w for w in text.lower().replace(".", "").split() if w not in STOP}

def compact(msgs, keep_last=4, budget=3):
    old, recent = msgs[:-keep_last], msgs[-keep_last:]
    topic = set().union(*(words(m) for m in recent))
    return sorted(old, key=lambda m: -len(words(m) & topic))[:budget] + recent

def next_action(ctx):
    ok = "never run migrations against prod" in " ".join(ctx).lower()
    return "skip migrate" if ok else "migrate prod"

RULE = "user: Never run migrations against prod."
msgs = ["user: set up the settings page", RULE]
msgs += [f"user: restyle button {i} css on the settings page" for i in range(26)]
msgs += ["user: tidy the settings page css", "user: fix the button color css", "user: deploy it", "user: ship it"]
after = compact(msgs)
assert RULE not in after and next_action(after) == "migrate prod"
print(f"FAILURE: {len(msgs)} messages -> {len(after)}, rule gone, next action = {next_action(after)}")

def compact_pinned(msgs, pinned):
    out = pinned + compact([m for m in msgs if m not in pinned])
    assert all(p in out for p in pinned), "pinned item lost in compaction"
    return out
after = compact_pinned(msgs, [RULE])
assert next_action(after) == "skip migrate"
print(f"FIXED: pinned block survives compaction, next action = {next_action(after)}")
```
The same mechanism, with message counts, is in repro/CTX-02.py.

## Detection
Make compaction testable: before and after every compaction, run an assertion that every item in the pinned set appears verbatim in the new context, and emit `compaction.pinned_lost` as a counter that must stay at zero. For items you do not pin, add a regression test that plants a rule at turn 2 of a synthetic 60-turn session, forces compaction, and then asks the agent to do the forbidden thing; the test fails if the action goes through. In production, diff the set of user messages containing "never", "always", "do not" or "only" between the raw transcript and the post-compaction context, and log the count of imperatives that vanished.

## The fix
Split context into a pinned block and a compactable region. Standing constraints, the original goal and the tool allowlist live in the pinned block, which compaction never reads or rewrites, and the compactor ends with the assertion from the repro so a bug fails loudly instead of silently dropping a rule. The structural change matters more than asking the summarizer to "preserve all rules": that instruction asks a lossy component to be lossless about the one thing it has no signal for.
```python
context = pinned + compact(rest)
assert all(p in context for p in pinned)
```
Back the pin with a hard gate where the damage is, so the migration tool itself refuses prod without an explicit approval token.

## How it still bites
Pinning moves the problem to recognition: someone or something has to decide that "oh, and don't touch prod" mid-sentence is a standing constraint, and a classifier that misses it leaves you exactly where you started. Pins also never expire, so a rule the user later relaxed ("prod migrations are fine for this release") stays in force alongside its replacement; see CTX-06 for that ordering problem.
