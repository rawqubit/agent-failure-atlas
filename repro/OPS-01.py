"""OPS-01: without a recorded trace an agent run cannot be replayed; with one it is reproduced exactly."""
import random


class World:
    """Tool backend whose answers depend on a clock that advances on every call."""

    def __init__(self, clock_start):
        self.t = clock_start

    def tool(self, name, args):
        self.t += 7
        if name == "get_quota":
            return {"remaining": 100 - (self.t % 37)}
        if name == "restart_job":
            return {"job": args["job"], "pid": 1000 + (self.t % 91)}
        raise KeyError(name)


def make_model(seed):
    rng = random.Random(seed)
    restart = ("restart_job", {"job": "etl-nightly"})

    def model(history):
        if not history:
            return ("get_quota", {})
        name, _, result = history[-1]
        if name == "restart_job":
            return ("done", {})
        if result["remaining"] < 50:
            return restart
        return rng.choice([restart, ("get_quota", {}), ("done", {})])

    return model


def run_agent(model, tools, patched=False):
    history = []
    for _ in range(6):
        name, args = model(history)
        if name == "done":
            break
        if patched and name == "restart_job":
            args = dict(args, dry_run=True)
        history.append((name, args, tools(name, args)))
    return history


def path(history):
    return [(n, r["pid"] if n == "restart_job" else r["remaining"]) for n, _, r in history]


class Recorder:
    """Wraps model and tools; the trace holds every model output and tool result in order."""

    def __init__(self, model, tools, meta):
        self.model, self.tools, self.trace = model, tools, {"meta": meta, "steps": []}

    def model_call(self, history):
        action = self.model(history)
        self.trace["steps"].append({"action": action, "result": None})
        return action

    def tool_call(self, name, args):
        result = self.tools(name, args)
        self.trace["steps"][-1].update(tool=name, args=args, result=result)
        return result


class ReplayDivergence(Exception):
    pass


class Replayer:
    def __init__(self, trace):
        self.steps, self.m, self.t = trace["steps"], 0, 0

    def model_call(self, history):
        action = self.steps[self.m]["action"] if self.m < len(self.steps) else ("done", {})
        self.m += 1
        return action

    def tool_call(self, name, args):
        step = self.steps[self.t]
        self.t += 1
        if (step["tool"], step["args"]) != (name, args):
            raise ReplayDivergence("step %d: recorded %s %s, code now calls %s %s"
                                   % (self.t, step["tool"], step["args"], name, args))
        return step["result"]


incident_rec = Recorder(make_model(seed=0), World(clock_start=1000).tool, {"seed": 0, "clock_start": 1000})
incident = run_agent(incident_rec.model_call, incident_rec.tool_call)
rerun = run_agent(make_model(seed=1), World(clock_start=1013).tool)
assert path(incident) != path(rerun)
print("FAILURE: rerun diverged. incident path %s, rerun path %s" % (path(incident), path(rerun)))

rep = Replayer(incident_rec.trace)
replayed = run_agent(rep.model_call, rep.tool_call)
assert replayed == incident and path(replayed) == path(incident)
print("FIXED: replay from the recorded trace reproduces the incident exactly: %s (%d steps)"
      % (path(replayed), len(replayed)))

rep = Replayer(incident_rec.trace)
try:
    run_agent(rep.model_call, rep.tool_call, patched=True)
    raise SystemExit("expected divergence")
except ReplayDivergence as e:
    print("RESIDUAL: replaying the same trace against patched agent code raises ReplayDivergence: %s" % e)
