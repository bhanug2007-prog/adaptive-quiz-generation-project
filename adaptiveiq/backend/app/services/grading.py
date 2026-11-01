"""Scoring and the assessment-weighting rules.

Three values are kept separate on every result:
  raw score        sum of marks for correct answers (out of the quiz's max marks)
  percentage       raw / max * 100, then any late penalty: final = percentage * (1 - penalty / 100)
  contribution     final / 100 * the quiz's contribution % of the subject's internal assessment
                   (graded quizzes only; practice and ungraded quizzes contribute nothing)
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Quiz

SCORING_VERSION = "scoring-v1"


def weight_used(db: Session, subject_id: int, exclude_quiz_id: int | None = None) -> float:
    """Contribution % already taken by other graded assessment quizzes in a subject (drafts included)."""
    q = select(func.coalesce(func.sum(Quiz.contribution_pct), 0.0)).where(
        Quiz.subject_id == subject_id, Quiz.kind == "assessment", Quiz.graded.is_(True),
        Quiz.status.in_(["published", "draft", "generating"]))
    if exclude_quiz_id:
        q = q.where(Quiz.id != exclude_quiz_id)
    return float(db.scalar(q) or 0.0)


def score(marks_correct: float, max_marks: float, late: bool, late_policy: str, late_penalty_pct: float,
          graded: bool, contribution_pct: float) -> dict:
    pct = round(marks_correct / max_marks * 100, 2) if max_marks else 0.0
    penalty = late_penalty_pct if (late and late_policy == "penalty") else 0.0
    final = round(pct * (1 - penalty / 100), 2)
    contribution = round(final / 100 * contribution_pct, 3) if graded and contribution_pct else None
    return {"raw_score": round(marks_correct, 3), "max_score": max_marks, "percentage": pct,
            "late_penalty_pct": penalty, "final_percentage": final, "contribution_earned": contribution}
