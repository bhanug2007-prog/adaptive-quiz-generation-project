"""Lecturer dashboards: overview, class performance, heatmap, question analytics, students, insights, coverage."""
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_lecturer
from app.ml.mastery import LABEL_TEXT
from app.models import (Course, GenerationRun, ModelVersion, Question, QuestionReviewRecord, Quiz, QuizQuestion,
                        QuizSession, User)
from app.models.base import utcnow
from app.services import adaptive_service as ad
from app.services import attempt_service as att
from app.services import class_analytics as ca
from app.services import permissions as perm
from app.services.validation_service import REASONS

router = APIRouter(prefix="/api/lecturer", tags=["lecturer analytics"])


def _filters(quiz_id=None, subject_id=None, unit_id=None, topic_id=None, student_id=None, date_from=None, date_to=None):
    for d in (date_from, date_to):
        if d is not None and d.tzinfo is None:
            raise HTTPException(422, "Dates must include a time zone.")
    return ca.Filters(quiz_id, subject_id, unit_id, topic_id, student_id, date_from, date_to)


@router.get("/overview")
def overview(days: int = Query(default=30, ge=1, le=365), user: User = Depends(require_lecturer),
             db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    now = utcnow()
    since = now - timedelta(days=days)
    courses = list(db.scalars(select(Course).where(Course.lecturer_id == user.id, Course.archived.is_(False))))
    students, published, expected, done = set(), 0, 0, 0
    recent_pcts, activity, pending = [], [], 0
    gaps = []
    for c in courses:
        roster = ca.course_students(db, c.id)
        students |= {u.id for u in roster}
        quizzes = [z for z in ca.course_quizzes(db, c.id) if z.status == "published"]
        published += len(quizzes)
        sess = [x for x in ca.best_sessions(db, [z.id for z in quizzes]) if x.student_id in {u.id for u in roster}]
        pairs = {(x.quiz_id, x.student_id) for x in sess}
        for z in quizzes:
            opened = not z.opens_at or z.opens_at <= now
            if not opened:
                continue
            expected += len(roster)
            got = sum((z.id, u.id) in pairs for u in roster)
            done += got
            end = att.window_end(z)
            if not end or now <= end:
                pending += len(roster) - got
        for x in sess:
            if x.submitted_at >= since and x.result:
                recent_pcts.append(x.result.final_percentage)
        for x in sorted(sess, key=lambda x: x.submitted_at, reverse=True)[:10]:
            z = db.get(Quiz, x.quiz_id)
            st = db.get(User, x.student_id)
            activity.append({"at": x.submitted_at, "student": st.full_name, "quiz": z.title, "course": c.title,
                             "percentage": x.result.final_percentage if x.result else None})
        snaps = {u.id: ad.latest_snapshots(db, u.id) for u in roster}
        for t, unit, sub in ca.course_topics(db, c.id):
            vals = [snaps[u.id][f"t:{t.id}"].score for u in roster
                    if f"t:{t.id}" in snaps[u.id] and snaps[u.id][f"t:{t.id}"].label != "insufficient_evidence"]
            if len(vals) >= 3:
                gaps.append({"course": c.title, "course_id": c.id, "topic": t.name, "topic_id": t.id,
                             "mean_mastery": round(statistics.mean(vals), 3), "students_with_evidence": len(vals)})
    gaps.sort(key=lambda g: g["mean_mastery"])
    activity.sort(key=lambda a: a["at"], reverse=True)
    return {"period_days": days, "active_courses": len(courses), "published_quizzes": published,
            "enrolled_students": len(students),
            "completion_rate": round(done / expected, 3) if expected else None, "expected_submissions": expected,
            "recent_average": round(statistics.mean(recent_pcts), 1) if recent_pcts else None,
            "recent_submissions": len(recent_pcts), "pending_submissions": pending,
            "largest_gaps": gaps[:5], "recent_activity": activity[:10],
            "definitions": {"completion_rate": "Submitted / (enrolled students x opened published quizzes).",
                            "recent_average": f"Mean final % of latest attempts submitted in the last {days} days.",
                            "pending_submissions": "Students who have not submitted a quiz that is still open.",
                            "largest_gaps": "Topics with the lowest mean mastery among at least 3 students with enough evidence."}}


@router.get("/courses/{course_id}/analytics")
def course_analytics(course_id: int, quiz_id: int | None = None, subject_id: int | None = None,
                     unit_id: int | None = None, topic_id: int | None = None, student_id: int | None = None,
                     date_from: datetime | None = None, date_to: datetime | None = None,
                     user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                     s: Settings = Depends(get_settings_dep)):
    c = perm.own_course(db, user, course_id)
    return ca.class_performance(db, c, _filters(quiz_id, subject_id, unit_id, topic_id, student_id, date_from, date_to), s)


@router.get("/courses/{course_id}/heatmap")
def course_heatmap(course_id: int, subject_id: int | None = None, unit_id: int | None = None,
                   user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                   s: Settings = Depends(get_settings_dep)):
    c = perm.own_course(db, user, course_id)
    return ca.heatmap(db, c, s, _filters(subject_id=subject_id, unit_id=unit_id))


@router.get("/courses/{course_id}/heatmap/cell")
def heatmap_cell(course_id: int, student_id: int, topic_id: int, user: User = Depends(require_lecturer),
                 db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    c = perm.own_course(db, user, course_id)
    if not perm.is_enrolled(db, student_id, c.id):
        raise perm.not_found("Student")
    t = perm.own_topic(db, user, topic_id)
    if t.unit.subject.course_id != c.id:
        raise perm.not_found("Topic")
    return ca.cell_detail(db, c, db.get(User, student_id), t, s)


@router.get("/quizzes/{quiz_id}/question-analytics")
def quiz_question_analytics(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    return ca.question_analytics(db, [z])


@router.get("/courses/{course_id}/question-analytics")
def course_question_analytics(course_id: int, flagged_only: bool = False, user: User = Depends(require_lecturer),
                              db: Session = Depends(get_db)):
    c = perm.own_course(db, user, course_id)
    rows = ca.question_analytics(db, ca.course_quizzes(db, c.id))
    return [r for r in rows if r["flags"]] if flagged_only else rows


@router.get("/courses/{course_id}/insights")
def course_insights(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                    s: Settings = Depends(get_settings_dep)):
    c = perm.own_course(db, user, course_id)
    return ca.insights(db, c, s)


@router.get("/courses/{course_id}/coverage")
def objective_coverage(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """How many approved questions and published-quiz questions assess each learning objective."""
    c = perm.own_course(db, user, course_id)
    out = []
    for t, u, sub in ca.course_topics(db, c.id):
        for o in t.objectives:
            bank = db.scalars(select(Question).where(Question.objective_id == o.id, Question.review_status == "approved"))
            bank = list(bank)
            used = sum(1 for q in bank if db.scalar(select(QuizQuestion.id).join(Quiz, Quiz.id == QuizQuestion.quiz_id)
                                                    .where(QuizQuestion.question_id == q.id, Quiz.status == "published").limit(1)))
            out.append({"objective_id": o.id, "code": o.code, "objective": o.text, "topic": t.name, "unit": u.name,
                        "subject": sub.name, "approved_questions": len(bank), "in_published_quizzes": used,
                        "coverage": "not_assessed" if used == 0 else "light" if used < 3 else "covered"})
    untagged = db.scalar(select(Question.id).where(Question.course_id == c.id, Question.objective_id.is_(None),
                                                   Question.review_status == "approved").limit(1)) is not None
    return {"objectives": out, "has_untagged_questions": untagged}


@router.get("/students")
def students(course_id: int | None = None, q: str | None = Query(default=None, max_length=100),
             page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
             user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    cids = [course_id] if course_id else perm.lecturer_course_ids(db, user)
    if course_id:
        perm.own_course(db, user, course_id)
    seen, rows = {}, []
    for cid in cids:
        quizzes = [z.id for z in ca.course_quizzes(db, cid)]
        for st in ca.course_students(db, cid):
            if q and q.lower() not in (st.full_name + " " + st.email).lower():
                continue
            r = seen.setdefault(st.id, {"student_id": st.id, "name": st.full_name, "email": st.email,
                                        "roll_number": st.student_profile.roll_number if st.student_profile else None,
                                        "courses": [], "submissions": 0, "pcts": [], "last_activity": None})
            r["courses"].append(db.get(Course, cid).title)
            for x in ca.best_sessions(db, quizzes, ca.Filters(student_id=st.id)):
                r["submissions"] += 1
                if x.result:
                    r["pcts"].append(x.result.final_percentage)
                if r["last_activity"] is None or x.submitted_at > r["last_activity"]:
                    r["last_activity"] = x.submitted_at
    for r in seen.values():
        snaps = ad.latest_snapshots(db, r["student_id"])
        r["weak_topics"] = sum(1 for k, sn in snaps.items() if k.startswith("t:") and sn.label == "needs_improvement")
        r["average"] = round(statistics.mean(r["pcts"]), 1) if r["pcts"] else None
        del r["pcts"]
        rows.append(r)
    rows.sort(key=lambda r: r["name"])
    return {"total": len(rows), "page": page, "page_size": page_size,
            "items": rows[(page - 1) * page_size: page * page_size]}


@router.get("/students/{student_id}")
def student_profile(student_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                    s: Settings = Depends(get_settings_dep)):
    st = perm.lecturer_student(db, user, student_id)
    cids = [cid for cid in perm.lecturer_course_ids(db, user) if perm.is_enrolled(db, st.id, cid)
            or db.scalar(select(QuizSession.id).join(Quiz, Quiz.id == QuizSession.quiz_id)
                         .where(Quiz.course_id == cid, QuizSession.student_id == st.id).limit(1))]
    history, skipped, by_subject = [], [], defaultdict(list)
    wrong_count = defaultdict(int)
    qtext = {}
    for cid in cids:
        c = db.get(Course, cid)
        for z in ca.course_quizzes(db, cid):
            for x in db.scalars(select(QuizSession).where(QuizSession.quiz_id == z.id, QuizSession.student_id == st.id)
                                .order_by(QuizSession.attempt_no)):
                r = x.result
                history.append({"session_id": x.id, "course": c.title, "quiz": z.title, "attempt_no": x.attempt_no,
                                "status": x.status, "submitted_at": x.submitted_at, "is_late": x.is_late,
                                "percentage": r.final_percentage if r else None,
                                "correct": r.correct if r else None, "unanswered": r.unanswered if r else None})
                if r:
                    subj = z.items[0].question.subject_label if z.items else "—"
                    by_subject[subj].append(r.final_percentage)
                for a in x.answers if x.status == "submitted" else []:
                    q = db.get(Question, a.question_id)
                    qtext[q.id] = (q.text, q.topic_label)
                    if a.selected_option_id is None:
                        skipped.append({"question_id": q.id, "text": q.text, "quiz": z.title})
                    elif a.is_correct is False:
                        wrong_count[q.id] += 1
    keys = {f"t:{t.id}" for cid in cids for t, _, _ in ca.course_topics(db, cid)}
    topics = [r for r in _topic_rows_for(db, st, s) if r["topic_key"] in keys]
    hist_sorted = sorted([h for h in history if h["percentage"] is not None], key=lambda h: h["submitted_at"])
    change = None
    if len(hist_sorted) >= 3:
        first = statistics.mean(h["percentage"] for h in hist_sorted[: len(hist_sorted) // 2])
        last = statistics.mean(h["percentage"] for h in hist_sorted[len(hist_sorted) // 2:])
        change = {"earlier_average": round(first, 1), "later_average": round(last, 1),
                  "note": "Earlier half vs later half of submitted quizzes; different quizzes cover different content."}
    return {"student": {"id": st.id, "name": st.full_name, "email": st.email,
                        "roll_number": st.student_profile.roll_number if st.student_profile else None},
            "participation": {"submitted": len([h for h in history if h["status"] == "submitted"]),
                              "note": "A student with no submissions has insufficient evidence, not weak mastery."},
            "history": history,
            "subjects": [{"subject": k, "average": round(statistics.mean(v), 1), "quizzes": len(v)} for k, v in by_subject.items()],
            "topics": topics,
            "repeated_mistakes": [{"question_id": q, "text": qtext[q][0], "topic": qtext[q][1], "times_wrong": n}
                                  for q, n in wrong_count.items() if n >= 2],
            "skipped": skipped[:50], "change_over_time": change,
            "recommended_revision": [t for t in topics if t["status"] in ("weak", "developing")][:5]}


def _topic_rows_for(db: Session, st: User, s: Settings) -> list[dict]:
    rows = []
    for info in ad.topic_infos(db, st.id, s):
        e = info.estimate
        rows.append({"topic_key": info.topic_key, "topic": info.topic_label, "subject": info.subject_label,
                     "status": info.status.status, "status_reason": info.status.reason,
                     "label": e.label if e else "not_attempted",
                     "label_text": LABEL_TEXT[e.label] if e else "Not attempted",
                     "score": e.score if e else None, "lower": e.lower if e else None, "upper": e.upper if e else None,
                     "answers": e.answers if e else 0, "unique_questions": e.unique_questions if e else 0,
                     "correct": e.correct if e else 0, "incorrect": e.incorrect if e else 0,
                     "skipped": e.skipped if e else 0, **ad.topic_summary(e, s)})
    return rows



@router.get("/model-quality")
def model_quality(user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """How the question-generation model has performed for this lecturer, per model version.

    Reliability comes from generation runs (model calls, questions that passed the automatic checks,
    reasons for rejection). Human review comes from what the lecturer did with the questions
    (approved, rejected, edited). Answer correctness, topic relevance and difficulty match need a
    human judgement per question, so they are measured offline (backend/evaluation/), not here."""
    versions = {v.id: v for v in db.scalars(select(ModelVersion))}
    out: dict = {}

    def row(vid):
        if vid not in out:
            v = versions.get(vid)
            out[vid] = {"model_version_id": vid, "name": v.name if v else "Unknown model",
                        "variant": v.variant if v else None, "base_model": v.base_model if v else None,
                        "adapter": v.adapter if v else None, "quantization": v.quantization if v else None,
                        "runs": 0, "runs_failed": 0, "runs_partial": 0, "model_calls": 0, "passed_checks": 0,
                        "requested": 0, "rejected_by_check": defaultdict(int), "seconds_per_question": [],
                        "questions": 0, "approved": 0, "rejected": 0, "pending": 0, "edited": 0}
        return out[vid]

    for r in db.scalars(select(GenerationRun).where(GenerationRun.requested_by == user.id,
                                                    GenerationRun.purpose.in_(("lecturer_draft", "regenerate")))):
        x = row(r.model_version_id)
        x["runs"] += 1
        x["runs_failed"] += r.status == "failed"
        x["runs_partial"] += r.status == "partial"
        x["model_calls"] += r.attempts or 0
        x["passed_checks"] += r.ready or 0
        x["requested"] += r.total or 0
        for k, n in (r.rejected or {}).items():
            x["rejected_by_check"][k] += n
        if r.avg_question_s:
            x["seconds_per_question"].append(r.avg_question_s)
    edited = set(db.scalars(select(QuestionReviewRecord.question_id).where(
        QuestionReviewRecord.reviewer_id == user.id, QuestionReviewRecord.action == "edited")))
    for q in db.scalars(select(Question).where(Question.owner_id == user.id, Question.model_version_id.is_not(None),
                                               Question.review_status != "personal")):
        x = row(q.model_version_id)
        x["questions"] += 1
        x["approved"] += q.review_status == "approved"
        x["rejected"] += q.review_status == "rejected"
        x["pending"] += q.review_status == "draft"
        x["edited"] += q.id in edited

    def rate(a, b):
        return round(a / b, 4) if b else None

    result = []
    for x in out.values():
        reviewed = x["approved"] + x["rejected"]
        spq = x.pop("seconds_per_question")
        x["rejected_by_check"] = [{"reason": k, "text": REASONS.get(k, k), "count": n}
                                  for k, n in sorted(x["rejected_by_check"].items(), key=lambda kv: -kv[1])]
        x.update({"pass_rate": rate(x["passed_checks"], x["model_calls"]),
                  "retry_rate": rate(x["model_calls"] - x["passed_checks"], x["model_calls"]),
                  "run_failure_rate": rate(x["runs_failed"], x["runs"]),
                  "approval_rate": rate(x["approved"], reviewed), "rejection_rate": rate(x["rejected"], reviewed),
                  "edit_rate": rate(x["edited"], x["questions"]),
                  "avg_seconds_per_question": round(statistics.mean(spq), 1) if spq else None})
        result.append(x)
    return {"versions": sorted(result, key=lambda x: -x["questions"]),
            "note": "Rates use only this lecturer's generation runs and review decisions. Approval and rejection "
                    "rates count reviewed questions only; questions still waiting for review are shown as pending."}
