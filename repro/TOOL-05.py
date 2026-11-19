"""TOOL-05: a client timeout is read as 'the refund failed' while the refund is still pending or already committed."""


class RefundGateway:
    """Deterministic clock: one tick per call to tick(). The commit happens at commit_at, the response is readable at respond_at."""

    def __init__(self, commit_at, respond_at):
        self.t, self.commit_at, self.respond_at = 0, commit_at, respond_at
        self.state, self.ledger = "pending", []

    def tick(self, n):
        for _ in range(n):
            self.t += 1
            if self.state == "pending" and self.t == self.commit_at:
                self.state = "done"
                self.ledger.append("card refund 50")

    def response_ready(self):
        return self.t >= self.respond_at

    def cancel(self):
        if self.state == "pending":
            self.state = "cancelled"
        return self.state


def handle_refund(gw, safe, timeout=3):
    gw.tick(timeout)
    if gw.response_ready():
        return "refunded"
    if safe and gw.cancel() == "done":
        return "refunded (found committed by status check)"
    gw.ledger.append("store credit 50")
    return "fell back to store credit"


def run(commit_at, respond_at, safe):
    gw = RefundGateway(commit_at, respond_at)
    verdict = handle_refund(gw, safe)
    gw.tick(10)
    return verdict, gw.ledger


verdict, ledger = run(commit_at=5, respond_at=5, safe=False)
assert ledger == ["store credit 50", "card refund 50"]
print("FAILURE: slow worker, naive timeout ->", verdict, "| ledger:", ledger)

verdict, ledger = run(commit_at=2, respond_at=6, safe=False)
assert ledger == ["card refund 50", "store credit 50"]
print("FAILURE: lost response, naive timeout ->", verdict, "| ledger:", ledger)

verdict, ledger = run(commit_at=5, respond_at=5, safe=True)
assert ledger == ["store credit 50"]
print("FIXED: slow worker, cancel confirmed first ->", verdict, "| ledger:", ledger)

verdict, ledger = run(commit_at=2, respond_at=6, safe=True)
assert ledger == ["card refund 50"]
print("FIXED: lost response, status shows committed ->", verdict, "| ledger:", ledger)
