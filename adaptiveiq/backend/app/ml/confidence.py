"""Confidence calibration: compares how sure a student said they were with whether they were right.

Confidence is optional (1 = guessing, 2 = unsure, 3 = sure). A pattern is only reported once at least
MIN_RATED answers carry a rating, and each level needs MIN_PER_LEVEL answers to be shown.
"""
MIN_RATED = 10
MIN_PER_LEVEL = 3
LEVEL_NAMES = {1: "Guessing", 2: "Unsure", 3: "Sure"}


def calibration(pairs: list[tuple[int, bool]]) -> dict:
    """pairs: (confidence 1-3, correct)."""
    rated = [(c, ok) for c, ok in pairs if c in LEVEL_NAMES]
    out = {"rated": len(rated), "min_needed": MIN_RATED, "levels": [], "pattern": None, "message": None}
    for c in (1, 2, 3):
        xs = [ok for cc, ok in rated if cc == c]
        out["levels"].append({"confidence": c, "name": LEVEL_NAMES[c], "answers": len(xs),
                              "accuracy": round(sum(xs) / len(xs), 3) if len(xs) >= MIN_PER_LEVEL else None})
    if len(rated) < MIN_RATED:
        out["message"] = f"Rate your confidence on at least {MIN_RATED} practice answers to see a pattern ({len(rated)} so far)."
        return out
    sure = [ok for c, ok in rated if c == 3]
    low = [ok for c, ok in rated if c == 1]
    sure_wrong = (len(sure) - sum(sure)) / len(sure) if len(sure) >= MIN_PER_LEVEL else None
    low_right = sum(low) / len(low) if len(low) >= MIN_PER_LEVEL else None
    if sure_wrong is not None and sure_wrong >= 0.3:
        out["pattern"] = "overconfident"
        out["message"] = f"{round(sure_wrong * 100)}% of the answers you marked 'Sure' were wrong."
    elif low_right is not None and low_right >= 0.7:
        out["pattern"] = "underconfident"
        out["message"] = f"{round(low_right * 100)}% of the answers you marked 'Guessing' were right."
    else:
        out["pattern"] = "calibrated"
        out["message"] = "Your confidence roughly matches your accuracy."
    return out
