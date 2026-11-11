"""Starting and following AI generation runs (lecturer drafts, student practice, single-question regenerate)."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import current_user, get_db, get_settings_dep, require_student, verified_lecturer, verified_student
from app.models import GenerationRun, LearningObjective, Quiz, QuizQuestion, User
from app.schemas.quizzes import DraftGenerateRequest, PracticeGenerateRequest, RunStatus
from app.services import adaptive_service, permissions as perm
from app.services.document_service import DocumentError, select_chunks
from app.services.practice_service import guard_generation_capacity, practice_topic_key, start_practice_generation
from app.services.quiz_views import queue_position, run_status

router = APIRouter(prefix="/api", tags=["generation"])


def _scale_distribution(dist: dict | None, target: int) -> dict | None:
    if not dist:
        return None
    total = sum(int(dist.get(k, 0)) for k in ("easy", "medium", "hard"))
    if total == target or total <= 0:
        return dist
    raw = {k: int(dist.get(k, 0)) * target / total for k in ("easy", "medium", "hard")}
    scaled = {k: int(v) for k, v in raw.items()}
    rem = target - sum(scaled.values())
    for k in sorted(raw, key=lambda x: -(raw[x] - scaled[x])):
        if rem <= 0:
            break
        scaled[k] += 1
        rem -= 1
    return scaled


def _guard_capacity(db: Session, user: User, s: Settings):
    guard_generation_capacity(db, user, s)


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

    effective_count = body.question_count
    dist_dict = body.distribution.model_dump() if body.distribution else None
    doc_params: dict = {"source_mode": body.source_mode}
    if body.source_mode == "document":
        doc = request.app.state.documents.get(body.document_id, user.id)
        if doc is None:
            raise HTTPException(404, "Uploaded document was not found or expired. Upload the file again.")
        try:
            sel = select_chunks(
                doc, body.question_count,
                topic=(body.focus_topic or topic.name),
                subject=subject.name,
                objectives=objectives,
                section_filter=body.document_section,
                difficulty=body.difficulty,
                min_words=s.min_document_words,
                min_words_per_q=s.min_words_per_document_question,
            )
        except DocumentError as exc:
            raise HTTPException(exc.status_code, exc.message) from exc
        effective_count = sel.effective_count
        if dist_dict and effective_count != body.question_count:
            dist_dict = _scale_distribution(dist_dict, effective_count)
        doc_params.update({
            "document_name": doc.document_name,
            "file_type": doc.file_type,
            "document_section": body.document_section,
            "focus_topic": body.focus_topic,
            "document_chunks": [c.to_param_dict() for c in sel.chunks],
            "requested_count": sel.requested_count,
            "supported_count": sel.supported_count,
            "insufficient_content_note": sel.insufficient_content_note,
        })

    _guard_capacity(db, user, s)
    _model_ready(request)
    if body.source_mode == "document":
        request.app.state.documents.pop(body.document_id, user.id)

    quiz = Quiz(owner_id=user.id, kind="assessment", course_id=course.id, subject_id=subject.id, title=body.title.strip(),
                status="generating", graded=True, target_duration_min=body.target_duration_min)
    db.add(quiz)
    db.flush()
    run = GenerationRun(requested_by=user.id, purpose="lecturer_draft", total=effective_count, params={
        "quiz_id": quiz.id, "purpose": "lecturer_draft", "course_id": course.id, "subject": subject.name,
        "unit": topic.unit.name, "topic": topic.name, "topic_id": topic.id, "topic_key": f"t:{topic.id}",
        "objective_id": body.objective_ids[0] if len(body.objective_ids) == 1 else None, "objectives": objectives,
        "difficulty": body.difficulty, "distribution": dist_dict,
        "reference_text": body.reference_text, "marks_each": body.marks_each, **doc_params})
    db.add(run)
    db.flush()
    quiz.generation_run_id = run.id
    return _start(request, db, run)


@router.post("/student/practice/generate", response_model=RunStatus, status_code=202)
def generate_practice(body: PracticeGenerateRequest, request: Request, user: User = Depends(verified_student),
                      db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    started = start_practice_generation(
        db,
        user,
        s,
        body,
        model_service=request.app.state.model,
        generation_service=request.app.state.generation,
        document_store=request.app.state.documents,
        enforce_unarchived_course=False,
        allow_offline_handoff=False,
    )
    return started["run_status"]


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
    src_p = (src.params or {}) if src else {}
    ref = src_p.get("reference_text")
    extra: dict = {"source_mode": src_p.get("source_mode", "topic")}
    if src_p.get("source_mode") == "document" or q.source_type == "document":
        chunks = list(src_p.get("document_chunks") or [])
        if len(chunks) > 1:
            chunks = chunks[1:] + chunks[:1]
        elif not chunks and q.source_excerpt:
            src_meta = (q.validation or {}).get("source") or {}
            chunks = [{"text": q.source_excerpt, **src_meta}]
        extra.update({
            "source_mode": "document",
            "document_name": src_p.get("document_name") or ((q.validation or {}).get("source") or {}).get("document_name"),
            "document_section": src_p.get("document_section"),
            "document_chunks": chunks,
        })
    run = GenerationRun(requested_by=user.id, purpose="regenerate", total=1, params={
        "quiz_id": quiz.id, "purpose": "regenerate", "replace_question_id": q.id, "course_id": q.course_id,
        "subject": q.subject_label, "unit": q.unit_label, "topic": q.topic_label, "topic_id": q.topic_id,
        "topic_key": q.topic_key, "objective_id": q.objective_id, "difficulty": q.difficulty,
        "reference_text": ref, "objectives": src_p.get("objectives", []), **extra})
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
