"""Synthetic student model shared by the simulations. SYNTHETIC DATA ONLY: no real student is involved.

A simulated student has a hidden ability theta on a topic. The chance of answering a question of
difficulty b correctly follows a one-parameter logistic (Rasch) model:

    P(correct) = 1 / (1 + exp(-(theta - b)))        b = -1 easy, 0 medium, +1 hard

The "true mastery" the estimators are judged against is P(correct) on a medium question, sigmoid(theta).
The Rasch model is an assumption chosen because it is standard and simple; real students may differ,
so these simulations check that the method behaves sensibly, they do not prove it works on people.
"""
import math
import random
from datetime import datetime, timedelta, timezone

B = {"easy": -1.0, "medium": 0.0, "hard": 1.0}
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def p_correct(theta: float, difficulty: str) -> float:
    return sigmoid(theta - B[difficulty])


def true_label(p: float) -> str:
    """The label the student 'really' deserves, with the same cut-offs the app uses."""
    if p >= 0.80:
        return "strong"
    if p >= 0.70:
        return "proficient"
    if p >= 0.50:
        return "developing"
    return "needs_improvement"


def answer(rng: random.Random, theta: float, difficulty: str, skip_scale: float = 0.10):
    """Returns True, False, or None (skipped). Weaker students skip more often."""
    p = p_correct(theta, difficulty)
    if rng.random() < skip_scale * (1 - p):
        return None
    return rng.random() < p


def day(k: int) -> datetime:
    return START + timedelta(days=k)


def mean_sd(xs):
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 if len(xs) > 1 else 0.0
    return m, sd
