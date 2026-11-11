"""The feedback learning loop, run inside the submission transaction.

After every submitted attempt:
 1-3. (attempt_service) validate, score, store question-level results
 4. collect the student's observations for every topic in the attempt
 5. recalculate mastery (app.ml.mastery) and store a new snapshot per topic
 6. classify weak areas (app.ml.weak_areas)
 7. rebuild recommendations (app.ml.recommendations); older open ones become "superseded"
 8. choose the next practice difficulty per topic (app.ml.difficulty) and store it on the snapshot
 9. update spaced revision (app.ml.spaced_revision) and record every algorithm version used
No model weights are retrained here: the loop updates per-student statistics and policy state only.
"""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ml import difficulty, mastery, recommendations, spaced_revision, weak_areas
from app.models import (Course, LearningRecommendation, Question, QuizSession, RevisionSchedule, StudentAnswer,
                        Subject, Topic, TopicMasterySnapshot, Unit)
from app.models.base import utcnow
from app.services import permissions as perm

ALGORITHM_VERSION = "+".join([mastery.MASTERY_VERSION, difficulty.POLICY_VERSION, weak_areas.WEAK_VERSION,
                              recommendations.RECO_VERSION, spaced_revision.REVISION_VERSION])


def observations(db: Session, student_id: int, topic_keys: list[str] | None = None) -> dict[str, list]:
    """All answers in submitted attempts, grouped by topic_key, oldest first, with repeat flags."""
    q = (select(StudentAnswer, QuizSession, Question)
         .join(QuizSession, QuizSession.id == StudentAnswer.session_id)
         .join(Question, Question.id == StudentAnswer.question_id)
         .where(QuizSession.student_id == student_id, QuizSession.status == "submitted"))
    if topic_keys:
        q = q.where(Question.topic_key.in_(topic_keys))
    rows = sorted(db.execute(q), key=lambda r: (r[1].submitted_at, r[0].id))
    seen: set[int] = set()
    out: dict[str, list] = defaultdict(list)
    for a, s, qn in rows:
        if a.is_correct is None and a.selected_option_id is None:
            correct = None                                  # skipped
        else:
            correct = bool(a.is_correct)
        out[qn.topic_key].append(mastery.Observation(
            question_id=qn.id, correct=correct, difficulty=qn.difficulty, at=a.answered_at or s.submitted_at,
            repeat=qn.id in seen, time_spent_s=a.time_spent_s))
        seen.add(qn.id)
    return out


def latest_snapshots(db: Session, student_id: int) -> dict[str, TopicMasterySnapshot]:
    sub = (select(TopicMasterySnapshot.topic_key, func.max(TopicMasterySnapshot.id).label("mid"))
           .where(TopicMasterySnapshot.student_id == student_id).group_by(TopicMasterySnapshot.topic_key).subquery())
    rows = db.scalars(select(TopicMasterySnapshot).join(sub, TopicMasterySnapshot.id == sub.c.mid))
    return {r.topic_key: r for r in rows}


def topic_labels(db: Session, student_id: int, keys: list[str]) -> dict[str, tuple[str, str, int | None]]:
    """topic_key -> (subject label, topic label, course topic id) from the newest question on that key."""
    out = {}
    for k in keys:
        q = db.scalar(select(Question).where(Question.topic_key == k).order_by(Question.id.desc()).limit(1))
        if q:
            out[k] = (q.subject_label, q.topic_label, q.topic_id)
    return out


def course_topic_rows(db: Session, student_id: int):
    """Every topic in the student's enrolled courses: (key, subject, topic, topic id, prerequisite key)."""
    ids = perm.enrolled_course_ids_for(db, student_id)
    if not ids:
        return []
    rows = db.execute(select(Topic, Subject).join(Unit, Unit.id == Topic.unit_id).join(Subject, Subject.id == Unit.subject_id)
                      .join(Course, Course.id == Subject.course_id).where(Course.id.in_(ids)))
    return [(f"t:{t.id}", s.name, t.name, t.id, f"t:{t.prerequisite_topic_id}" if t.prerequisite_topic_id else None)
            for t, s in rows]


def estimate_topic(obs, s: Settings, now: datetime) -> mastery.MasteryEstimate:
    return mastery.estimate(obs, now, half_life_days=s.mastery_half_life_days, min_evidence=s.mastery_min_evidence)


def update_after_submission(db: Session, session: QuizSession, s: Settings) -> list[TopicMasterySnapshot]:
    now = utcnow()
    student_id = session.student_id
    keys = sorted({q.topic_key for q in db.scalars(select(Question).where(Question.id.in_(session.question_order)))})
    obs = observations(db, student_id, keys)
    prev = latest_snapshots(db, student_id)
    labels = topic_labels(db, student_id, keys)
    snaps = []
    for k in keys:
        e = estimate_topic(obs.get(k, []), s, now)
        cur = prev[k].next_difficulty if k in prev else None
        nd, why = difficulty.next_difficulty(e, cur)
        st = weak_areas.classify(e)
        subj, top, tid = labels.get(k, ("", k, None))
        snap = TopicMasterySnapshot(
            student_id=student_id, topic_key=k, topic_id=tid, subject_label=subj, topic_label=top, score=e.score,
            lower=e.lower, upper=e.upper, evidence=e.evidence, answers=e.answers, unique_questions=e.unique_questions,
            label=e.label, next_difficulty=nd, algorithm_version=ALGORITHM_VERSION, trigger_session_id=session.id,
            details={**e.details, "evidence_level": e.evidence_level, "recent_accuracy": e.recent_accuracy,
                     "recent_n": e.recent_n, "historical_accuracy": e.historical_accuracy, "correct": e.correct,
                     "incorrect": e.incorrect, "skipped": e.skipped, "difficulty_reason": why,
                     "weak_status": st.status, "weak_reason": st.reason, "explanation": mastery.explain(e),
                     "previous_difficulty": cur})
        db.add(snap)
        snaps.append(snap)
    _update_revision(db, session, now)
    db.flush()
    rebuild_recommendations(db, student_id, s)
    return snaps


def _update_revision(db: Session, session: QuizSession, now: datetime):
    answers = {a.question_id: a for a in session.answers}
    for qid in session.question_order:
        a = answers.get(qid)
        correct = bool(a and a.is_correct)
        q = db.get(Question, qid)
        item = db.scalar(select(RevisionSchedule).where(RevisionSchedule.student_id == session.student_id,
                                                        RevisionSchedule.question_id == qid))
        if q is None or q.review_status == "rejected" or (q.validation or {}).get("quarantined"):
            if item is not None and item.status == "active":
                item.status = "retired"
            continue
        if item is None:
            if correct:
                continue
            box, due, status = spaced_revision.after_answer(None, False, now)
            db.add(RevisionSchedule(student_id=session.student_id, question_id=qid, topic_key=q.topic_key, box=box,
                                    due_at=due, last_correct=False, status=status))
        elif item.status == "active":
            box, due, status = spaced_revision.after_answer(item.box, correct, now)
            item.box, item.status, item.last_correct = box, status, correct
            item.reviews += 1
            if due:
                item.due_at = due


def due_revision_counts(db: Session, student_id: int, now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    rows = db.execute(
        select(RevisionSchedule.topic_key, Question.validation)
        .join(Question, Question.id == RevisionSchedule.question_id)
        .where(
            RevisionSchedule.student_id == student_id,
            RevisionSchedule.status == "active",
            RevisionSchedule.due_at <= now,
            Question.review_status != "rejected",
        )
    )
    counts: dict[str, int] = defaultdict(int)
    for k, val in rows:
        if not (val or {}).get("quarantined"):
            counts[k] += 1
    return dict(counts)


def topic_infos(db: Session, student_id: int, s: Settings) -> list[recommendations.TopicInfo]:
    """Current state of every topic the student has evidence on, plus unattempted course topics."""
    snaps = latest_snapshots(db, student_id)
    now = utcnow()
    obs = observations(db, student_id)
    infos: dict[str, recommendations.TopicInfo] = {}
    prereq: dict[str, str | None] = {}
    for key, subj, top, tid, pre in course_topic_rows(db, student_id):
        prereq[key] = pre
        infos[key] = recommendations.TopicInfo(key, subj, top, None, weak_areas.classify(None), "mixed", pre, tid)
    for key, snap in snaps.items():
        e = estimate_topic(obs.get(key, []), s, now)       # recomputed so recency decay is current
        infos[key] = recommendations.TopicInfo(key, snap.subject_label, snap.topic_label, e, weak_areas.classify(e),
                                               snap.next_difficulty, prereq.get(key), snap.topic_id)
    return list(infos.values())


def rebuild_recommendations(db: Session, student_id: int, s: Settings) -> list[LearningRecommendation]:
    infos = topic_infos(db, student_id, s)
    recos = recommendations.build(infos, due_revision_counts(db, student_id))
    for old in db.scalars(select(LearningRecommendation).where(LearningRecommendation.student_id == student_id,
                                                               LearningRecommendation.status == "open")):
        old.status = "superseded"
    out = []
    for r in recos:
        row = LearningRecommendation(student_id=student_id, kind=r.kind, topic_key=r.topic_key,
                                     subject_label=r.subject_label, topic_label=r.topic_label, reason=r.reason[:400],
                                     payload=r.payload, priority=r.priority, algorithm_version=ALGORITHM_VERSION)
        db.add(row)
        out.append(row)
    return out


def topic_summary(e: mastery.MasteryEstimate | None, s: Settings) -> dict:
    """What the dashboards show for one topic besides the score: evidence, trend and the next step."""
    level = e.evidence_level if e else "none"
    action, action_text = difficulty.next_action(e, s.mastery_min_evidence)
    t = e.trend if e else "not_enough_data"
    return {"score_100": mastery.pct100(e.score) if e else None, "evidence_level": level,
            "evidence_text": mastery.EVIDENCE_TEXT[level], "trend": t, "trend_text": mastery.TREND_TEXT[t],
            "trend_reason": mastery.trend_reason(e) if e else "No answers on this topic yet.",
            "next_action": action, "next_action_text": action_text}


def recommended_difficulty(db: Session, student_id: int, topic_key: str) -> tuple[str, str]:
    snap = latest_snapshots(db, student_id).get(topic_key)
    if snap is None:
        return "mixed", "No answers on this topic yet, so the quiz mixes easy, medium and hard questions."
    return snap.next_difficulty, (snap.details or {}).get("difficulty_reason", "")
