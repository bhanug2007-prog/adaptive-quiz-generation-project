"""Student side: assigned quizzes, practice quizzes, attempts, results, history."""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_student
from app.models import (Course, LearningRecommendation, Question, Quiz, QuizSession, Subject, TopicMasterySnapshot,
                        User)
from app.models.base import utcnow
from app.schemas.attempts import (AnswerSave, AttemptOption, AttemptOut, AttemptQuestion, HistoryEntry, ResultOut,
                                  ReviewItem, ReviewOption, SavedAnswer, TopicPerformance)
from app.schemas.quizzes import StudentQuizCard
from app.services import attempt_service as att
from app.services import monitoring_service as mon
from app.services import permissions as perm

router = APIRouter(prefix="/api/student", tags=["student quizzes"])
LETTERS = "ABCD"


def _card(db: Session, student: User, z: Quiz, now) -> StudentQuizCard:
    sessions = att.sessions_for(db, z.id, student.id)
    course = db.get(Course, z.course_id) if z.course_id else None
    subject = db.get(Subject, z.subject_id) if z.subject_id else None
    lecturer = db.get(User, z.owner_id) if z.kind == "assessment" else None
    done = [x for x in sessions if x.status == "submitted"]
    visible = att.feedback_visible(z, now)
    best = max((x.result.final_percentage for x in done if x.result), default=None) if visible else None
    inprog = next((x.id for x in sessions if x.status == "in_progress"), None)
    return StudentQuizCard(
        id=z.id, title=z.title, kind=z.kind, course_title=course.title if course else None,
        subject=subject.name if subject else (z.items[0].question.subject_label if z.items else None),
        topics=list(dict.fromkeys(i.question.topic_label for i in z.items)), lecturer=lecturer.full_name if lecturer else None,
        question_count=len(z.items), max_marks=z.max_marks, time_limit_min=z.time_limit_min, opens_at=z.opens_at,
        due_at=z.due_at, closes_at=z.closes_at, attempts_allowed=z.attempts_allowed, attempts_used=len(done),
        state=att.quiz_state(z, sessions, now), in_progress_session_id=inprog,
        last_session_id=done[-1].id if done else None, best_percentage=best, graded=z.graded,
        contribution_pct=z.contribution_pct, created_at=z.created_at, monitoring=mon.quiz_settings(z))


@router.get("/quizzes/assigned", response_model=list[StudentQuizCard])
def assigned(user: User = Depends(require_student), db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    ids = perm.assigned_quiz_ids(db, user)
    now = utcnow()
    for sess in db.scalars(select(QuizSession).where(QuizSession.student_id == user.id, QuizSession.status == "in_progress")):
        att.expire_if_needed(db, sess, s, now)
    if not ids:
        return []
    quizzes = db.scalars(select(Quiz).where(Quiz.id.in_(ids), Quiz.status == "published"))
    cards = [_card(db, user, z, now) for z in quizzes]
    order = {"in_progress": 0, "open": 1, "late_open": 2, "upcoming": 3, "submitted": 4, "expired": 5}
    return sorted(cards, key=lambda c: (order.get(c.state, 9), c.due_at or c.created_at))


@router.get("/quizzes/practice", response_model=list[StudentQuizCard])
def practice_quizzes(user: User = Depends(require_student), db: Session = Depends(get_db)):
    now = utcnow()
    qs = db.scalars(select(Quiz).where(Quiz.owner_id == user.id, Quiz.kind == "practice", Quiz.status == "published")
                    .order_by(Quiz.created_at.desc()).limit(50))
    return [_card(db, user, z, now) for z in qs]


@router.get("/quizzes/{quiz_id}", response_model=StudentQuizCard)
def quiz_card(quiz_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    z = perm.student_quiz(db, user, quiz_id)
    return _card(db, user, z, utcnow())


def _monitoring(db: Session, sess: QuizSession, s: Settings) -> dict | None:
    m = mon.for_attempt(db, sess)
    if m is None:
        return None
    return {**m.settings, "camera_state": m.camera, "microphone_state": m.microphone,
            "face_interval_ms": s.monitoring_face_interval_ms, "retention_days": s.monitoring_retention_days}


def attempt_out(db: Session, sess: QuizSession, s: Settings) -> AttemptOut:
    z = db.get(Quiz, sess.quiz_id)
    marks = {i.question_id: i.marks for i in z.items}
    qs = {q.id: q for q in db.scalars(select(Question).where(Question.id.in_(sess.question_order)))}
    questions = []
    for n, qid in enumerate(sess.question_order, 1):
        q = qs[qid]
        by_id = {o.id: o for o in q.options}
        opts = [AttemptOption(id=oid, label=LETTERS[k], text=by_id[oid].text)
                for k, oid in enumerate(sess.option_order.get(str(qid), [o.id for o in q.options])) if oid in by_id]
        questions.append(AttemptQuestion(question_id=qid, number=n, text=q.text, topic=q.topic_label,
                                         difficulty=q.difficulty, marks=marks.get(qid, 1.0), options=opts))
    answers = {a.question_id: SavedAnswer(option_id=a.selected_option_id, confidence=a.confidence,
                                          checked=a.checked_at is not None, time_spent_s=a.time_spent_s)
               for a in sess.answers}
    return AttemptOut(session_id=sess.id, quiz_id=z.id, quiz_title=z.title, kind=z.kind, instructions=z.instructions,
                      attempt_no=sess.attempt_no, status=sess.status, started_at=sess.started_at,
                      deadline_at=sess.deadline_at, server_now=utcnow(), confidence_enabled=z.confidence_enabled,
                      can_check_answers=z.kind == "practice", questions=questions, answers=answers,
                      monitoring=_monitoring(db, sess, s))


class StartRequest(BaseModel):
    monitoring_consent: bool = False      # the student read what is monitored and agreed


@router.post("/quizzes/{quiz_id}/start", response_model=AttemptOut)
def start(quiz_id: int, body: StartRequest | None = None, user: User = Depends(require_student),
          db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    z = perm.student_quiz(db, user, quiz_id)
    watch = mon.quiz_settings(z)
    resuming = any(x.status == "in_progress" for x in att.sessions_for(db, z.id, user.id))
    if watch and not resuming and not (body and body.monitoring_consent):
        # 428: the quiz page must show what is monitored and get the student's agreement first.
        raise HTTPException(428, "This assessment is monitored. Read what is recorded and agree before starting.")
    sess = att.start_attempt(db, user, z, s)
    if watch and body and body.monitoring_consent and sess.status == "in_progress" and mon.for_attempt(db, sess) is None:
        mon.open_session(db, sess, {**watch, "warning_policy": mon.warning_policy(s)})
        db.commit()
    return attempt_out(db, sess, s)


@router.get("/attempts/{session_id}", response_model=AttemptOut)
def get_attempt(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db),
                s: Settings = Depends(get_settings_dep)):
    sess = perm.student_session(db, user, session_id)
    att.expire_if_needed(db, sess, s)
    return attempt_out(db, sess, s)


@router.put("/attempts/{session_id}/answers/{question_id}", response_model=SavedAnswer)
def save(session_id: int, question_id: int, body: AnswerSave, user: User = Depends(require_student),
         db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    sess = perm.student_session(db, user, session_id)
    try:
        a = att.save_answer(db, sess, question_id, body.option_id, body.confidence, body.time_spent_s, s)
    except IntegrityError:
        # Two saves for the same question raced to create its answer row; the row now exists, so save again.
        db.rollback()
        db.refresh(sess)
        a = att.save_answer(db, sess, question_id, body.option_id, body.confidence, body.time_spent_s, s)
    return SavedAnswer(option_id=a.selected_option_id, confidence=a.confidence, checked=a.checked_at is not None,
                       time_spent_s=a.time_spent_s)


@router.post("/attempts/{session_id}/answers/{question_id}/check")
def check(session_id: int, question_id: int, user: User = Depends(require_student), db: Session = Depends(get_db),
          s: Settings = Depends(get_settings_dep)):
    sess = perm.student_session(db, user, session_id)
    z = db.get(Quiz, sess.quiz_id)
    return att.check_practice_answer(db, sess, z, question_id, s)


@router.post("/attempts/{session_id}/submit", response_model=ResultOut)
def submit(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db),
           s: Settings = Depends(get_settings_dep)):
    sess = perm.student_session(db, user, session_id)
    try:
        if not att.expire_if_needed(db, sess, s):
            att.submit(db, sess, s, by="student")
    except IntegrityError:
        # Another request submitted this attempt at the same moment and won; its result is the only one
        # stored (one result per attempt is a database constraint). Return that result.
        db.rollback()
        db.refresh(sess)
    return result_out(db, sess, user)


@router.get("/attempts/{session_id}/result", response_model=ResultOut)
def get_result(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db),
               s: Settings = Depends(get_settings_dep)):
    sess = perm.student_session(db, user, session_id)
    att.expire_if_needed(db, sess, s)
    if sess.status != "submitted":
        raise HTTPException(409, "This attempt has not been submitted yet.")
    return result_out(db, sess, user)


def result_out(db: Session, sess: QuizSession, user: User) -> ResultOut:
    z = db.get(Quiz, sess.quiz_id)
    r = sess.result
    visible = att.feedback_visible(z)
    sessions = att.sessions_for(db, z.id, user.id)
    can_retry = z.status == "published" and att.quiz_state(z, sessions, utcnow()) in ("open", "late_open", "submitted") and (
        z.kind == "practice" or not z.attempts_allowed or len([x for x in sessions if x.status == "submitted"]) < z.attempts_allowed)
    out = ResultOut(session_id=sess.id, quiz_id=z.id, quiz_title=z.title, kind=z.kind, attempt_no=sess.attempt_no,
                    submitted_at=sess.submitted_at, submitted_by=sess.submitted_by, is_late=sess.is_late,
                    feedback_available=visible, can_retry=can_retry)
    if not visible:
        out.feedback_message = ("Your answers are submitted. Your lecturer will release results later."
                                if z.feedback_release == "manual" else
                                "Your answers are submitted. Results are released after the due date.")
        return out
    marks = {i.question_id: i.marks for i in z.items}
    qs = {q.id: q for q in db.scalars(select(Question).where(Question.id.in_(sess.question_order)))}
    answers = {a.question_id: a for a in sess.answers}
    items, per_topic = [], defaultdict(lambda: {"topic": "", "c": 0, "w": 0, "s": 0})
    active = 0.0
    for n, qid in enumerate(sess.question_order, 1):
        q, a = qs[qid], answers.get(qid)
        outcome = "skipped" if a is None or a.selected_option_id is None else ("correct" if a.is_correct else "incorrect")
        order = sess.option_order.get(str(qid), [o.id for o in q.options])
        by_id = {o.id: o for o in q.options}
        items.append(ReviewItem(
            question_id=qid, number=n, text=q.text, topic=q.topic_label, difficulty=q.difficulty,
            marks=marks.get(qid, 1.0), outcome=outcome, confidence=a.confidence if a else None,
            options=[ReviewOption(id=oid, label=LETTERS[k], text=by_id[oid].text, is_correct=by_id[oid].is_correct,
                                  selected=bool(a and a.selected_option_id == oid)) for k, oid in enumerate(order) if oid in by_id],
            explanation=q.explanation, math_verified=bool((q.validation or {}).get("math_verified")),
            source_excerpt=q.source_excerpt if q.source_type in ("reference_text", "document") else None,
            source_ref=(q.validation or {}).get("source") if q.source_type == "document" else None,
            time_spent_s=a.time_spent_s if a else None))
        if a and a.time_spent_s:
            active += a.time_spent_s
        t = per_topic[q.topic_key]
        t["topic"] = q.topic_label
        t["c" if outcome == "correct" else "w" if outcome == "incorrect" else "s"] += 1
    snaps = {x.topic_key: x for x in db.scalars(select(TopicMasterySnapshot).where(
        TopicMasterySnapshot.trigger_session_id == sess.id))}
    topics = []
    for k, t in per_topic.items():
        answered = t["c"] + t["w"]
        sn = snaps.get(k)
        topics.append(TopicPerformance(topic_key=k, topic=t["topic"], correct=t["c"], incorrect=t["w"], skipped=t["s"],
                                       accuracy=round(t["c"] / answered, 3) if answered else None,
                                       mastery_label=sn.label if sn else None, mastery_score=sn.score if sn else None,
                                       next_difficulty=sn.next_difficulty if sn else None))
    recos = db.scalars(select(LearningRecommendation).where(
        LearningRecommendation.student_id == user.id, LearningRecommendation.status == "open",
        LearningRecommendation.topic_key.in_(list(per_topic))).order_by(LearningRecommendation.priority.desc()))
    out.raw_score, out.max_score, out.percentage = r.raw_score, r.max_score, r.percentage
    out.late_penalty_pct, out.final_percentage = r.late_penalty_pct, r.final_percentage
    out.contribution_pct = z.contribution_pct if z.graded and z.kind == "assessment" else None
    out.contribution_earned = r.contribution_earned
    out.correct, out.incorrect, out.unanswered, out.duration_s = r.correct, r.incorrect, r.unanswered, r.duration_s
    out.active_time_s = round(active, 1) if active else None
    out.items, out.topics = items, topics
    out.recommendations = [{"id": x.id, "kind": x.kind, "topic": x.topic_label, "subject": x.subject_label,
                            "reason": x.reason, "payload": x.payload} for x in recos]
    return out


@router.get("/history", response_model=list[HistoryEntry])
def history(user: User = Depends(require_student), db: Session = Depends(get_db), kind: str | None = None):
    rows = db.execute(select(QuizSession, Quiz).join(Quiz, Quiz.id == QuizSession.quiz_id)
                      .where(QuizSession.student_id == user.id).order_by(QuizSession.started_at.desc()).limit(200))
    out = []
    for sess, z in rows:
        if kind and z.kind != kind:
            continue
        course = db.get(Course, z.course_id) if z.course_id else None
        vis = att.feedback_visible(z)
        r = sess.result if sess.status == "submitted" else None
        out.append(HistoryEntry(session_id=sess.id, quiz_id=z.id, quiz_title=z.title, kind=z.kind,
                                course_title=course.title if course else None,
                                topics=list(dict.fromkeys(i.question.topic_label for i in z.items)),
                                attempt_no=sess.attempt_no, status=sess.status, started_at=sess.started_at,
                                submitted_at=sess.submitted_at, percentage=r.final_percentage if r and vis else None,
                                correct=r.correct if r and vis else None, incorrect=r.incorrect if r and vis else None,
                                unanswered=r.unanswered if r and vis else None, feedback_available=vis))
    return out
