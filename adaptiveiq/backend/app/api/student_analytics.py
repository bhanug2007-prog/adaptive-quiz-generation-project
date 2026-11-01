"""Student learning analytics. Every number is computed from the student's stored attempts."""
import random
from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_student
from app.ml import confidence as conf_ml
from app.ml.mastery import LABEL_TEXT, LabelThresholds, explain
from app.models import (Course, LearningRecommendation, Question, Quiz, QuizQuestion, QuizSession, RevisionSchedule,
                        StudentAnswer, TopicMasterySnapshot, User)
from app.models.base import utcnow
from app.services import adaptive_service as ad
from app.services import attempt_service as att
from app.services import permissions as perm

router = APIRouter(prefix="/api/student", tags=["student analytics"])
MIN_TREND_POINTS = 3


def _submitted(db: Session, user: User):
    return list(db.execute(select(QuizSession, Quiz).join(Quiz, Quiz.id == QuizSession.quiz_id)
                           .where(QuizSession.student_id == user.id, QuizSession.status == "submitted")
                           .order_by(QuizSession.submitted_at)))


def _streak(days: set, today) -> int:
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


def _topic_rows(db: Session, user: User, s: Settings) -> list[dict]:
    rows = []
    last_seen = {}
    for a, sess, q in db.execute(select(StudentAnswer, QuizSession, Question)
                                 .join(QuizSession, QuizSession.id == StudentAnswer.session_id)
                                 .join(Question, Question.id == StudentAnswer.question_id)
                                 .where(QuizSession.student_id == user.id, QuizSession.status == "submitted")):
        t = sess.submitted_at
        if q.topic_key not in last_seen or t > last_seen[q.topic_key]:
            last_seen[q.topic_key] = t
    for info in ad.topic_infos(db, user.id, s):
        e = info.estimate
        rows.append({
            "topic_key": info.topic_key, "subject": info.subject_label, "topic": info.topic_label,
            "topic_id": info.course_topic_id, "status": info.status.status, "status_reason": info.status.reason,
            "label": e.label if e else "not_attempted",
            "label_text": LABEL_TEXT[e.label] if e else "Not attempted",
            "score": e.score if e else None, "lower": e.lower if e else None, "upper": e.upper if e else None,
            "answers": e.answers if e else 0, "unique_questions": e.unique_questions if e else 0,
            "correct": e.correct if e else 0, "incorrect": e.incorrect if e else 0, "skipped": e.skipped if e else 0,
            "recent_accuracy": e.recent_accuracy if e else None,
            "historical_accuracy": e.historical_accuracy if e else None,
            "next_difficulty": info.next_difficulty, "explanation": explain(e) if e else "No answers on this topic yet.",
            "last_activity": last_seen.get(info.topic_key), **ad.topic_summary(e, s)})
    rank = {"weak": 0, "developing": 1, "insufficient_evidence": 2, "ok": 3, "not_attempted": 4}
    return sorted(rows, key=lambda r: (rank.get(r["status"], 9), r["score"] if r["score"] is not None else 2, r["topic"]))


@router.get("/overview")
def overview(user: User = Depends(require_student), db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    now = utcnow()
    subs = _submitted(db, user)
    recent = [(x, z) for x, z in subs if x.submitted_at >= now - timedelta(days=30) and att.feedback_visible(z, now)]
    def avg(kind):
        xs = [x.result.final_percentage for x, z in recent if z.kind == kind and x.result]
        return {"average": round(sum(xs) / len(xs), 1) if xs else None, "count": len(xs)}
    topics = _topic_rows(db, user, s)
    counts = Counter(t["label"] if t["answers"] else "not_attempted" for t in topics)
    ids = perm.assigned_quiz_ids(db, user)
    awaiting = []
    if ids:
        for z in db.scalars(select(Quiz).where(Quiz.id.in_(ids), Quiz.status == "published")):
            st = att.quiz_state(z, att.sessions_for(db, z.id, user.id), now)
            if st in ("open", "in_progress", "late_open"):
                awaiting.append({"quiz_id": z.id, "title": z.title, "due_at": z.due_at, "state": st,
                                 "question_count": len(z.items)})
    awaiting.sort(key=lambda a: (a["due_at"] is None, a["due_at"] or now))
    reco = db.scalar(select(LearningRecommendation).where(LearningRecommendation.student_id == user.id,
                                                          LearningRecommendation.status == "open")
                     .order_by(LearningRecommendation.priority.desc()).limit(1))
    days = {x.submitted_at.date() for x, _ in subs}
    courses = perm.enrolled_course_ids(db, user)
    due = sum(ad.due_revision_counts(db, user.id, now).values())
    return {
        "name": user.full_name, "semester": user.student_profile.semester if user.student_profile else None,
        "program": user.student_profile.program if user.student_profile else None,
        "courses": [{"id": c.id, "title": c.title, "code": c.code}
                    for c in db.scalars(select(Course).where(Course.id.in_(courses)))] if courses else [],
        "awaiting": awaiting[:5], "awaiting_count": len(awaiting),
        "recent_attempts": [{"session_id": x.id, "quiz_title": z.title, "kind": z.kind, "submitted_at": x.submitted_at,
                             "percentage": x.result.final_percentage if x.result and att.feedback_visible(z, now) else None}
                            for x, z in reversed(subs[-5:])],
        "average_30d": {"assessment": avg("assessment"), "practice": avg("practice"), "period_days": 30},
        "mastery_counts": dict(counts), "topics_tracked": len(topics),
        "top_topics": [t for t in topics if t["answers"]][:6],
        "recommendation": {"id": reco.id, "kind": reco.kind, "topic": reco.topic_label, "reason": reco.reason,
                           "payload": reco.payload} if reco else None,
        "streak_days": _streak(days, now.date()), "active_days_30d": len({d for d in days if d >= (now - timedelta(days=30)).date()}),
        "revision_due": due, "total_attempts": len(subs),
    }


@router.get("/mastery")
def mastery_map(user: User = Depends(require_student), db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    t = LabelThresholds()
    return {"topics": _topic_rows(db, user, s), "method": {
        "summary": ("Each answer adds weighted evidence: recent answers and harder questions count more, a repeated "
                    "question counts half, a skipped question counts as half a wrong answer. The score is the share of "
                    "weighted evidence that is correct, with an approximate likely range (80% interval). A trend is shown only "
                    "when the last 5 answers differ from the earlier ones by at least 20 points and Fisher's exact test "
                    "says the difference is unlikely to be chance."),
        "limits": ("The 5-question minimum is a product rule, not a guarantee of reliability. The range is approximate: "
                   "because answers are weighted it is not a calibrated statistical interval, and it has only been "
                   "checked on simulated students, not real ones."),
        "min_evidence": s.mastery_min_evidence, "half_life_days": s.mastery_half_life_days,
        "thresholds": {"strong": f"lower end of the range >= {t.strong_lower:.0%}",
                       "proficient": f"score >= {t.proficient_score:.0%}", "developing": f"score >= {t.developing_score:.0%}",
                       "needs_improvement": f"score < {t.developing_score:.0%}",
                       "insufficient_evidence": f"fewer than {s.mastery_min_evidence} different questions answered"}}}


@router.get("/mastery/history")
def mastery_history(topic_key: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    snaps = db.scalars(select(TopicMasterySnapshot).where(TopicMasterySnapshot.student_id == user.id,
                                                          TopicMasterySnapshot.topic_key == topic_key)
                       .order_by(TopicMasterySnapshot.computed_at))
    pts = [{"at": x.computed_at, "score": x.score, "lower": x.lower, "upper": x.upper, "label": x.label,
            "answers": x.answers, "next_difficulty": x.next_difficulty} for x in snaps]
    return {"topic_key": topic_key, "points": pts, "enough_data": len(pts) >= MIN_TREND_POINTS}


@router.get("/weak-areas")
def weak_areas(user: User = Depends(require_student), db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    rows = _topic_rows(db, user, s)
    groups = defaultdict(list)
    for r in rows:
        groups[r["status"]].append(r)
    return {"weak": groups["weak"], "developing": groups["developing"],
            "insufficient_evidence": groups["insufficient_evidence"], "not_attempted": groups["not_attempted"],
            "ok": groups["ok"]}


@router.get("/question-status")
def question_status(user: User = Depends(require_student), db: Session = Depends(get_db)):
    """Three separate lists: skipped in a quiz, answered incorrectly, never attempted (in assigned quizzes)."""
    now = utcnow()
    skipped, incorrect = [], []
    seen_q: set[int] = set()
    for a, sess, z, q in db.execute(select(StudentAnswer, QuizSession, Quiz, Question)
                                    .join(QuizSession, QuizSession.id == StudentAnswer.session_id)
                                    .join(Quiz, Quiz.id == QuizSession.quiz_id)
                                    .join(Question, Question.id == StudentAnswer.question_id)
                                    .where(QuizSession.student_id == user.id, QuizSession.status == "submitted")
                                    .order_by(QuizSession.submitted_at.desc())):
        seen_q.add(q.id)
        if not att.feedback_visible(z, now):
            continue
        row = {"question_id": q.id, "text": q.text, "topic": q.topic_label, "quiz_title": z.title, "kind": z.kind,
               "session_id": sess.id, "at": sess.submitted_at}
        if a.selected_option_id is None:
            skipped.append(row)
        elif a.is_correct is False:
            incorrect.append(row)
    never = []
    ids = perm.assigned_quiz_ids(db, user)
    if ids:
        for z in db.scalars(select(Quiz).where(Quiz.id.in_(ids), Quiz.status == "published")):
            unseen = [i for i in z.items if i.question_id not in seen_q]
            if unseen:
                never.append({"quiz_id": z.id, "quiz_title": z.title, "questions": len(unseen),
                              "state": att.quiz_state(z, att.sessions_for(db, z.id, user.id), now)})
    return {"skipped": skipped[:100], "incorrect": incorrect[:100], "never_attempted": never}


@router.get("/trends")
def trends(user: User = Depends(require_student), db: Session = Depends(get_db)):
    now = utcnow()
    subs = _submitted(db, user)
    scores = [{"at": x.submitted_at, "percentage": x.result.final_percentage, "kind": z.kind, "title": z.title}
              for x, z in subs if x.result and att.feedback_visible(z, now)]
    weekly = defaultdict(lambda: {"practice": 0, "assessment": 0})
    first, later = [0, 0], [0, 0]
    seen: dict[int, int] = defaultdict(int)
    wrong_count: Counter = Counter()
    qtext = {}
    for x, z in subs:
        wk = (x.submitted_at - timedelta(days=x.submitted_at.weekday())).date().isoformat()
        for a in sorted(x.answers, key=lambda a: a.id):
            weekly[wk][z.kind] += 1
            if a.selected_option_id is None:
                seen[a.question_id] += 1
                continue
            bucket = first if seen[a.question_id] == 0 else later
            bucket[0] += bool(a.is_correct)
            bucket[1] += 1
            seen[a.question_id] += 1
            if a.is_correct is False:
                wrong_count[a.question_id] += 1
    repeated = [qid for qid, n in wrong_count.items() if n >= 2]
    for q in db.scalars(select(Question).where(Question.id.in_(repeated))) if repeated else []:
        qtext[q.id] = (q.text, q.topic_label)
    rev = list(db.scalars(select(RevisionSchedule).where(RevisionSchedule.student_id == user.id)))
    return {
        "scores": scores, "scores_enough": len(scores) >= MIN_TREND_POINTS,
        "weekly_activity": [{"week": k, **v} for k, v in sorted(weekly.items())],
        "first_vs_later": {"first_attempt": {"correct": first[0], "answered": first[1],
                                             "accuracy": round(first[0] / first[1], 3) if first[1] else None},
                           "later_attempts": {"correct": later[0], "answered": later[1],
                                              "accuracy": round(later[0] / later[1], 3) if later[1] else None},
                           "enough_data": first[1] >= 5 and later[1] >= 5},
        "repeated_mistakes": [{"question_id": q, "times_wrong": wrong_count[q], "text": qtext[q][0], "topic": qtext[q][1]}
                              for q in repeated if q in qtext][:20],
        "revision": {"scheduled": len(rev), "reviewed": sum(r.reviews > 0 for r in rev),
                     "retired": sum(r.status == "retired" for r in rev),
                     "due_now": sum(r.status == "active" and r.due_at <= now for r in rev)},
    }


@router.get("/recommendations")
def recommendations(user: User = Depends(require_student), db: Session = Depends(get_db)):
    rows = db.scalars(select(LearningRecommendation).where(LearningRecommendation.student_id == user.id,
                                                           LearningRecommendation.status == "open")
                      .order_by(LearningRecommendation.priority.desc()))
    return [{"id": r.id, "kind": r.kind, "topic_key": r.topic_key, "topic": r.topic_label, "subject": r.subject_label,
             "reason": r.reason, "payload": r.payload, "created_at": r.created_at,
             "algorithm_version": r.algorithm_version} for r in rows]


@router.post("/recommendations/{reco_id}/{action}", status_code=204)
def update_recommendation(reco_id: int, action: str, user: User = Depends(require_student), db: Session = Depends(get_db)):
    if action not in ("done", "dismiss"):
        raise HTTPException(404, "Unknown action.")
    r = db.get(LearningRecommendation, reco_id)
    if r is None or r.student_id != user.id:
        raise perm.not_found("Recommendation")
    r.status = "done" if action == "done" else "dismissed"
    db.commit()


@router.post("/recommendations/refresh")
def refresh_recommendations(user: User = Depends(require_student), db: Session = Depends(get_db),
                            s: Settings = Depends(get_settings_dep)):
    ad.rebuild_recommendations(db, user.id, s)
    db.commit()
    return recommendations(user, db)


def _revisable(db: Session, user: User, now):
    """Active revision items whose source quiz feedback is visible (never leak an unreleased key)."""
    items = list(db.scalars(select(RevisionSchedule).where(RevisionSchedule.student_id == user.id,
                                                           RevisionSchedule.status == "active")
                            .order_by(RevisionSchedule.due_at)))
    out = []
    for it in items:
        quizzes = db.scalars(select(Quiz).join(QuizQuestion, QuizQuestion.quiz_id == Quiz.id)
                             .join(QuizSession, QuizSession.quiz_id == Quiz.id)
                             .where(QuizQuestion.question_id == it.question_id, QuizSession.student_id == user.id))
        if any(att.feedback_visible(z, now) for z in quizzes):
            out.append(it)
    return out


@router.get("/revision")
def revision(user: User = Depends(require_student), db: Session = Depends(get_db)):
    now = utcnow()
    items = _revisable(db, user, now)
    qs = {q.id: q for q in db.scalars(select(Question).where(Question.id.in_([i.question_id for i in items])))} if items else {}
    rows = [{"question_id": i.question_id, "text": qs[i.question_id].text, "topic": qs[i.question_id].topic_label,
             "box": i.box, "due_at": i.due_at, "due": i.due_at <= now, "reviews": i.reviews} for i in items if i.question_id in qs]
    return {"due": [r for r in rows if r["due"]], "upcoming": [r for r in rows if not r["due"]],
            "method": "Leitner boxes: a missed question returns after 1 day, then 3, 7, 14 and 30 days after each correct answer."}


@router.post("/revision/start")
def start_revision(user: User = Depends(require_student), db: Session = Depends(get_db),
                   s: Settings = Depends(get_settings_dep)):
    """Builds a practice quiz from up to 10 due revision questions (no AI generation needed)."""
    now = utcnow()
    due = [i for i in _revisable(db, user, now) if i.due_at <= now][:10]
    if not due:
        raise HTTPException(409, "Nothing is due for revision right now.")
    random.shuffle(due)
    z = Quiz(owner_id=user.id, kind="practice", title="Spaced revision", status="published", graded=False,
             attempts_allowed=0, confidence_enabled=True, published_at=now)
    for k, it in enumerate(due):
        z.items.append(QuizQuestion(question_id=it.question_id, position=k, marks=1.0))
    z.max_marks = float(len(due))
    db.add(z)
    db.commit()
    sess = att.start_attempt(db, user, z, s)
    return {"quiz_id": z.id, "session_id": sess.id}


@router.get("/confidence")
def confidence(user: User = Depends(require_student), db: Session = Depends(get_db)):
    pairs = [(a.confidence, bool(a.is_correct)) for a, z in db.execute(
        select(StudentAnswer, Quiz).join(QuizSession, QuizSession.id == StudentAnswer.session_id)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(QuizSession.student_id == user.id, QuizSession.status == "submitted", Quiz.kind == "practice",
               StudentAnswer.confidence.is_not(None), StudentAnswer.selected_option_id.is_not(None)))]
    return conf_ml.calibration(pairs)


@router.get("/study-plan")
def study_plan(user: User = Depends(require_student), db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    """A week's plan from mastery, due assessments and the student's available hours. Each item says why."""
    now = utcnow()
    hours = (user.student_profile.weekly_study_hours if user.student_profile else None) or None
    rows = [r for r in _topic_rows(db, user, s) if r["status"] in ("weak", "developing", "insufficient_evidence")]
    soon = {}
    ids = perm.assigned_quiz_ids(db, user)
    if ids:
        for z in db.scalars(select(Quiz).where(Quiz.id.in_(ids), Quiz.status == "published", Quiz.due_at.is_not(None))):
            if now <= z.due_at <= now + timedelta(days=7) and att.quiz_state(z, att.sessions_for(db, z.id, user.id), now) in ("open", "in_progress"):
                for i in z.items:
                    soon.setdefault(i.question.topic_key, (z.title, z.due_at))
    weight = {"weak": 3.0, "developing": 2.0, "insufficient_evidence": 1.0}
    items = []
    for r in rows:
        w = weight[r["status"]] + (1.5 if r["topic_key"] in soon else 0)
        why = [r["status_reason"]]
        if r["topic_key"] in soon:
            title, due = soon[r["topic_key"]]
            why.append(f"'{title}' is due {due.date().isoformat()}.")
        items.append({**{k: r[k] for k in ("topic_key", "topic", "subject", "topic_id", "status", "next_difficulty")},
                      "weight": w, "why": " ".join(why)})
    for k, (title, due) in soon.items():
        if not any(i["topic_key"] == k for i in items):
            q = db.scalar(select(Question).where(Question.topic_key == k).limit(1))
            if q:
                items.append({"topic_key": k, "topic": q.topic_label, "subject": q.subject_label, "topic_id": q.topic_id,
                              "status": "upcoming_assessment", "next_difficulty": "mixed", "weight": 1.5,
                              "why": f"'{title}' is due {due.date().isoformat()}."})
    items.sort(key=lambda i: -i["weight"])
    items = items[:6]
    total_w = sum(i["weight"] for i in items) or 1
    for i in items:
        i["hours"] = round(hours * i["weight"] / total_w, 1) if hours else None
    return {"weekly_hours": hours, "items": items,
            "note": None if hours else "Add your weekly study hours in Profile to split time between topics."}
