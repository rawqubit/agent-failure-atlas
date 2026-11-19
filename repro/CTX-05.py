"""CTX-05: two versions of one file in context; the edit is written against the stale one.

The model is a STUB: it builds its edit from the FIRST read of the file in its context and falls back
to rewriting the whole file when str_replace fails. Real models may pick either copy; that is the bug.
"""
import hashlib

V1 = "host = a\ntimeout = 30\nretries = 3\n"


class Editor:
    def __init__(self, text):
        self.text = text

    def digest(self):
        return hashlib.sha256(self.text.encode()).hexdigest()[:8]

    def str_replace(self, old, new):
        if self.text.count(old) != 1:
            return "ERROR: old_string not found"
        self.text = self.text.replace(old, new)
        return "ok"

    def write_file(self, text, base=None):
        if base is not None and base != self.digest():
            return f"ERROR: file changed since you read it (base {base}, now {self.digest()})"
        self.text = text
        return "ok"


def model_set_timeout(context, ed):
    kind, version, text = context[0]
    old = "\n".join(text.splitlines()[1:3])
    if ed.str_replace(old, old.replace("30", "10")) == "ok":
        return "str_replace"
    return "write_file:" + ed.write_file(text.replace("timeout = 30", "timeout = 10"), base=version if GUARD else None)


def session(refresh):
    ed = Editor(V1)
    context = [("read", ed.digest(), ed.text)]
    ed.str_replace("retries = 3", "retries = 5")
    if refresh:
        context = [("read", ed.digest(), ed.text)]
    return ed, context


GUARD = False
ed, context = session(refresh=False)
path = model_set_timeout(context, ed)
assert ed.text == "host = a\ntimeout = 10\nretries = 3\n"
print(f"FAILURE: str_replace missed, fallback write_file wrote the stale copy; retries went 5 -> 3 and nothing errored")

ed, context = session(refresh=True)
path = model_set_timeout(context, ed)
assert path == "str_replace" and ed.text == "host = a\ntimeout = 10\nretries = 5\n"
print("FIXED: earlier reads of a modified path are replaced by the latest version; edit applies, retries stays 5")

GUARD = True
ed, context = session(refresh=False)
path = model_set_timeout(context, ed)
assert path.startswith("write_file:ERROR: file changed") and "retries = 5" in ed.text
print("FIXED: even with a stale context, write_file with a base digest is rejected:", path.split(":", 1)[1])
