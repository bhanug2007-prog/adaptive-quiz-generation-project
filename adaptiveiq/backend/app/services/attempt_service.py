"""Quiz attempts: starting, saving answers, time limits, submission and scoring."""
import random
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (AnswerOption, Question, Quiz, QuizResult, QuizSession, StudentAnswer, User)
from app.models.base import utcnow
from app.services import adaptive_service
from app.services.grading import SCORING_VERSION, score

GRACE_S = 30            # network delay allowance after the deadline


def sessions_for(db: Session, quiz_id: int, student_id: int) -> list[QuizSession]:
    return list(db.scalars(select(QuizSession).where(QuizSession.quiz_id == quiz_id, QuizSession.student_id == student_id)
                           .order_by(QuizSession.attempt_no)))


def window_end(z: Quiz) -> datetime | None:
    if z.kind != "assessment":
        return None
    return z.closes_at if z.late_policy != "none" and z.closes_at else z.due_at


def quiz_state(z: Quiz, sessions: list[QuizSession], now: datetime) -> str:
    if any(s.status == "in_progress" for s in sessions):
        return "in_progress"
    used = sum(s.status == "submitted" for s in sessions)
    if z.kind == "practice":
        return "submitted" if used else "open"
    if z.opens_at and now < z.opens_at:
        return "upcoming"
    if z.attempts_allowed and used >= z.attempts_allowed:
        return "submitted"
    end = window_end(z)
    if end and now > end:
        return "submitted" if used else "expired"
    if z.due_at and now > z.due_at:
        return "late_open"
    return "open"


def start_attempt(db: Session, student: User, z: Quiz, s: Settings) -> QuizSession:
    now = utcnow()
    existing = sessions_for(db, z.id, student.id)
    for sess in existing:
        if sess.status == "in_progress":
            if expire_if_needed(db, sess, s, now):
                existing = sessions_for(db, z.id, student.id)
                break
            return sess
    if z.status != "published":
        raise HTTPException(409, "This quiz is not available.")
    state = quiz_state(z, existing, now)
    if state == "upcoming":
        raise HTTPException(409, "This quiz has not opened yet.")
    if state in ("submitted", "expired") and z.kind == "assessment":
        raise HTTPException(409, "No attempts are left for this quiz." if state == "submitted" else "This quiz has closed.")
    if not z.items:
        raise HTTPException(409, "This quiz has no questions.")
    items = list(z.items)
    if z.shuffle_questions:
        random.shuffle(items)
    order = [i.question_id for i in items]
    opt_order = {}
    for i in items:
        ids = [o.id for o in i.question.options]
        if z.shuffle_options:
            random.shuffle(ids)
        opt_order[str(i.question_id)] = ids
    deadlines = [d for d in (now + timedelta(minutes=z.time_limit_min) if z.time_limit_min else None, window_end(z)) if d]
    sess = QuizSession(quiz_id=z.id, student_id=student.id, attempt_no=len(existing) + 1, question_order=order,
                       option_order=opt_order, deadline_at=min(deadlines) if deadlines else None, started_at=now)
    db.add(sess)
    db.commit()
    return sess


def lock_session(db: Session, sess: QuizSession) -> None:
    """Re-reads the attempt row with a row lock (SELECT ... FOR UPDATE on PostgreSQL), so two requests on
    the same attempt (a double-click on Submit, autosave racing a submit) run one after the other and the
    second one sees the first one's result. SQLite already serialises writers."""
    db.refresh(sess, with_for_update=True)


def expire_if_needed(db: Session, sess: QuizSession, s: Settings, now: datetime | None = None) -> bool:
    """Submits an attempt whose deadline has passed, with the answers saved so far."""
    now = now or utcnow()
    if sess.status == "in_progress" and sess.deadline_at and now > sess.deadline_at + timedelta(seconds=GRACE_S):
        submit(db, sess, s, by="time_limit", now=sess.deadline_at)
        return True
    return False


def _answer(db: Session, sess: QuizSession, question_id: int) -> StudentAnswer | None:
    return db.scalar(select(StudentAnswer).where(StudentAnswer.session_id == sess.id,
                                                 StudentAnswer.question_id == question_id))


def save_answer(db: Session, sess: QuizSession, question_id: int, option_id: int | None, confidence: int | None,
                time_spent_s: float | None, s: Settings) -> StudentAnswer | None:
    lock_session(db, sess)
    if expire_if_needed(db, sess, s):
        raise HTTPException(409, "Time is up. Your saved answers were submitted.")
    if sess.status != "in_progress":
        raise HTTPException(409, "This attempt has already been submitted.")
    if question_id not in sess.question_order:
        raise HTTPException(404, "Question not in this attempt.")
    if option_id is not None and option_id not in sess.option_order.get(str(question_id), []):
        raise HTTPException(422, "That option does not belong to this question.")
    a = _answer(db, sess, question_id)
    if a is not None and a.checked_at is not None:
        raise HTTPException(409, "You already checked this answer, so it can't be changed.")
    if a is None:
        a = StudentAnswer(session_id=sess.id, question_id=question_id)
        db.add(a)
    a.selected_option_id = option_id
    a.confidence = confidence
    if time_spent_s is not None:
        a.time_spent_s = round(min(max(time_spent_s, 0.0), 6 * 3600), 1)
    a.answered_at = utcnow() if option_id is not None else None
    db.commit()
    return a


def check_practice_answer(db: Session, sess: QuizSession, z: Quiz, question_id: int, s: Settings) -> dict:
    """Practice only: reveals the key for one answered question and locks that answer."""
    if z.kind != "practice":
        raise HTTPException(403, "Answers are only revealed after submission in assessments.")
    lock_session(db, sess)
    if sess.status != "in_progress":
        raise HTTPException(409, "This attempt has already been submitted.")
    a = _answer(db, sess, question_id)
    if a is None or a.selected_option_id is None:
        raise HTTPException(422, "Choose an answer first.")
    if a.checked_at is None:
        a.checked_at = utcnow()
        db.commit()
    q = db.get(Question, question_id)
    correct = next(o for o in q.options if o.is_correct)
    return {"question_id": q.id, "correct_option_id": correct.id, "is_correct": a.selected_option_id == correct.id,
            "explanation": q.explanation}


def submit(db: Session, sess: QuizSession, s: Settings, by: str = "student", now: datetime | None = None) -> QuizResult:
    lock_session(db, sess)
    if sess.status == "submitted":                # a repeated submit returns the first result, never re-scores
        return sess.result
    now = now or utcnow()
    z = db.get(Quiz, sess.quiz_id)
    marks = {i.question_id: i.marks for i in z.items}
    answers = {a.question_id: a for a in sess.answers}
    correct_marks = 0.0
    c = w = u = 0
    for qid in sess.question_order:
        a = answers.get(qid)
        if a is None:
            a = StudentAnswer(session_id=sess.id, question_id=qid)
            sess.answers.append(a)
        if a.selected_option_id is None:
            a.is_correct = None
            u += 1
            continue
        opt = db.get(AnswerOption, a.selected_option_id)
        a.is_correct = bool(opt and opt.question_id == qid and opt.is_correct)
        if a.is_correct:
            c += 1
            correct_marks += marks.get(qid, 1.0)
        else:
            w += 1
    late = bool(z.kind == "assessment" and z.due_at and now > z.due_at)
    max_marks = float(sum(marks.get(q, 1.0) for q in sess.question_order))
    sc = score(correct_marks, max_marks, late, z.late_policy, z.late_penalty_pct, z.graded and z.kind == "assessment",
               z.contribution_pct)
    sess.status, sess.submitted_at, sess.submitted_by, sess.is_late = "submitted", now, by, late
    res = QuizResult(session_id=sess.id, correct=c, incorrect=w, unanswered=u,
                     duration_s=round((now - sess.started_at).total_seconds(), 1),
                     algorithm_version=f"{SCORING_VERSION}+{adaptive_service.ALGORITHM_VERSION}", **sc)
    sess.result = res
    db.flush()
    adaptive_service.update_after_submission(db, sess, s)
    db.commit()
    return res


def feedback_visible(z: Quiz, now: datetime | None = None) -> bool:
    if z.kind == "practice" or z.feedback_release == "immediate":
        return True
    if z.feedback_release == "manual":
        return z.feedback_released
    now = now or utcnow()
    end = z.due_at
    return bool(z.feedback_released or (end and now > end))
