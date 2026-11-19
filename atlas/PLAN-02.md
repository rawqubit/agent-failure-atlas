---
id: PLAN-02
title: The goal drifts because each step restates it from the previous step's paraphrase
category: planning
severity: high
frequency: occasional
symptom: A late action violates a constraint the user gave in the first message, and the agent's stated goal no longer mentions it
stage: planning
tags: goal-drift, constraints, summarization
---

## What you see
The user asked: "delete *.tmp files, only under src/, never touch tests/, ask before deleting anything over 1000 KB." Forty turns later the agent's own plan header reads "delete *.tmp files" and it removes `tests/fixture.tmp` and a 3 MB file under `src/` without asking. Diffing the plan header turn by turn shows the constraints vanishing one at a time, with no single turn that looks wrong.

## Why it happens
Each step builds its prompt from the previous step's restatement of the goal ("current objective: ...") rather than from the original message. A paraphrase compresses, and what compresses first is the qualifier: the verb phrase is the task, the clauses after it read as optional detail. Loss compounds, because step n+1 can only preserve what step n kept, so the constraint set shrinks monotonically and never regrows. The model then behaves correctly with respect to the goal it has been shown; the error was made earlier and silently. The stub in the repro assumes two things: each restatement drops its last qualifier clause, and the agent obeys exactly the constraints present in its prompt.

## Minimal reproduction
```python
FILES = {"src/a.tmp": 1, "src/big.tmp": 3000, "tests/x.tmp": 2, "build/y.tmp": 4}
ORIGINAL = "delete *.tmp files, only under src/, never touch tests/, ask before deleting anything over 1000 KB"

def restate(text):
    clauses = text.split(", ")
    return ", ".join(clauses[:-1]) if len(clauses) > 1 else text

def agent_deletes(prompt):
    out = []
    for path, kb in FILES.items():
        if "only under src/" in prompt and not path.startswith("src/"): continue
        if "never touch tests/" in prompt and path.startswith("tests/"): continue
        if "over 1000 KB" in prompt and kb > 1000: continue
        out.append(path)
    return out

def run(steps, pinned):
    goal = ORIGINAL
    for _ in range(steps):
        goal = restate(goal)
    return goal, agent_deletes(ORIGINAL + " | " + goal if pinned else goal)

goal, deleted = run(3, pinned=False)
assert len(deleted) == 4
print("FAILURE: goal is now %r; deleted %s" % (goal, deleted))
goal, deleted = run(3, pinned=True)
assert deleted == ["src/a.tmp"]
print("FIXED: original verbatim in every prompt; deleted %s" % deleted)
```
The fuller version, which also gates the action against the original constraints, is in repro/PLAN-02.py.

## Detection
Track a goal-drift count per run: the number of original constraint clauses that no longer appear in the goal text the current step is using. Store constraints as a list at intake, so the check is a set difference rather than a judgment call, and alert when the count is above zero. Before shipping a change to a summarizer or planner prompt, run a replay test: restate a fixed three-constraint goal ten times with the production prompt and assert all three constraints survive verbatim.

## The fix
Treat the goal as immutable data, not as text that flows through the loop. At intake, parse it into `{task, constraints[]}` and store it. Every prompt renders the constraints verbatim from that record, never from the previous step's output; a paraphrase is allowed only as a labelled scratch summary. Then check each proposed action against the constraints in code, at the tool boundary, so a drifted prompt cannot produce a violating action even if the model gets it wrong. Re-stating the constraints more firmly in the prompt is the band-aid: it fights the paraphrase instead of removing it.
```python
GOAL = Goal(task="delete tmp files", constraints=[under("src/"), not_under("tests/"), max_kb(1000)])
prompt = render(GOAL) + scratch_summary
assert all(c.allows(action) for c in GOAL.constraints), "action violates original goal"
```

## How it still bites
The action gate can only enforce constraints that were compiled into predicates: "only under src/" is checkable, "keep the tone formal" is not, and that second kind goes back to drifting inside the verbatim text the model has to attend to (see CTX-01). Compiling the constraints is also itself an interpretation step; if the intake parser drops a clause, the drift is now permanent and carries the original goal's authority.
