"""Course-level aggregations shared by the lecturer dashboards and CSV reports.

Only data from the lecturer's own courses is read. Mastery cells use each student's evidence on the
course's topics (assessments and any practice the student did on those course topics).
"""
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ml import mastery as mastery_ml
from app.ml import question_stats, weak_areas
from app.models import (AnswerOption, Course, CourseEnrollment, Question, Quiz, QuizQuestion, QuizSession, Subject,
                        Topic, Unit, User)
from app.models.base import utcnow
from app.services import adaptive_service as ad


@dataclass
class Filters:
    quiz_id: int | None = None
    subject_id: int | None = None
    unit_id: int | None = None
    topic_id: int | None = None
    student_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def course_students(db: Session, course_id: int, include_removed: bool = False) -> list[User]:
    q = select(User).join(CourseEnrollment, CourseEnrollment.student_id == User.id).where(CourseEnrollment.course_id == course_id)
    if not include_removed:
        q = q.where(CourseEnrollment.status == "active")
    return list(db.scalars(q.order_by(User.full_name)))


def course_topics(db: Session, course_id: int, f: Filters | None = None) -> list[tuple[Topic, Unit, Subject]]:
    q = (select(Topic, Unit, Subject).join(Unit, Unit.id == Topic.unit_id).join(Subject, Subject.id == Unit.subject_id)
         .where(Subject.course_id == course_id))
    if f and f.subject_id:
        q = q.where(Subject.id == f.subject_id)
    if f and f.unit_id:
        q = q.where(Unit.id == f.unit_id)
    if f and f.topic_id:
        q = q.where(Topic.id == f.topic_id)
    return list(db.execute(q.order_by(Subject.name, Unit.position, Topic.id)))


def course_quizzes(db: Session, course_id: int, f: Filters | None = None) -> list[Quiz]:
    q = select(Quiz).where(Quiz.course_id == course_id, Quiz.kind == "assessment", Quiz.status.in_(["published", "archived"]),
                           Quiz.published_at.is_not(None))
    if f and f.quiz_id:
        q = q.where(Quiz.id == f.quiz_id)
    if f and f.subject_id:
        q = q.where(Quiz.subject_id == f.subject_id)
    return list(db.scalars(q.order_by(Quiz.published_at)))


def best_sessions(db: Session, quiz_ids: list[int], f: Filters | None = None) -> list[QuizSession]:
    """Each student's latest submitted attempt per quiz (the attempt the grade normally uses is policy;
    latest is shown and labelled as such)."""
    if not quiz_ids:
        return []
    q = select(QuizSession).where(QuizSession.quiz_id.in_(quiz_ids), QuizSession.status == "submitted")
    if f and f.student_id:
        q = q.where(QuizSession.student_id == f.student_id)
    if f and f.date_from:
        q = q.where(QuizSession.submitted_at >= f.date_from)
    if f and f.date_to:
        q = q.where(QuizSession.submitted_at <= f.date_to)
    latest = {}
    for s in db.scalars(q.order_by(QuizSession.attempt_no)):
        latest[(s.quiz_id, s.student_id)] = s
    return list(latest.values())


def _topic_filter(f: Filters | None, topics: list[tuple[Topic, Unit, Subject]]) -> set[str] | None:
    if f and (f.topic_id or f.unit_id or f.subject_id):
        return {f"t:{t.id}" for t, _, _ in topics}
    return None


def class_performance(db: Session, course: Course, f: Filters, s: Settings) -> dict:
    students = course_students(db, course.id)
    student_ids = {u.id for u in students}
    quizzes = course_quizzes(db, course.id, f)
    topics = course_topics(db, course.id, f)
    allowed_keys = _topic_filter(f, topics)
    sessions = [x for x in best_sessions(db, [z.id for z in quizzes], f) if x.student_id in student_ids]
    pcts = [x.result.final_percentage for x in sessions if x.result]
    bins = [0] * 10
    for p in pcts:
        bins[min(9, int(p // 10))] += 1
    expected = len(students) * len([z for z in quizzes if z.status == "published"]) if not f.student_id else len(quizzes)
    done_pairs = {(x.quiz_id, x.student_id) for x in sessions}
    by_quiz = defaultdict(list)
    for x in sessions:
        if x.result:
            by_quiz[x.quiz_id].append(x.result.final_percentage)
    trend = [{"quiz_id": z.id, "title": z.title, "date": z.due_at or z.published_at, "submissions": len(by_quiz[z.id]),
              "average": round(statistics.mean(by_quiz[z.id]), 1) if by_quiz[z.id] else None} for z in quizzes]
    # question-level aggregates
    qstats = defaultdict(lambda: {"c": 0, "w": 0, "s": 0})
    diff = defaultdict(lambda: [0, 0])
    qmeta = {}
    for x in sessions:
        for a in x.answers:
            q = qmeta.get(a.question_id) or db.get(Question, a.question_id)
            qmeta[a.question_id] = q
            if allowed_keys is not None and q.topic_key not in allowed_keys:
                continue
            k = "s" if a.selected_option_id is None else ("c" if a.is_correct else "w")
            qstats[a.question_id][k] += 1
            if k != "s":
                diff[q.difficulty][0] += k == "c"
                diff[q.difficulty][1] += 1
    missed = []
    total_skips = total_ans = 0
    for qid, st in qstats.items():
        n = st["c"] + st["w"] + st["s"]
        total_skips += st["s"]
        total_ans += n
        if n >= 3:
            missed.append({"question_id": qid, "text": qmeta[qid].text, "topic": qmeta[qid].topic_label, "answers": n,
                           "pct_incorrect": round(st["w"] / n, 3), "pct_skipped": round(st["s"] / n, 3)})
    missed.sort(key=lambda m: -(m["pct_incorrect"] + m["pct_skipped"]))
    # mastery distribution per topic
    dist = []
    support = []
    snaps_by_student = {u.id: ad.latest_snapshots(db, u.id) for u in students}
    for t, u, sub in topics:
        c = Counter(snaps_by_student[st.id][f"t:{t.id}"].label if f"t:{t.id}" in snaps_by_student[st.id] else "not_attempted"
                    for st in students)
        dist.append({"topic_id": t.id, "topic": t.name, "unit": u.name, "subject": sub.name, "counts": dict(c)})
    for st in students:
        mine = [x for x in sessions if x.student_id == st.id]
        snaps = snaps_by_student[st.id]
        weak = [sn.topic_label for k, sn in snaps.items() if k.startswith("t:") and sn.label == "needs_improvement"
                and (allowed_keys is None or k in allowed_keys)]
        avg = statistics.mean([x.result.final_percentage for x in mine if x.result]) if mine else None
        if not mine:
            support.append({"student_id": st.id, "name": st.full_name, "reason": "No submissions yet (participation, not performance).",
                            "kind": "participation", "average": None, "weak_topics": []})
        elif len(weak) >= 2 or (avg is not None and avg < 50 and len(mine) >= 2):
            reason = []
            if weak:
                reason.append(f"Needs improvement in {', '.join(weak[:3])}" + (" and more" if len(weak) > 3 else ""))
            if avg is not None and avg < 50 and len(mine) >= 2:
                reason.append(f"average {avg:.0f}% over {len(mine)} quizzes")
            support.append({"student_id": st.id, "name": st.full_name, "reason": "; ".join(reason) + ".",
                            "kind": "performance", "average": round(avg, 1) if avg is not None else None, "weak_topics": weak})
    return {
        "students": len(students), "quizzes": len(quizzes), "submissions": len(sessions),
        "average": round(statistics.mean(pcts), 1) if pcts else None,
        "median": round(statistics.median(pcts), 1) if pcts else None,
        "distribution": [{"range": f"{i * 10}-{i * 10 + 9 if i < 9 else 100}", "count": n} for i, n in enumerate(bins)],
        "completion_rate": round(len(done_pairs) / expected, 3) if expected else None,
        "expected_submissions": expected,
        "trend": trend, "trend_enough": len([t for t in trend if t["average"] is not None]) >= 2,
        "commonly_missed": missed[:10], "skipped_rate": round(total_skips / total_ans, 3) if total_ans else None,
        "by_difficulty": [{"difficulty": d, "answered": diff[d][1],
                           "accuracy": round(diff[d][0] / diff[d][1], 3) if diff[d][1] else None}
                          for d in ("easy", "medium", "hard")],
        "mastery_distribution": dist, "needs_support": support,
        "note": "Scores use each student's latest submitted attempt per quiz.",
    }


def heatmap(db: Session, course: Course, s: Settings, f: Filters | None = None) -> dict:
    students = course_students(db, course.id)
    topics = course_topics(db, course.id, f)
    now = utcnow()
    rows = []
    for st in students:
        obs = ad.observations(db, st.id, [f"t:{t.id}" for t, _, _ in topics])
        cells = []
        for t, _, _ in topics:
            o = obs.get(f"t:{t.id}", [])
            if not o:
                cells.append({"topic_id": t.id, "label": "not_attempted", "score": None, "answers": 0, "evidence_level": "none"})
                continue
            e = mastery_ml.estimate(o, now, s.mastery_half_life_days, s.mastery_min_evidence)
            cells.append({"topic_id": t.id, "label": e.label, "score": e.score, "lower": e.lower, "upper": e.upper,
                          "answers": e.answers, "unique_questions": e.unique_questions, "evidence_level": e.evidence_level})
        rows.append({"student_id": st.id, "name": st.full_name,
                     "roll_number": st.student_profile.roll_number if st.student_profile else None, "cells": cells})
    return {"topics": [{"topic_id": t.id, "topic": t.name, "unit": u.name, "subject": sb.name} for t, u, sb in topics],
            "students": rows, "labels": mastery_ml.LABEL_TEXT}


def cell_detail(db: Session, course: Course, student: User, topic: Topic, s: Settings) -> dict:
    key = f"t:{topic.id}"
    obs = ad.observations(db, student.id, [key]).get(key, [])
    e = mastery_ml.estimate(obs, utcnow(), s.mastery_half_life_days, s.mastery_min_evidence) if obs else None
    attempts = []
    wrong_choices = Counter()
    for sess, z in db.execute(select(QuizSession, Quiz).join(Quiz, Quiz.id == QuizSession.quiz_id)
                              .where(QuizSession.student_id == student.id, QuizSession.status == "submitted")
                              .order_by(QuizSession.submitted_at)):
        mine = [a for a in sess.answers if db.get(Question, a.question_id).topic_key == key]
        if not mine:
            continue
        c = sum(bool(a.is_correct) for a in mine)
        sk = sum(a.selected_option_id is None for a in mine)
        visible_quiz = z.kind == "assessment" and z.course_id == course.id
        attempts.append({"session_id": sess.id, "quiz": z.title if visible_quiz else "Personal practice",
                         "kind": z.kind, "at": sess.submitted_at, "correct": c, "incorrect": len(mine) - c - sk,
                         "skipped": sk})
        for a in mine:
            if a.is_correct is False and a.selected_option_id and visible_quiz:
                opt = db.get(AnswerOption, a.selected_option_id)
                q = db.get(Question, a.question_id)
                wrong_choices[(q.id, q.text, opt.text)] += 1
    st = weak_areas.classify(e)
    intervention = {
        "weak": "Assign a short easy-to-medium practice set on this topic and review the most-missed concept in class.",
        "developing": "Encourage one more mixed practice quiz on this topic.",
        "insufficient_evidence": "Not enough answers to judge; include this topic in the next quiz.",
        "not_attempted": "The student has not answered any question on this topic yet.",
        "ok": "No intervention needed on current evidence."}[st.status]
    return {"student": {"id": student.id, "name": student.full_name}, "topic": {"id": topic.id, "name": topic.name},
            "estimate": None if e is None else {**e.__dict__, "label_text": mastery_ml.LABEL_TEXT[e.label],
                                                "explanation": mastery_ml.explain(e)},
            "status": st.status, "status_reason": st.reason, "attempts": attempts,
            "common_mistakes": [{"question_id": k[0], "question": k[1], "chosen": k[2], "times": n}
                                for k, n in wrong_choices.most_common(5)],
            "suggested_intervention": intervention}


def question_analytics(db: Session, quizzes: list[Quiz]) -> list[dict]:
    out = []
    for z in quizzes:
        sessions = [x for x in db.scalars(select(QuizSession).where(QuizSession.quiz_id == z.id,
                                                                   QuizSession.status == "submitted"))]
        totals = {x.id: x.result.raw_score if x.result else 0.0 for x in sessions}
        marks = {i.question_id: i.marks for i in z.items}
        for it in z.items:
            q = it.question
            c = w = sk = 0
            times, item, rest = [], [], []
            for x in sessions:
                a = next((a for a in x.answers if a.question_id == q.id), None)
                if a is None:
                    continue
                if a.selected_option_id is None:
                    sk += 1
                elif a.is_correct:
                    c += 1
                else:
                    w += 1
                if a.time_spent_s:
                    times.append(a.time_spent_s)
                got = 1 if a.is_correct else 0
                item.append(got)
                rest.append(totals[x.id] - (marks.get(q.id, 1.0) if got else 0))
            reused = db.scalar(select(QuizQuestion.id).where(QuizQuestion.question_id == q.id,
                                                             QuizQuestion.quiz_id != z.id).limit(1)) is not None
            rep = question_stats.question_report(q.difficulty, c, w, sk, times, item, rest)
            out.append({"quiz_id": z.id, "quiz_title": z.title, "question_id": q.id, "position": it.position + 1,
                        "text": q.text, "topic": q.topic_label, "difficulty": q.difficulty, "reused": reused,
                        "objective_id": q.objective_id, **rep})
    return out


def insights(db: Session, course: Course, s: Settings) -> list[dict]:
    """Descriptive observations, each with its supporting numbers. None of them claims a cause."""
    perf = class_performance(db, course, Filters(), s)
    out = []
    topic_acc = defaultdict(lambda: [0, 0, "", ""])
    for x in best_sessions(db, [z.id for z in course_quizzes(db, course.id)]):
        for a in x.answers:
            q = db.get(Question, a.question_id)
            if a.selected_option_id is None or q.topic_id is None:
                continue
            t = topic_acc[q.topic_id]
            t[0] += bool(a.is_correct)
            t[1] += 1
            t[2], t[3] = q.topic_label, q.unit_label or ""
    by_unit = defaultdict(list)
    for tid, (c, n, name, unit) in topic_acc.items():
        if n >= 10:
            by_unit[unit].append((c / n, name, n))
    for unit, items in by_unit.items():
        if len(items) < 2:
            continue
        mean = sum(a for a, _, _ in items) / len(items)
        low = min(items)
        if mean - low[0] >= 0.15:
            out.append({"kind": "low_topic", "severity": "warning",
                        "text": f"{low[1]} has lower accuracy ({low[0]:.0%} over {low[2]} answers) than the average of "
                                f"topics in {unit or 'this unit'} ({mean:.0%}).",
                        "metric": {"topic_accuracy": round(low[0], 3), "unit_average": round(mean, 3), "answers": low[2]},
                        "type": "descriptive"})
    for m in perf["commonly_missed"]:
        if m["answers"] >= 10 and m["pct_skipped"] >= 0.3:
            out.append({"kind": "high_skip", "severity": "info",
                        "text": f"{m['pct_skipped']:.0%} of students skipped the question \"{m['text'][:80]}\" ({m['answers']} answers).",
                        "metric": {"pct_skipped": m["pct_skipped"], "answers": m["answers"]}, "type": "descriptive"})
    for d in perf["mastery_distribution"]:
        c = d["counts"]
        judged = sum(v for k, v in c.items() if k not in ("not_attempted", "insufficient_evidence"))
        weak = c.get("needs_improvement", 0)
        if judged >= 5 and weak / judged >= 0.4:
            out.append({"kind": "revisit_topic", "severity": "warning",
                        "text": f"Consider revisiting {d['topic']} before the next assessment: {weak} of {judged} students "
                                f"with enough evidence are at 'needs improvement'.",
                        "metric": {"needs_improvement": weak, "judged": judged}, "type": "suggestion"})
    t = [x for x in perf["trend"] if x["average"] is not None]
    if len(t) >= 2 and abs(t[-1]["average"] - t[-2]["average"]) >= 10:
        word = "higher" if t[-1]["average"] > t[-2]["average"] else "lower"
        out.append({"kind": "trend", "severity": "info",
                    "text": f"The class average on '{t[-1]['title']}' ({t[-1]['average']:.0f}%) is {word} than on "
                            f"'{t[-2]['title']}' ({t[-2]['average']:.0f}%). Different quizzes cover different content, so "
                            f"this is a comparison, not proof of change.",
                    "metric": {"latest": t[-1]["average"], "previous": t[-2]["average"]}, "type": "descriptive"})
    return out
