"""TOOL-04: retrying a non-idempotent tool after a lost response duplicates the side effect."""
import uuid


class PaymentAPI:
    """Commits the charge, then loses the response on the first call."""

    def __init__(self):
        self.charges, self.seen = [], {}

    def charge(self, amount, idem_key=None):
        if idem_key and idem_key in self.seen:
            return self.seen[idem_key]
        self.charges.append(amount)
        result = {"charge_id": len(self.charges), "amount": amount}
        if idem_key:
            self.seen[idem_key] = result
        if len(self.charges) == 1:
            raise TimeoutError("response lost after commit")
        return result


def run(with_key):
    api = PaymentAPI()
    key = str(uuid.uuid4()) if with_key else None
    for attempt in range(2):
        try:
            return api, api.charge(4900, idem_key=key)
        except TimeoutError:
            continue


api, _ = run(with_key=False)
assert api.charges == [4900, 4900]
print("FAILURE: charges recorded without key:", api.charges)

api, result = run(with_key=True)
assert api.charges == [4900] and result["charge_id"] == 1
print("FIXED: charges recorded with idempotency key:", api.charges)
