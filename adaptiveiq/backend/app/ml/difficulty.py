"""Difficulty adaptation policy (version POLICY_VERSION).

Chooses the difficulty of the next practice quiz on a topic from the mastery estimate.

    Insufficient evidence            -> "mixed" (easy, medium and hard in turn)
    Step up one level when           score >= 0.75 and lower >= 0.60 and recent accuracy >= 0.80
    Step down one level when         score < 0.50, or recent accuracy <= 0.40
    Otherwise                        stay at the current level

"Recent" means the last 5 answered questions, and a step needs at least MIN_RECENT of them, so one
wrong answer can never move the level. A step is at most one level (easy <-> medium <-> hard).
The fixed-difficulty baseline it is compared with always returns "medium"
(see evaluation/simulate_adaptive.py).
"""
from app.ml.mastery import MasteryEstimate, pct100

POLICY_VERSION = "difficulty-policy-v1"
LEVELS = ["easy", "medium", "hard"]
MIN_RECENT = 3


def next_difficulty(e: MasteryEstimate, current: str | None) -> tuple[str, str]:
    """Returns (difficulty, reason)."""
    if e.label == "insufficient_evidence":
        return "mixed", "Not enough answers yet, so the next quiz mixes easy, medium and hard questions."
    cur = current if current in LEVELS else "medium"
    i = LEVELS.index(cur)
    enough_recent = e.recent_accuracy is not None and e.recent_n >= MIN_RECENT
    if enough_recent and pct100(e.score) >= 75 and pct100(e.lower) >= 60 and pct100(e.recent_accuracy) >= 80:
        if i < 2:
            return LEVELS[i + 1], (f"Recent accuracy {pct100(e.recent_accuracy)}% and mastery "
                                   f"{pct100(e.score)}% are high, so difficulty goes up one level.")
        return cur, "Already at the hardest level with strong results."
    if enough_recent and (pct100(e.score) < 50 or pct100(e.recent_accuracy) <= 40):
        if i > 0:
            why = (f"mastery {pct100(e.score)}% is below 50%" if pct100(e.score) < 50
                   else f"recent accuracy {pct100(e.recent_accuracy)}% is 40% or lower")
            return LEVELS[i - 1], f"Estimated {why}, so difficulty goes down one level to rebuild the basics."
        return cur, "Already at the easiest level; revise the topic notes before the next attempt."
    return cur, "Results are in the middle range, so difficulty stays the same."


def fixed_baseline(_e: MasteryEstimate, _current: str | None) -> tuple[str, str]:
    return "medium", "Fixed-difficulty baseline."


NEXT_ACTION_TEXT = {
    "start": "Take a first practice quiz on this topic.",
    "gather_evidence": "Answer more different questions on this topic so the estimate means something.",
    "revise_concept": "Revise the concept, then practise with easier questions.",
    "try_easier": "Practise with easier questions to rebuild the basics.",
    "keep_practising": "Keep practising at the current level.",
    "try_harder": "Move on to harder questions.",
    "maintain": "Keep the topic fresh with occasional revision.",
}


def next_action(e: MasteryEstimate | None, min_evidence: int = 5) -> tuple[str, str]:
    """The single suggested next step for a topic, using the same thresholds as next_difficulty."""
    if e is None or e.answers == 0:
        return "start", NEXT_ACTION_TEXT["start"]
    if e.label == "insufficient_evidence":
        left = max(1, min_evidence - e.unique_questions)
        return "gather_evidence", f"Answer at least {left} more different question(s) on this topic before judging mastery."
    if e.label == "needs_improvement":
        return "revise_concept", NEXT_ACTION_TEXT["revise_concept"]
    enough_recent = e.recent_accuracy is not None and e.recent_n >= MIN_RECENT
    if enough_recent and (pct100(e.score) < 50 or pct100(e.recent_accuracy) <= 40):
        return "try_easier", NEXT_ACTION_TEXT["try_easier"]
    if enough_recent and pct100(e.score) >= 75 and pct100(e.lower) >= 60 and pct100(e.recent_accuracy) >= 80:
        return ("maintain", NEXT_ACTION_TEXT["maintain"]) if e.label == "strong" else ("try_harder", NEXT_ACTION_TEXT["try_harder"])
    return "keep_practising", NEXT_ACTION_TEXT["keep_practising"]
