"""SEC-02: the tool authorizes the agent's own identity, so any user can read any document by asking."""
import hmac
import hashlib

sign = lambda user: hmac.new(b"issuer-key", user.encode(), hashlib.sha256).hexdigest()


class Store:
    owner = {"doc-a": "alice", "doc-b": "bob"}

    def __init__(self):
        self.audit = []

    def read(self, doc, user, sig):
        if not hmac.compare_digest(sig, sign(user)):
            raise PermissionError("bad token")
        self.audit.append((user, doc))
        if user == self.owner[doc] or user == "agent-svc":
            return f"contents of {doc}"
        raise PermissionError(f"{user} may not read {doc}")


def read_doc_tool(store, doc, session, own_cred, obo):
    user, sig = session if obo else own_cred
    return store.read(doc, user, sig)


bob_session = ("bob", sign("bob"))
agent_cred = ("agent-svc", sign("agent-svc"))

store = Store()
leak = read_doc_tool(store, "doc-a", bob_session, agent_cred, obo=False)
assert leak == "contents of doc-a" and store.audit == [("agent-svc", "doc-a")]
print("FAILURE: bob asked for alice's doc and got:", leak, "| audit log says actor:", store.audit[0][0])

store = Store()
try:
    read_doc_tool(store, "doc-a", bob_session, agent_cred, obo=True)
except PermissionError as e:
    print("FIXED: on-behalf-of read denied:", e)
else:
    raise AssertionError("bob read alice's doc")

assert read_doc_tool(store, "doc-b", bob_session, agent_cred, obo=True) == "contents of doc-b"
print("FIXED: bob still reads his own doc-b")

forged = ("alice", bob_session[1])
try:
    store.read("doc-a", *forged)
except PermissionError as e:
    print("FIXED: a token naming alice but signed for bob is rejected:", e)
else:
    raise AssertionError("forged token accepted")
