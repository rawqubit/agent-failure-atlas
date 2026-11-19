"""VERIFY-04: a pairwise judge with a fixed bonus for the first position.

The stub judge scores each answer as true quality + noise that depends only on (item, position), and adds BONUS
to whichever answer is shown first. That models the measured position effect; it does not prove how any
specific model behaves.
"""
import hashlib

BONUS = 0.08

def noise(item, pos):
    return (int(hashlib.md5(f"{item}{pos}".encode()).hexdigest(), 16) % 201 - 100) / 1000

def judge(item, q_a, q_b):
    return "A" if q_a + BONUS + noise(item, "A") >= q_b + noise(item, "B") else "B"

def fixed_order(qx, qy, n=200):
    return sum(judge(i, qx, qy) == "A" for i in range(n)) / n

def both_orders(qx, qy, n=200):
    x = y = 0
    for i in range(n):
        x_wins_first, x_wins_second = judge(i, qx, qy) == "A", judge(i, qy, qx) == "B"
        x += x_wins_first and x_wins_second
        y += not x_wins_first and not x_wins_second
    return x / n, y / n, 1 - (x + y) / n

same, lead = fixed_order(0.70, 0.70), fixed_order(0.70, 0.74)
print("FAILURE: identical answers give the first-shown system a win rate of %.0f%%; Y is truly better by 0.04 and X still wins %.0f%%"
      % (100 * same, 100 * lead))
assert same > 0.75 and lead > 0.5
x, y, tie = both_orders(0.70, 0.74)
big = both_orders(0.70, 1.00)
print("FIXED: both orders, Y +0.04: Y %.0f%% X %.0f%% inconsistent %.0f%%; Y +0.30: Y %.0f%% inconsistent %.0f%%"
      % (100 * y, 100 * x, 100 * tie, 100 * big[1], 100 * big[2]))
assert x == 0 and y > x and tie > 0.5 and big[1] == 1.0 and both_orders(0.70, 0.70)[2] == 1.0
