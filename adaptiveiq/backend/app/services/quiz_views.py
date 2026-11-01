"""Converts database rows to API schemas. Answer keys only appear in owner views (QuestionFull)."""
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (Course, GenerationRun, ModelVersion, Question, Quiz, QuizQuestion, StudentAnswer, Subject)
from app.models.base import utcnow
from app.schemas.quizzes import OptionFull, QuestionFull, QuizDetail, QuizItemOut, QuizOut, RunStatus
from app.services.grading import weight_used
from app.services.validation_service import REASONS


def question_full(db: Session, q: Question) -> QuestionFull:
    mv = db.get(ModelVersion, q.model_version_id) if q.model_version_id else None
    used = db.scalar(select(func.count()).select_from(QuizQuestion).where(QuizQuestion.question_id == q.id)) or 0
    answered = db.scalar(select(func.count()).select_from(StudentAnswer).where(StudentAnswer.question_id == q.id)) or 0
    return QuestionFull(
        id=q.id, text=q.text, explanation=q.explanation, difficulty=q.difficulty, subject_label=q.subject_label,
        unit_label=q.unit_label, topic_label=q.topic_label, topic_id=q.topic_id, objective_id=q.objective_id,
        course_id=q.course_id, review_status=q.review_status, source_type=q.source_type, source_excerpt=q.source_excerpt,
        validation=q.validation or {},
        model=f"{mv.base_model} ({mv.variant}{', ' + mv.quantization if mv.quantization else ''})" if mv else None,
        options=[OptionFull(id=o.id, label=o.label, text=o.text, is_correct=o.is_correct) for o in q.options],
        created_at=q.created_at, updated_at=q.updated_at, used_in_quizzes=used, answered_count=answered,
        locked=answered > 0)


def quiz_out(db: Session, z: Quiz) -> QuizOut:
    course = db.get(Course, z.course_id) if z.course_id else None
    subject = db.get(Subject, z.subject_id) if z.subject_id else None
    statuses = Counter(i.question.review_status for i in z.items)
    topics = list(dict.fromkeys(i.question.topic_label for i in z.items))
    return QuizOut(
        id=z.id, kind=z.kind, title=z.title, instructions=z.instructions, status=z.status, course_id=z.course_id,
        course_title=course.title if course else None, subject_id=z.subject_id,
        subject_name=subject.name if subject else (z.items[0].question.subject_label if z.items else None),
        topics=topics, graded=z.graded, max_marks=z.max_marks, question_count=len(z.items),
        attempts_allowed=z.attempts_allowed, opens_at=z.opens_at, due_at=z.due_at, closes_at=z.closes_at,
        time_limit_min=z.time_limit_min, shuffle_questions=z.shuffle_questions, shuffle_options=z.shuffle_options,
        feedback_release=z.feedback_release, feedback_released=z.feedback_released, late_policy=z.late_policy,
        late_penalty_pct=z.late_penalty_pct, contribution_pct=z.contribution_pct,
        confidence_enabled=z.confidence_enabled, target_duration_min=z.target_duration_min, created_at=z.created_at,
        published_at=z.published_at, generation_run_id=z.generation_run_id, review_counts=dict(statuses))


def quiz_detail(db: Session, z: Quiz) -> QuizDetail:
    base = quiz_out(db, z).model_dump()
    subject = db.get(Subject, z.subject_id) if z.subject_id else None
    return QuizDetail(**base, items=[QuizItemOut(item_id=i.id, position=i.position, marks=i.marks,
                                                 question=question_full(db, i.question)) for i in z.items],
                      weight_cap_pct=subject.quiz_weight_cap_pct if subject else None,
                      weight_used_elsewhere_pct=weight_used(db, subject.id, z.id) if subject else None)


def run_status(db: Session, run: GenerationRun, queue_position: int = 0) -> RunStatus:
    end = run.finished_at or utcnow()
    rejected = run.rejected or {}
    return RunStatus(run_id=run.id, status=run.status, stage=run.stage, ready=run.ready, total=run.total,
                     attempts=run.attempts, rejected=rejected, rejected_reasons={k: REASONS.get(k, k) for k in rejected},
                     error=run.error, quiz_id=(run.params or {}).get("quiz_id"), queue_position=queue_position,
                     elapsed_s=round((end - run.started_at).total_seconds(), 1) if run.started_at else 0.0,
                     avg_question_s=run.avg_question_s, grounded_on=run.grounded_on,
                     difficulty_note=(run.params or {}).get("difficulty_note"))


def queue_position(db: Session, run: GenerationRun) -> int:
    if run.status != "queued":
        return 0
    return db.scalar(select(func.count()).select_from(GenerationRun).where(
        GenerationRun.status.in_(["queued", "running"]), GenerationRun.id < run.id)) or 0
