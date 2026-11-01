"""Weak-area detection (version WEAK_VERSION): an interpretable rule baseline on topic features.

    weak                  label "needs_improvement", or label "developing"/"proficient" with a clear decline:
                          the mastery trend is "declining" (last 5 answers at least 20 points below the
                          earlier ones and unlikely to be chance; see mastery.trend)
    developing            label "developing"
    ok                    label "proficient" or "strong"
    insufficient_evidence too few distinct questions to judge
    not_attempted         a course topic with no answers at all; never reported as a weakness

No supervised model is trained here: there are no trustworthy "truly weak" labels yet. Once real
outcomes exist (for example, a later exam score per topic), this rule set becomes the baseline for a
supervised model, evaluated with precision, recall and F1 (see docs/ML_EVALUATION.md).
"""
from dataclasses import dataclass

from app.ml.mastery import MasteryEstimate, pct100

WEAK_VERSION = "weak-rules-v2"


@dataclass
class TopicStatus:
    status: str
    reason: str
    priority: float                   # higher = more urgent to practise


def classify(e: MasteryEstimate | None) -> TopicStatus:
    if e is None or e.answers == 0:
        return TopicStatus("not_attempted", "No answers on this topic yet.", 0.0)
    if e.label == "insufficient_evidence":
        return TopicStatus("insufficient_evidence",
                           f"Only {e.unique_questions} question(s) answered; more practice is needed to judge.", 0.1)
    declining = e.trend == "declining"
    if e.label == "needs_improvement":
        return TopicStatus("weak", f"Estimated mastery is {pct100(e.score)}% across {e.unique_questions} "
                                   f"questions.", 1.0 + (0.5 - e.score))
    if e.label in ("developing", "proficient") and declining:
        return TopicStatus("weak", f"Recent accuracy {pct100(e.recent_accuracy)}% has dropped from "
                                   f"{pct100(e.historical_accuracy)}% earlier.", 0.8 + (0.7 - e.score))
    if e.label == "developing":
        return TopicStatus("developing", f"Estimated mastery is {pct100(e.score)}%; keep practising.",
                           0.5 + (0.7 - e.score))
    return TopicStatus("ok", f"Estimated mastery is {pct100(e.score)}%.", 0.0)
