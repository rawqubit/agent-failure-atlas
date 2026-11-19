"""PLAN-02: a goal restated from the previous restatement loses one qualifier per pass."""
FILES = {"src/a.tmp": 1, "src/big.tmp": 3000, "tests/fixture.tmp": 2, "build/x.tmp": 4, "src/notes.md": 1}
CONSTRAINTS = ["only under src/", "never touch tests/", "ask before deleting anything over 1000 KB"]
ORIGINAL = ", ".join(["delete *.tmp files"] + CONSTRAINTS)
ALLOWED = ["src/a.tmp"]


def restate(text):
    clauses = text.split(", ")
    return ", ".join(clauses[:-1]) if len(clauses) > 1 else text


def agent_deletes(prompt):
    out = []
    for path, kb in FILES.items():
        if not path.endswith(".tmp"):
            continue
        if "only under src/" in prompt and not path.startswith("src/"):
            continue
        if "never touch tests/" in prompt and path.startswith("tests/"):
            continue
        if "over 1000 KB" in prompt and kb > 1000:
            continue
        out.append(path)
    return out


def run(steps, pinned):
    goal, history = ORIGINAL, [ORIGINAL]
    for _ in range(steps):
        goal = restate(goal)
        history.append(goal)
    prompt = ORIGINAL + " | working summary: " + goal if pinned else goal
    deleted = agent_deletes(prompt)
    if pinned:
        assert set(deleted) <= set(ALLOWED), "gate: action violates the original constraints"
    return history, deleted


history, deleted = run(3, pinned=False)
for i, g in enumerate(history):
    print("restatement %d: %s" % (i, g))
violations = sorted(set(deleted) - set(ALLOWED))
assert history[-1] == "delete *.tmp files" and len(violations) == 3
print("FAILURE: agent deleted %d files, %d outside the original constraints: %s" % (len(deleted), len(violations), violations))

history, deleted = run(3, pinned=True)
assert deleted == ALLOWED
print("FIXED: same 3 lossy restatements, original verbatim in every prompt, deleted: %s" % deleted)
