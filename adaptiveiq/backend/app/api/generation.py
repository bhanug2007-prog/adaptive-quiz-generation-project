"""Starting and following AI generation runs (lecturer drafts, student practice, single-question regenerate)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import (current_user, get_db, get_settings_dep, require_student, verified_lecturer,
                           verified_student)
from app.models import GenerationRun, LearningObjective, Quiz, QuizQuestion, Topic, User
from app.schemas.quizzes import DraftGenerateRequest, PracticeGenerateRequest, RunStatus
from app.services import adaptive_service
from app.services import permissions as perm
from app.services.quiz_views import queue_position, run_status

router = APIRouter(prefix="/api", tags=["generation"])


def practice_topic_key(subject: str, topic: str) -> str:
    return f"p:{subject.strip().lower()}|{topic.strip().lower()}"[:300]


def _guard_capacity(db: Session, user: User, s: Settings):
    active = db.scalar(select(func.count()).select_from(GenerationRun).where(
        GenerationRun.requested_by == user.id, GenerationRun.status.in_(["queued", "running"])))
    if active:
        raise HTTPException(429, "You already have a generation running. Wait for it to finish or cancel it.")
    total = db.scalar(select(func.count()).select_from(GenerationRun).where(GenerationRun.status.in_(["queued", "running"])))
    if total >= s.max_queued_generations:
        raise HTTPException(503, "The question generator is busy. Please try again in a few minutes.")


def _model_ready(request: Request):
    state, detail = request.app.state.model.health()
    if state != "ok":
        raise HTTPException(503, detail or "The AI model is not available.")


def _start(request: Request, db: Session, run: GenerationRun) -> RunStatus:
    db.commit()
    request.app.state.generation.enqueue(run.id)
    return run_status(db, run, queue_position(db, run))


@router.post("/lecturer/generate", response_model=RunStatus, status_code=202)
def generate_draft(body: DraftGenerateRequest, request: Request, user: User = Depends(verified_lecturer),
                   db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    course = perm.own_course(db, user, body.course_id)
    subject = perm.own_subject(db, user, body.subject_id)
    topic = perm.own_topic(db, user, body.topic_id)
    if subject.course_id != course.id or topic.unit.subject_id != subject.id:
        raise HTTPException(422, "The topic does not belong to that subject and course.")
    objectives = []
    for oid in body.objective_ids:
        o = db.get(LearningObjective, oid)
        if o is None or o.topic_id != topic.id:
            raise HTTPException(422, "A learning objective does not belong to this topic.")
        objectives.append(o.text)
    _guard_capacity(db, user, s)
    _model_ready(request)
    quiz = Quiz(owner_id=user.id, kind="assessment", course_id=course.id, subject_id=subject.id, title=body.title.strip(),
                status="generating", graded=True, target_duration_min=body.target_duration_min)
    db.add(quiz)
    db.flush()
    run = GenerationRun(requested_by=user.id, purpose="lecturer_draft", total=body.question_count, params={
        "quiz_id": quiz.id, "purpose": "lecturer_draft", "course_id": course.id, "subject": subject.name,
        "unit": topic.unit.name, "topic": topic.name, "topic_id": topic.id, "topic_key": f"t:{topic.id}",
        "objective_id": body.objective_ids[0] if len(body.objective_ids) == 1 else None, "objectives": objectives,
        "difficulty": body.difficulty, "distribution": body.distribution.model_dump() if body.distribution else None,
        "reference_text": body.reference_text, "marks_each": body.marks_each})
    db.add(run)
    db.flush()
    quiz.generation_run_id = run.id
    return _start(request, db, run)


@router.post("/student/practice/generate", response_model=RunStatus, status_code=202)
def generate_practice(body: PracticeGenerateRequest, request: Request, user: User = Depends(verified_student),
                      db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    subject, topic, unit, topic_id = body.subject, body.topic, body.unit, None
    if body.topic_id is not None:
        t = db.get(Topic, body.topic_id)
        if t is None or t.unit.subject.course_id not in perm.enrolled_course_ids(db, user):
            raise HTTPException(404, "Topic not found in your courses.")
        subject, topic, unit, topic_id = t.unit.subject.name, t.name, t.unit.name, t.id
    key = f"t:{topic_id}" if topic_id else practice_topic_key(subject, topic)
    difficulty, note = body.difficulty, None
    if difficulty == "adaptive":
        difficulty, note = adaptive_service.recommended_difficulty(db, user.id, key)
    _guard_capacity(db, user, s)
    _model_ready(request)
    quiz = Quiz(owner_id=user.id, kind="practice", title=f"Practice: {topic}", status="generating", graded=False,
                attempts_allowed=0, time_limit_min=body.time_limit_min, confidence_enabled=body.confidence_enabled,
                feedback_release="immediate")
    db.add(quiz)
    db.flush()
    run = GenerationRun(requested_by=user.id, purpose="practice", total=body.question_count, params={
        "quiz_id": quiz.id, "purpose": "practice", "subject": subject, "unit": unit, "topic": topic,
        "topic_id": topic_id, "topic_key": key, "difficulty": difficulty, "requested_difficulty": body.difficulty,
        "difficulty_note": note, "reference_text": body.reference_text, "marks_each": 1.0})
    db.add(run)
    db.flush()
    quiz.generation_run_id = run.id
    return _start(request, db, run)


@router.post("/lecturer/questions/{question_id}/regenerate", response_model=RunStatus, status_code=202)
def regenerate_question(question_id: int, request: Request, quiz_id: int, user: User = Depends(verified_lecturer),
                        db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    q = perm.own_question(db, user, question_id)
    quiz = perm.own_quiz(db, user, quiz_id)
    if quiz.status != "draft":
        raise HTTPException(409, "Only questions in a draft quiz can be regenerated.")
    if not db.scalar(select(QuizQuestion.id).where(QuizQuestion.quiz_id == quiz.id, QuizQuestion.question_id == q.id)):
        raise HTTPException(404, "That question is not in this quiz.")
    _guard_capacity(db, user, s)
    _model_ready(request)
    src = db.get(GenerationRun, q.generation_run_id) if q.generation_run_id else None
    ref = (src.params or {}).get("reference_text") if src else None
    run = GenerationRun(requested_by=user.id, purpose="regenerate", total=1, params={
        "quiz_id": quiz.id, "purpose": "regenerate", "replace_question_id": q.id, "course_id": q.course_id,
        "subject": q.subject_label, "unit": q.unit_label, "topic": q.topic_label, "topic_id": q.topic_id,
        "topic_key": q.topic_key, "objective_id": q.objective_id, "difficulty": q.difficulty,
        "reference_text": ref, "objectives": (src.params or {}).get("objectives", []) if src else []})
    db.add(run)
    return _start(request, db, run)


@router.get("/generation/{run_id}", response_model=RunStatus)
def get_run(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(GenerationRun, run_id)
    if run is None or run.requested_by != user.id:
        raise perm.not_found("Generation")
    return run_status(db, run, queue_position(db, run))


@router.post("/generation/{run_id}/cancel", response_model=RunStatus)
def cancel_run(run_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(GenerationRun, run_id)
    if run is None or run.requested_by != user.id:
        raise perm.not_found("Generation")
    if run.status in ("queued", "running"):
        request.app.state.generation.cancel(run.id)
    return run_status(db, run, queue_position(db, run))


@router.get("/generation", response_model=list[RunStatus])
def my_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    runs = db.scalars(select(GenerationRun).where(GenerationRun.requested_by == user.id)
                      .order_by(GenerationRun.id.desc()).limit(20))
    return [run_status(db, r, queue_position(db, r)) for r in runs]


@router.get("/student/practice/recommended-difficulty")
def practice_difficulty(subject: str, topic: str, topic_id: int | None = None, user: User = Depends(require_student),
                        db: Session = Depends(get_db)):
    key = f"t:{topic_id}" if topic_id else practice_topic_key(subject, topic)
    d, why = adaptive_service.recommended_difficulty(db, user.id, key)
    return {"difficulty": d, "reason": why}
