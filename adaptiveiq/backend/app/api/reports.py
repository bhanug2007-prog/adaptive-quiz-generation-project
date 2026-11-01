"""CSV exports. Each checks ownership first; cells that look like spreadsheet formulas are neutralised."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_lecturer
from app.models import QuizSession, User
from app.services import class_analytics as ca
from app.services import permissions as perm

router = APIRouter(prefix="/api/lecturer/reports", tags=["reports"])


def _safe(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return "" if v is None else v


def _csv(name: str, header: list[str], rows: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(x) for x in r])
    data = "﻿" + buf.getvalue()                      # BOM so Excel opens UTF-8 names correctly
    safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{safe_name}"'})


def _roll(u: User):
    return u.student_profile.roll_number if u.student_profile else None


@router.get("/quizzes/{quiz_id}/results.csv")
def quiz_results(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    roster = ca.course_students(db, z.course_id, include_removed=True) if z.course_id else []
    rows = []
    for st in roster:
        sessions = list(db.scalars(select(QuizSession).where(QuizSession.quiz_id == z.id, QuizSession.student_id == st.id)
                                   .order_by(QuizSession.attempt_no)))
        if not sessions:
            rows.append([st.full_name, st.email, _roll(st), "", "not started", "", "", "", "", "", "", "", "", ""])
        for x in sessions:
            r = x.result
            rows.append([st.full_name, st.email, _roll(st), x.attempt_no, x.status,
                         x.submitted_at.isoformat() if x.submitted_at else "", "yes" if x.is_late else "no",
                         r.raw_score if r else "", r.max_score if r else "", r.percentage if r else "",
                         r.late_penalty_pct if r else "", r.final_percentage if r else "",
                         r.contribution_earned if r and r.contribution_earned is not None else "",
                         z.contribution_pct if z.graded else ""])
    return _csv(f"{z.title}-results.csv",
                ["student", "email", "roll_number", "attempt", "status", "submitted_at", "late", "raw_score",
                 "max_score", "percentage", "late_penalty_pct", "final_percentage", "contribution_earned",
                 "contribution_pct_of_subject"], rows)


@router.get("/quizzes/{quiz_id}/completion.csv")
def quiz_completion(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    rows = []
    for st in ca.course_students(db, z.course_id) if z.course_id else []:
        sessions = list(db.scalars(select(QuizSession).where(QuizSession.quiz_id == z.id, QuizSession.student_id == st.id)))
        sub = [x for x in sessions if x.status == "submitted"]
        state = "submitted" if sub else ("in progress" if sessions else "not started")
        rows.append([st.full_name, st.email, _roll(st), state, len(sub),
                     max(x.submitted_at for x in sub).isoformat() if sub else "", "yes" if any(x.is_late for x in sub) else "no"])
    return _csv(f"{z.title}-completion.csv", ["student", "email", "roll_number", "state", "submitted_attempts",
                                              "last_submitted_at", "late"], rows)


@router.get("/quizzes/{quiz_id}/questions.csv")
def quiz_questions(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    rows = [[r["position"], r["text"], r["topic"], r["difficulty"], r["answers"], r["pct_correct"], r["pct_incorrect"],
             r["pct_skipped"], r["avg_time_s"], r["discrimination"], r["empirical_difficulty"],
             "; ".join(f["text"] for f in r["flags"])] for r in ca.question_analytics(db, [z])]
    return _csv(f"{z.title}-questions.csv", ["position", "question", "topic", "difficulty_label", "answers", "pct_correct",
                                             "pct_incorrect", "pct_skipped", "avg_time_s", "discrimination",
                                             "observed_difficulty", "review_flags"], rows)


@router.get("/courses/{course_id}/marks.csv")
def course_marks(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """Student-wise marks: one row per student, one column per published quiz (latest attempt, final %)."""
    c = perm.own_course(db, user, course_id)
    quizzes = ca.course_quizzes(db, c.id)
    latest = {(x.quiz_id, x.student_id): x for x in ca.best_sessions(db, [z.id for z in quizzes])}
    rows = []
    for st in ca.course_students(db, c.id):
        cells, contrib = [], 0.0
        for z in quizzes:
            x = latest.get((z.id, st.id))
            cells.append(x.result.final_percentage if x and x.result else "")
            if x and x.result and x.result.contribution_earned:
                contrib += x.result.contribution_earned
        rows.append([st.full_name, st.email, _roll(st), *cells, round(contrib, 3)])
    return _csv(f"{c.code}-marks.csv", ["student", "email", "roll_number", *[f"{z.title} (%)" for z in quizzes],
                                        "total_contribution_points"], rows)


@router.get("/courses/{course_id}/topics.csv")
def course_topics(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                  s: Settings = Depends(get_settings_dep)):
    c = perm.own_course(db, user, course_id)
    hm = ca.heatmap(db, c, s)
    topics = hm["topics"]
    rows = []
    for st in hm["students"]:
        for t, cell in zip(topics, st["cells"]):
            rows.append([st["name"], st["roll_number"], t["subject"], t["unit"], t["topic"], cell["label"],
                         cell.get("score"), cell.get("lower"), cell.get("upper"), cell["answers"],
                         cell.get("unique_questions", 0), cell["evidence_level"]])
    return _csv(f"{c.code}-topics.csv", ["student", "roll_number", "subject", "unit", "topic", "mastery_label",
                                         "mastery_score", "range_low", "range_high", "answers", "unique_questions",
                                         "evidence"], rows)

