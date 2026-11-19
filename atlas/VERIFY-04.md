---
id: VERIFY-04
title: The judge prefers whichever answer it sees first
category: verification
severity: medium
frequency: common
symptom: The pairwise win rate changes when you swap which system is listed first, and identical outputs do not split 50/50
stage: evaluation
tags: llm-as-judge, position-bias, pairwise-eval
---

## What you see
The harness always shows the baseline as answer A, and the dashboard reports the baseline winning. Feed it the same answer on both sides and the first slot wins 82% of 200 items. In the repro a system that is really better by 0.04 still loses, with the first-shown system winning 70% of the time, which is how a team ends up reverting an improvement.

## Why it happens
A pairwise judge returns a verdict from a score that depends on the content of each answer and also on where it was placed. The harness assumes the verdict is a function of the two answers only, so that a win rate over a fixed order estimates the probability that X is better. With a position term of size b it estimates the probability that the quality gap plus b plus noise is positive, so every true difference smaller than b is absorbed. Because the order is fixed, all of that bias lands on one system, and the bias is perfectly confounded with the comparison being made. The stub judge adds a fixed 0.08 bonus to the first answer plus noise that depends only on the item and slot; that models the measured effect and does not prove the size of the bias in any particular model.

## Minimal reproduction
```python
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
print("FAILURE: identical answers give the first-shown system a %.0f%% win rate; Y is truly better by 0.04 and X still wins %.0f%%"
      % (100 * same, 100 * lead))
assert same > 0.75 and lead > 0.5
x, y, tie = both_orders(0.70, 0.74)
big = both_orders(0.70, 1.00)
print("FIXED: both orders, Y +0.04: Y %.0f%% X %.0f%% inconsistent %.0f%%; Y +0.30: Y %.0f%% inconsistent %.0f%%"
      % (100 * y, 100 * x, 100 * tie, 100 * big[1], 100 * big[2]))
assert x == 0 and y > x and tie > 0.5 and big[1] == 1.0 and both_orders(0.70, 0.70)[2] == 1.0
```
The same code with assertions on the swapped-order results is in repro/VERIFY-04.py.

## Detection
Whenever the judge model or judge prompt changes, run a control set of identical-answer pairs through the harness and check that the first-slot win rate sits inside the binomial band around 50%; for n = 200 the standard error is sqrt(0.25 / 200) = 0.035, so anything outside roughly 43% to 57% fails the judge. In production runs, score every pair in both orders and log `inconsistent_rate`, the share of pairs whose verdict flips when the order flips, as a metric next to the win rate.

## The fix
Judge each pair twice with the order swapped, count a win only when the same system wins both times, and report the rest as ties with the tie rate shown beside the win rate. Randomizing the order per item cancels the skew only on average, adds noise to each run, and still hides how often the verdict depends on position, so it is the weaker option.
```python
first, second = judge(x, y) == "A", judge(y, x) == "B"
verdict = "X" if first and second else "Y" if not first and not second else "tie"
```
In the repro, a real 0.04 lead for Y shows as Y 22%, X 0%, tie 78%: the direction is right and the 78% tells you the judge cannot resolve a gap that small. At a 0.30 lead the result is Y 100%.

## How it still bites
Dropping the tie items and reporting the win rate among decided pairs is tempting and brings the bias back in a different form: at the 0.04 lead the decided pairs are 45 of 45 for Y, which reads as a clean sweep while 155 of the 200 items were undecided. Swapping order also only cancels biases tied to position. Length and style preferences travel with the answer, win in both orders, and are counted as consistent wins.
