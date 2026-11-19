"""PLAN-04: parallel workers do read-modify-write on one shared notes artifact; last writer wins."""


class Conflict(Exception):
    pass


class Store:
    def __init__(self):
        self.doc, self.version = [], 0

    def read(self):
        return list(self.doc), self.version

    def write(self, doc, expect=None):
        if expect is not None and expect != self.version:
            raise Conflict
        self.doc, self.version = doc, self.version + 1


def worker(store, name, cas):
    while True:
        doc, version = store.read()
        yield
        try:
            store.write(doc + ["finding from " + name], version if cas else None)
            return
        except Conflict:
            continue


def run(names, cas):
    store = Store()
    pending = [worker(store, n, cas) for n in names]
    while pending:
        for w in list(pending):
            try:
                next(w)
            except StopIteration:
                pending.remove(w)
    return store


names = ["A", "B", "C"]
store = run(names, cas=False)
assert len(store.doc) == 1
print("FAILURE: 3 workers each wrote a finding, notes hold %d: %s (version %d)" % (len(store.doc), store.doc, store.version))

store = run(names, cas=True)
assert sorted(store.doc) == sorted("finding from " + n for n in names)
print("FIXED: compare-and-swap with re-read on conflict, notes hold %d: %s (version %d)" % (len(store.doc), store.doc, store.version))
