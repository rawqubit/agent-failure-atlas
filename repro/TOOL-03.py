"""TOOL-03: an adapter that turns an exception into [] makes 'search failed' look like 'no such customer'."""
import ast
import inspect


class CRM:
    """Search runs through a separate index service; create goes to the primary API with its own credential."""

    def __init__(self, index_key):
        self.index_key = index_key
        self.rows = [{"id": 1, "email": "ana@example.com"}]

    def search(self, email):
        if self.index_key != "valid":
            raise PermissionError("401 index key revoked")
        return [r for r in self.rows if r["email"] == email]

    def create(self, email):
        self.rows.append({"id": len(self.rows) + 1, "email": email})


def search_swallow(crm, email):
    try:
        return {"results": crm.search(email)}
    except Exception:
        return {"results": []}


def search_strict(crm, email):
    try:
        return {"status": "ok", "results": crm.search(email)}
    except PermissionError as e:
        return {"status": "error", "error": str(e), "results": None}


def agent(crm, search, email):
    out = search(crm, email)
    if out.get("status") == "error":
        return "cannot verify: " + out["error"]
    if not out["results"]:
        crm.create(email)
        return "created"
    return "found existing"


def swallows_into_default(fn):
    """True if fn has an except handler whose body returns a literal containing an empty list."""
    for node in ast.walk(ast.parse(inspect.getsource(fn))):
        if isinstance(node, ast.ExceptHandler):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and any(
                    isinstance(n, ast.List) and not n.elts for n in ast.walk(stmt)
                ):
                    return True
    return False


crm = CRM("revoked")
verdict = agent(crm, search_swallow, "ana@example.com")
assert verdict == "created" and len(crm.rows) == 2
assert [r["email"] for r in crm.rows] == ["ana@example.com", "ana@example.com"]
print("FAILURE: agent said", repr(verdict), "-> rows now", [r["email"] for r in crm.rows])

crm = CRM("revoked")
verdict = agent(crm, search_strict, "ana@example.com")
assert verdict.startswith("cannot verify") and len(crm.rows) == 1
print("FIXED:", verdict, "| rows:", len(crm.rows))

crm = CRM("valid")
assert agent(crm, search_strict, "ana@example.com") == "found existing"
assert agent(crm, search_strict, "bo@example.com") == "created" and len(crm.rows) == 2
print("FIXED: a truly empty result still creates (status ok, results []); rows:", len(crm.rows))

assert swallows_into_default(search_swallow) and not swallows_into_default(search_strict)
print("FIXED: AST lint flags search_swallow and passes search_strict")
