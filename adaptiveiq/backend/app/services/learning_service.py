"""Read-only analytics, revision-eligibility, and permission-scoped evidence loaders
shared by student analytics and the Stage 1 Personalized Learning Agent.

All helpers here are strictly read-only: no rows, snapshots, schedules, or marks
are created or mutated.
"""
from collections import defaultdict
from datetime import datetime, timedelta
import random

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ml import difficulty, mastery, recommendations, weak_areas
from app.ml.mastery import LABEL_TEXT, explain
from app.models import (
    Course,
    CourseEnrollment,
    Question,
    Quiz,
    QuizQuestion,
    QuizSession,
    RevisionSchedule,
    StudentAnswer,
    Subject,
    Topic,
    TopicMasterySnapshot,
    Unit,
    User,
)
from app.models.base import utcnow
from app.services import adaptive_service as ad
from app.services import attempt_service as att
from app.services import permissions as perm


def _quiz_feedback_accessible(z: Quiz, now: datetime) -> bool:
    """True when answers/results from `z` are permitted to influence student insights or revision."""
    if z.kind == "practice":
        return z.status != "generating"
    if z.status not in ("published", "archived"):
        return False
    return att.feedback_visible(z, now)


def revisable_rows(db: Session, student_id: int, now: datetime | None = None) -> list[tuple[RevisionSchedule, Question]]:
    """Active spaced-revision (schedule, question) pairs whose source quiz feedback is visible to this student.

    Excludes rejected and quarantined questions and never leaks unreleased manual/after-due assessment items.
    """
    now = now or utcnow()
    rows = list(db.execute(
        select(RevisionSchedule, Question)
        .join(Question, Question.id == RevisionSchedule.question_id)
        .where(
            RevisionSchedule.student_id == student_id,
            RevisionSchedule.status == "active",
            Question.review_status != "rejected",
        )
        .order_by(RevisionSchedule.due_at)
    ))
    out: list[tuple[RevisionSchedule, Question]] = []
    for it, q in rows:
        if (q.validation or {}).get("quarantined"):
            continue
        quizzes = db.scalars(
            select(Quiz)
            .join(QuizQuestion, QuizQuestion.quiz_id == Quiz.id)
            .join(QuizSession, QuizSession.quiz_id == Quiz.id)
            .where(QuizQuestion.question_id == it.question_id, QuizSession.student_id == student_id)
        )
        if any((z.kind == "practice" or z.status in ("published", "archived")) and att.feedback_visible(z, now) for z in quizzes):
            out.append((it, q))
    return out


def revisable_items(db: Session, student_id: int, now: datetime | None = None) -> list[RevisionSchedule]:
    return [it for it, _ in revisable_rows(db, student_id, now)]


def start_spaced_revision(
    db: Session,
    user: User,
    s: Settings,
    *,
    topic_key: str | None = None,
    reuse_active: bool = True,
    now: datetime | None = None,
) -> dict:
    """Starts (or safely reuses) an active Spaced Revision quiz from eligible feedback-visible due questions."""
    now = now or utcnow()
    if reuse_active:
        active_rows = list(db.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.student_id == user.id,
                QuizSession.status == "in_progress",
                Quiz.owner_id == user.id,
                Quiz.kind == "practice",
                Quiz.title.like("Spaced revision%"),
            )
            .order_by(QuizSession.id.desc())
        ))
        for sess, z in active_rows:
            if att.expire_if_needed(db, sess, s, now):
                continue
            if topic_key is None or any(i.question.topic_key == topic_key for i in z.items):
                return {
                    "quiz_id": z.id,
                    "session_id": sess.id,
                    "reused_existing": True,
                    "question_count": len(sess.question_order or []),
                }

    rows = revisable_rows(db, user.id, now)
    due = [(it, q) for it, q in rows if it.due_at <= now]
    if topic_key is not None:
        if topic_key.startswith("t:"):
            try:
                tid = int(topic_key.split(":", 1)[1])
            except ValueError:
                raise HTTPException(404, "Topic not found.") from None
            topic_obj = db.get(Topic, tid)
            enrolled = set(perm.enrolled_course_ids(db, user))
            if (
                topic_obj is None
                or topic_obj.unit.subject.course.archived
                or topic_obj.unit.subject.course_id not in enrolled
            ):
                raise HTTPException(404, "Topic not found in your active courses.")
        due = [(it, q) for it, q in due if q.topic_key == topic_key]

    due = due[:10]
    if not due:
        msg = (
            "Nothing is due for revision right now."
            if topic_key is None
            else "Nothing is currently due or released for revision on this topic."
        )
        raise HTTPException(409, msg)

    random.shuffle(due)
    title = (
        f"Spaced revision: {due[0][1].topic_label}"[:200]
        if topic_key is not None
        else "Spaced revision"
    )
    z = Quiz(
        owner_id=user.id,
        kind="practice",
        title=title,
        status="published",
        graded=False,
        attempts_allowed=0,
        confidence_enabled=True,
        published_at=now,
    )
    for k, (it, _q) in enumerate(due):
        z.items.append(QuizQuestion(question_id=it.question_id, position=k, marks=1.0))
    z.max_marks = float(len(due))
    db.add(z)
    db.commit()
    sess = att.start_attempt(db, user, z, s)
    return {
        "quiz_id": z.id,
        "session_id": sess.id,
        "reused_existing": False,
        "question_count": len(due),
    }


def analytics_topic_rows(db: Session, user: User, s: Settings) -> list[dict]:
    """Preserves the exact existing `/api/student/weak-areas` and `/api/student/mastery` topic row format."""
    rows = []
    last_seen: dict[str, datetime] = {}
    for _a, sess, q in db.execute(
        select(StudentAnswer, QuizSession, Question)
        .join(QuizSession, QuizSession.id == StudentAnswer.session_id)
        .join(Question, Question.id == StudentAnswer.question_id)
        .where(QuizSession.student_id == user.id, QuizSession.status == "submitted")
    ):
        t = sess.submitted_at
        if q.topic_key not in last_seen or t > last_seen[q.topic_key]:
            last_seen[q.topic_key] = t
    for info in ad.topic_infos(db, user.id, s):
        e = info.estimate
        rows.append({
            "topic_key": info.topic_key,
            "subject": info.subject_label,
            "topic": info.topic_label,
            "topic_id": info.course_topic_id,
            "status": info.status.status,
            "status_reason": info.status.reason,
            "label": e.label if e else "not_attempted",
            "label_text": LABEL_TEXT[e.label] if e else "Not attempted",
            "score": e.score if e else None,
            "lower": e.lower if e else None,
            "upper": e.upper if e else None,
            "answers": e.answers if e else 0,
            "unique_questions": e.unique_questions if e else 0,
            "correct": e.correct if e else 0,
            "incorrect": e.incorrect if e else 0,
            "skipped": e.skipped if e else 0,
            "recent_accuracy": e.recent_accuracy if e else None,
            "historical_accuracy": e.historical_accuracy if e else None,
            "next_difficulty": info.next_difficulty,
            "explanation": explain(e) if e else "No answers on this topic yet.",
            "last_activity": last_seen.get(info.topic_key),
            **ad.topic_summary(e, s),
        })
    rank = {"weak": 0, "developing": 1, "insufficient_evidence": 2, "ok": 3, "not_attempted": 4}
    return sorted(rows, key=lambda r: (rank.get(r["status"], 9), r["score"] if r["score"] is not None else 2, r["topic"]))


def upcoming_assigned_quizzes(db: Session, user: User, now: datetime, horizon_days: int = 7) -> list[dict]:
    """Published, assigned assessments open for work and due within `horizon_days` (never exposes questions/keys)."""
    ids = perm.assigned_quiz_ids(db, user)
    if not ids:
        return []
    out: list[dict] = []
    for z in db.scalars(
        select(Quiz).where(
            Quiz.id.in_(ids),
            Quiz.kind == "assessment",
            Quiz.status == "published",
            Quiz.due_at.is_not(None),
        )
    ):
        if not z.items:
            continue
        if any(i.question.review_status != "approved" or (i.question.validation or {}).get("quarantined") for i in z.items):
            continue
        if not (now <= z.due_at <= now + timedelta(days=horizon_days)):
            continue
        state_z = att.quiz_state(z, att.sessions_for(db, z.id, user.id), now)
        if state_z not in ("open", "in_progress", "late_open"):
            continue
        topic_keys = list(dict.fromkeys(i.question.topic_key for i in z.items))
        topic_labels = list(dict.fromkeys(i.question.topic_label for i in z.items))
        subject_label = z.items[0].question.subject_label
        out.append({
            "quiz_id": z.id,
            "title": z.title,
            "course_id": z.course_id,
            "due_at": z.due_at.isoformat(),
            "state": state_z,
            "question_count": len(z.items),
            "subject_label": subject_label,
            "topic_keys": topic_keys,
            "topic_labels": topic_labels,
        })
    out.sort(key=lambda item: item["due_at"])
    return out


def _visible_observations(db: Session, user: User, now: datetime) -> tuple[dict[str, list], dict[str, tuple[str, str, int | None, int | None]]]:
    """Submitted answers scoped to this student and strictly visible feedback (never leaks unreleased assessments)."""
    q = (
        select(StudentAnswer, QuizSession, Quiz, Question)
        .join(QuizSession, QuizSession.id == StudentAnswer.session_id)
        .join(Quiz, Quiz.id == QuizSession.quiz_id)
        .join(Question, Question.id == StudentAnswer.question_id)
        .where(QuizSession.student_id == user.id, QuizSession.status == "submitted")
        .order_by(QuizSession.submitted_at, StudentAnswer.id)
    )
    seen: set[int] = set()
    obs: dict[str, list] = defaultdict(list)
    labels: dict[str, tuple[str, str, int | None, int | None]] = {}
    for ans, sess, quiz, qn in db.execute(q):
        if quiz.kind == "practice" and quiz.owner_id != user.id:
            continue
        if not _quiz_feedback_accessible(quiz, now):
            continue
        correct = None if (ans.is_correct is None and ans.selected_option_id is None) else bool(ans.is_correct)
        obs[qn.topic_key].append(mastery.Observation(
            question_id=qn.id,
            correct=correct,
            difficulty=qn.difficulty,
            at=ans.answered_at or sess.submitted_at,
            repeat=qn.id in seen,
            time_spent_s=ans.time_spent_s,
        ))
        seen.add(qn.id)
        labels[qn.topic_key] = (qn.subject_label, qn.topic_label, qn.topic_id, qn.course_id or quiz.course_id)
    return dict(obs), labels


def _visible_snapshots(db: Session, user: User, now: datetime) -> dict[str, TopicMasterySnapshot]:
    """Most recent snapshot per topic whose triggering session is visible to the student."""
    rows = db.execute(
        select(TopicMasterySnapshot, QuizSession, Quiz)
        .outerjoin(QuizSession, QuizSession.id == TopicMasterySnapshot.trigger_session_id)
        .outerjoin(Quiz, Quiz.id == QuizSession.quiz_id)
        .where(TopicMasterySnapshot.student_id == user.id)
        .order_by(TopicMasterySnapshot.id.desc())
    )
    out: dict[str, TopicMasterySnapshot] = {}
    for snap, _sess, quiz in rows:
        if snap.topic_key in out:
            continue
        if quiz is not None and not _quiz_feedback_accessible(quiz, now):
            continue
        out[snap.topic_key] = snap
    return out


def _eligible_question_inventory(
    db: Session,
    user: User,
    enrolled_ids: list[int],
    now: datetime,
) -> tuple[dict[str, int], set[str], dict[str, tuple[str, str, int | None, int | None]]]:
    """Counts questions cleanly available to this student (never draft/rejected/quarantined/unopened)."""
    counts: dict[str, int] = defaultdict(int)
    open_quiz_topics: set[str] = set()
    labels: dict[str, tuple[str, str, int | None, int | None]] = {}
    counted_qids: set[int] = set()

    # 1. Approved questions inside published assessments assigned to this student
    assigned_ids = perm.assigned_quiz_ids(db, user)
    if assigned_ids and enrolled_ids:
        for z in db.scalars(
            select(Quiz).where(
                Quiz.id.in_(assigned_ids),
                Quiz.kind == "assessment",
                Quiz.status == "published",
                Quiz.course_id.in_(enrolled_ids),
            )
        ):
            if not z.items:
                continue
            if any(i.question.review_status != "approved" or (i.question.validation or {}).get("quarantined") for i in z.items):
                continue
            state_z = att.quiz_state(z, att.sessions_for(db, z.id, user.id), now)
            if state_z in ("upcoming", "expired"):
                continue
            if state_z == "submitted" and not _quiz_feedback_accessible(z, now):
                continue
            for item in z.items:
                q = item.question
                labels.setdefault(q.topic_key, (q.subject_label, q.topic_label, q.topic_id, q.course_id))
                if state_z in ("open", "in_progress", "late_open"):
                    open_quiz_topics.add(q.topic_key)
                if q.id not in counted_qids:
                    counts[q.topic_key] += 1
                    counted_qids.add(q.id)

    # 2. Student's own personal practice questions (non-rejected, non-quarantined)
    personal_qs = db.scalars(
        select(Question).where(
            Question.owner_id == user.id,
            Question.review_status == "personal",
        )
    )
    for q in personal_qs:
        if (q.validation or {}).get("quarantined") or q.id in counted_qids:
            continue
        if q.course_id is not None and (not enrolled_ids or q.course_id not in enrolled_ids):
            continue
        labels.setdefault(q.topic_key, (q.subject_label, q.topic_label, q.topic_id, q.course_id))
        counts[q.topic_key] += 1
        counted_qids.add(q.id)

    return dict(counts), open_quiz_topics, labels


def load_student_evidence(db: Session, student_id: int, s: Settings, now: datetime | None = None) -> dict:
    """Loads permission-scoped, JSON-serializable student evidence for the LangGraph Personalized Learning Agent."""
    now = now or utcnow()
    user = db.get(User, student_id)
    if user is None or not user.is_active or user.role != "student":
        return {"authorized": False, "auth_error": "Student account is inactive or not authorized."}

    weekly_hours = user.student_profile.weekly_study_hours if user.student_profile else None

    # Active, non-archived enrolled courses only
    enrolled_courses_rows = list(db.scalars(
        select(Course)
        .join(CourseEnrollment, CourseEnrollment.course_id == Course.id)
        .where(
            CourseEnrollment.student_id == user.id,
            CourseEnrollment.status == "active",
            Course.archived.is_(False),
        )
        .order_by(Course.title)
    ))
    enrolled_courses = [{"id": c.id, "code": c.code, "title": c.title} for c in enrolled_courses_rows]
    enrolled_ids = [c.id for c in enrolled_courses_rows]
    enrolled_set = set(enrolled_ids)

    # Enrolled syllabus topics + prerequisites (within enrolled courses only)
    course_topic_map: dict[str, dict] = {}
    if enrolled_ids:
        t_rows = db.execute(
            select(Topic, Unit, Subject, Course)
            .join(Unit, Unit.id == Topic.unit_id)
            .join(Subject, Subject.id == Unit.subject_id)
            .join(Course, Course.id == Subject.course_id)
            .where(Course.id.in_(enrolled_ids))
            .order_by(Course.id, Subject.id, Unit.position, Topic.id)
        )
        for topic_row, _unit, subject_row, course_row in t_rows:
            k = f"t:{topic_row.id}"
            course_topic_map[k] = {
                "topic_key": k,
                "subject_label": subject_row.name,
                "topic_label": topic_row.name,
                "topic_id": topic_row.id,
                "course_id": course_row.id,
                "raw_prereq_key": f"t:{topic_row.prerequisite_topic_id}" if topic_row.prerequisite_topic_id else None,
            }
    for meta in course_topic_map.values():
        rk = meta.pop("raw_prereq_key")
        meta["prerequisite_key"] = rk if (rk and rk in course_topic_map) else None

    visible_obs, obs_labels = _visible_observations(db, user, now)
    visible_snaps = _visible_snapshots(db, user, now)
    revisable = revisable_rows(db, user.id, now)
    due_rev = [(it, q) for it, q in revisable if it.due_at <= now]
    upcoming_rev = [(it, q) for it, q in revisable if it.due_at > now]

    due_by_topic: dict[str, dict] = {}
    for it, q in due_rev:
        if q.topic_key.startswith("t:") and q.topic_key not in course_topic_map:
            continue
        entry = due_by_topic.get(q.topic_key)
        if entry is None:
            meta = course_topic_map.get(q.topic_key, {})
            entry = {
                "topic_key": q.topic_key,
                "subject_label": meta.get("subject_label") or q.subject_label,
                "topic_label": meta.get("topic_label") or q.topic_label,
                "topic_id": meta.get("topic_id") or q.topic_id,
                "course_id": meta.get("course_id") or q.course_id,
                "due_count": 0,
                "min_box": it.box,
                "oldest_due_at": it.due_at.isoformat(),
            }
            due_by_topic[q.topic_key] = entry
        entry["due_count"] += 1
        entry["min_box"] = min(entry["min_box"], it.box)

    eligible_q_counts, open_quiz_topics, inv_labels = _eligible_question_inventory(db, user, enrolled_ids, now)
    upcoming_quizzes = upcoming_assigned_quizzes(db, user, now)

    # Own practice keys from user's practice questions / sessions so Node 3 can enforce ownership
    own_practice_keys = {k for k in visible_obs if k.startswith("p:")} | {k for k in eligible_q_counts if k.startswith("p:")}

    all_keys = list(dict.fromkeys([
        *course_topic_map.keys(),
        *[k for k in visible_obs if k.startswith("p:") or k in course_topic_map],
        *[k for k in visible_snaps if k.startswith("p:") or k in course_topic_map],
        *[k for k in eligible_q_counts if k.startswith("p:") or k in course_topic_map],
        *due_by_topic.keys(),
        *open_quiz_topics,
    ]))

    topics: list[dict] = []
    for key in all_keys:
        if key.startswith("t:") and key not in course_topic_map:
            # Exclude topics from courses the student is no longer actively enrolled in
            continue
        c_meta = course_topic_map.get(key)
        snap = visible_snaps.get(key)
        obs_list = visible_obs.get(key, [])
        if c_meta:
            subj = c_meta["subject_label"]
            top = c_meta["topic_label"]
            tid = c_meta["topic_id"]
            cid = c_meta["course_id"]
            prereq_key = c_meta["prerequisite_key"]
        elif snap:
            subj = snap.subject_label
            top = snap.topic_label
            tid = snap.topic_id
            cid = obs_labels.get(key, inv_labels.get(key, (None, None, None, None)))[3]
            prereq_key = None
        else:
            subj, top, tid, cid = obs_labels.get(key) or inv_labels.get(key) or ("Practice topics", key, None, None)
            prereq_key = None

        if obs_list or snap:
            est = ad.estimate_topic(obs_list, s, now)
            st = weak_areas.classify(est)
            if snap and snap.next_difficulty:
                nd, diff_why = snap.next_difficulty, (snap.details or {}).get("difficulty_reason", "")
            else:
                nd, diff_why = difficulty.next_difficulty(est, None)
        else:
            est = None
            st = weak_areas.classify(None)
            nd = "mixed"
            diff_why = "No answers on this topic yet, so the quiz mixes easy, medium and hard questions."

        summary = ad.topic_summary(est, s)
        next_act, next_act_text = difficulty.next_action(est, s.mastery_min_evidence)
        due_cnt = due_by_topic.get(key, {}).get("due_count", 0)
        elig_cnt = eligible_q_counts.get(key, 0)
        has_open_quiz = key in open_quiz_topics
        evidence_sufficient = bool(est and est.unique_questions >= s.mastery_min_evidence)

        topics.append({
            "topic_key": key,
            "subject_label": subj,
            "topic_label": top,
            "topic_id": tid,
            "course_id": cid if cid in enrolled_set else None,
            "prerequisite_key": prereq_key,
            "status": st.status,
            "status_reason": st.reason,
            "priority": round(float(st.priority), 4),
            "label": est.label if est else "not_attempted",
            "label_text": LABEL_TEXT[est.label] if est else "Not attempted",
            "score": est.score if est else None,
            "score_pct": summary["score_100"] if evidence_sufficient else None,
            "lower": est.lower if est else None,
            "upper": est.upper if est else None,
            "answers": est.answers if est else 0,
            "unique_questions": est.unique_questions if est else 0,
            "correct": est.correct if est else 0,
            "incorrect": est.incorrect if est else 0,
            "skipped": est.skipped if est else 0,
            "recent_accuracy": est.recent_accuracy if est else None,
            "recent_n": est.recent_n if est else 0,
            "historical_accuracy": est.historical_accuracy if est else None,
            "trend": est.trend if est else "not_enough_data",
            "evidence_level": summary["evidence_level"],
            "evidence_sufficient": evidence_sufficient,
            "min_evidence": s.mastery_min_evidence,
            "next_difficulty": nd,
            "difficulty_reason": diff_why,
            "next_action": next_act,
            "next_action_text": next_act_text,
            "explanation": explain(est) if est else "No answers on this topic yet.",
            "due_revision_count": due_cnt,
            "eligible_question_count": elig_cnt,
            "has_open_quiz": has_open_quiz,
            "is_own_practice": key in own_practice_keys,
        })

    due_revisions = sorted(due_by_topic.values(), key=lambda r: (-r["due_count"], r["oldest_due_at"]))
    has_eligible_material = bool(
        due_revisions
        or upcoming_quizzes
        or any(
            t["answers"] > 0 or t["eligible_question_count"] > 0 or t["has_open_quiz"]
            for t in topics
        )
    )

    return {
        "authorized": True,
        "auth_error": None,
        "weekly_study_hours": weekly_hours,
        "enrolled_course_ids": enrolled_ids,
        "enrolled_courses": enrolled_courses,
        "topics": topics,
        "due_revisions": due_revisions,
        "upcoming_revisions_count": len(upcoming_rev),
        "upcoming_quizzes": upcoming_quizzes,
        "has_eligible_material": has_eligible_material,
        "evidence_summary": {
            "topic_count": len(topics),
            "enrolled_courses_count": len(enrolled_courses),
            "due_revision_total": sum(r["due_count"] for r in due_revisions),
            "upcoming_revision_total": len(upcoming_rev),
            "upcoming_quizzes_count": len(upcoming_quizzes),
            "sufficient_evidence_topics": sum(1 for t in topics if t["evidence_sufficient"]),
            "insufficient_evidence_topics": sum(1 for t in topics if t["status"] == "insufficient_evidence"),
            "min_evidence_threshold": s.mastery_min_evidence,
        },
    }
