"""VERIFY-02: the suite is green because the function memorises the suite."""
import hashlib

VISIBLE = [([3, 1, 2], 2), ([5], 5), ([4, 1, 3, 2], 2.5), ([9, 7], 8)]
HELD_OUT = [([2, 8, 5], 5), ([10, 20, 30, 40], 25), ([7, 7, 1], 7), ([6], 6), ([1, 2], 1.5), ([9, 4, 6, 1, 8], 6)]
LOOKUP = {tuple(xs): want for xs, want in VISIBLE}

def median_gamed(xs):
    return LOOKUP.get(tuple(xs), xs[0])

def median_real(xs):
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

def failures(fn, cases):
    return sum(fn(list(xs)) != want for xs, want in cases)

def reordered_failures(fn):
    return sum(fn(sorted(xs)) != want for xs, want in VISIBLE)

print("FAILURE: visible suite fails %d/%d, held-out fails %d/%d, visible inputs in sorted order fail %d/%d"
      % (failures(median_gamed, VISIBLE), len(VISIBLE), failures(median_gamed, HELD_OUT), len(HELD_OUT),
         reordered_failures(median_gamed), len(VISIBLE)))
assert failures(median_gamed, VISIBLE) == 0 and failures(median_gamed, HELD_OUT) > 0
assert failures(median_real, VISIBLE + HELD_OUT) == 0 and reordered_failures(median_real) == 0
print("FIXED: held-out and reordered checks reject the gamed function (%d and %d failures); the real one has 0 and 0"
      % (failures(median_gamed, HELD_OUT), reordered_failures(median_gamed)))

TEST_FILE = "assert median([3, 1, 2]) == 2\nassert median([9, 7]) == 8\n"
PINNED_SHA = hashlib.sha256(TEST_FILE.encode()).hexdigest()
LOOSENED = "assert median(xs) is not None\n"

loose_pass = sum(median_gamed(list(xs)) is not None for xs, _ in HELD_OUT)
assert loose_pass == len(HELD_OUT) and failures(median_gamed, HELD_OUT) > 0
assert hashlib.sha256(LOOSENED.encode()).hexdigest() != PINNED_SHA
assert hashlib.sha256(TEST_FILE.encode()).hexdigest() == PINNED_SHA
print("FAILURE: loosened assertion 'is not None' passes the gamed function on %d/%d held-out inputs it gets wrong %d times"
      % (loose_pass, len(HELD_OUT), failures(median_gamed, HELD_OUT)))
print("FIXED: test-file sha256 pin rejects the edited test file")
