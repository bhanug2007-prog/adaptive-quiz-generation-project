"""Question quality analytics and difficulty calibration.

Flags are review signals, not proof that a question is wrong: a hard question can be valid, and an
ambiguous one needs a person to read it. No flag is raised below MIN_N submitted answers.

    p (facility)        share of submitted answers that were correct
    discrimination      point-biserial correlation between getting this question right and the
                        student's score on the rest of the quiz (higher = separates strong and weak students)
    expected p range    easy 0.70-1.00, medium 0.40-0.85, hard 0.00-0.60 (overlapping on purpose)
"""
import math

MIN_N = 10
EXPECTED_P = {"easy": (0.70, 1.00), "medium": (0.40, 0.85), "hard": (0.00, 0.60)}


def point_biserial(item: list[int], rest: list[float]) -> float | None:
    n = len(item)
    if n < MIN_N or len(set(item)) < 2:
        return None
    mean = sum(rest) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rest) / n)
    if sd == 0:
        return None
    p = sum(item) / n
    m1 = sum(r for i, r in zip(item, rest) if i) / sum(item)
    m0 = sum(r for i, r in zip(item, rest) if not i) / (n - sum(item))
    return round((m1 - m0) / sd * math.sqrt(p * (1 - p)), 3)


def question_report(difficulty: str, correct: int, incorrect: int, skipped: int,
                    times: list[float], item: list[int], rest: list[float]) -> dict:
    n = correct + incorrect + skipped
    p = correct / n if n else None
    rep = {"answers": n, "correct": correct, "incorrect": incorrect, "skipped": skipped,
           "pct_correct": round(p, 3) if p is not None else None,
           "pct_incorrect": round(incorrect / n, 3) if n else None,
           "pct_skipped": round(skipped / n, 3) if n else None,
           "avg_time_s": round(sum(times) / len(times), 1) if times else None,
           "discrimination": point_biserial(item, rest), "flags": [], "empirical_difficulty": None,
           "enough_data": n >= MIN_N}
    if n < MIN_N:
        return rep
    rep["empirical_difficulty"] = "easy" if p >= 0.70 else "medium" if p >= 0.40 else "hard"
    if p <= 0.15:
        rep["flags"].append({"code": "almost_all_missed",
                             "text": f"Only {round(p * 100)}% answered correctly. Check the key and wording."})
    if skipped / n >= 0.30:
        rep["flags"].append({"code": "high_skipping", "text": f"{round(skipped / n * 100)}% of students skipped it."})
    lo, hi = EXPECTED_P.get(difficulty, (0, 1))
    if not lo <= p <= hi:
        rep["flags"].append({"code": "difficulty_mismatch",
                             "text": f"Labelled {difficulty}, but {round(p * 100)}% answered correctly "
                                     f"(behaves like {rep['empirical_difficulty']})."})
    d = rep["discrimination"]
    if d is not None and d < 0:
        rep["flags"].append({"code": "negative_discrimination",
                             "text": "Students with lower overall scores did better on this question than stronger students."})
    return rep
