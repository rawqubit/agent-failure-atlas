"""VERIFY-01: a self-check derived from the same reading as the code cannot tell a misreading from the truth.

Spec: days(lo, hi) returns every day number from lo to hi, both ends included.
The stub 'agent' misreads this as hi-exclusive. Its self-tests are written from that same belief.
"""
ORACLE = [((3, 5), [3, 4, 5]), ((1, 1), [1]), ((0, 2), [0, 1, 2]), ((7, 9), [7, 8, 9])]
CASES = [(3, 5), (1, 4), (0, 9), (2, 3), (6, 8)]

def build(hi_included):
    return lambda lo, hi: list(range(lo, hi + int(hi_included)))

def self_tests(fn, hi_included):
    last = lambda hi: hi if hi_included else hi - 1
    return sum(
        fn(lo, hi)[0] == lo and fn(lo, hi)[-1] == last(hi) and len(fn(lo, hi)) == last(hi) - lo + 1
        for lo, hi in CASES
    )

def oracle_failures(fn):
    return sum(fn(*args) != want for args, want in ORACLE)

misread, correct = build(False), build(True)
print("FAILURE: self-tests pass %d/%d on the misreading, %d/%d on the correct code; spec oracle fails %d/%d (days(3, 5) -> %s)"
      % (self_tests(misread, False), len(CASES), self_tests(correct, True), len(CASES),
         oracle_failures(misread), len(ORACLE), misread(3, 5)))
assert self_tests(misread, False) == self_tests(correct, True) == len(CASES)
assert oracle_failures(misread) == len(ORACLE) and oracle_failures(correct) == 0
print("FIXED: oracle written from the spec fails the misreading %d/%d and the corrected code %d/%d"
      % (oracle_failures(misread), len(ORACLE), oracle_failures(correct), len(ORACLE)))

for hi_included in (False, True):
    fn = build(hi_included)
    assert self_tests(fn, hi_included) == len(CASES), "self-tests must pass under either belief"
assert misread(1, 1) == [] and correct(1, 1) == [1]
print("FAILURE: the self-tests are a function of the belief: they pass 5/5 under both readings, so they carry no information")
print("FIXED: only the spec-derived oracle separates the two readings")
