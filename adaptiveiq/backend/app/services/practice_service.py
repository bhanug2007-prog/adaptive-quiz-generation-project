"""Shared student practice-generation service used by both REST endpoints and the LangGraph agent."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import is_verified
from app.models import GenerationRun, Quiz, Topic, User
from app.schemas.quizzes import PracticeGenerateRequest, RunStatus
from app.services import adaptive_service
from app.services import permissions as perm
from app.services.document_service import DocumentError, select_chunks
from app.services.quiz_views import queue_position, run_status


def practice_topic_key(subject: str, topic: str) -> str:
    return f"p:{subject.strip().lower()}|{topic.strip().lower()}"[:300]


def guard_generation_capacity(db: Session, user: User, s: Settings) -> None:
    active = db.scalar(
        select(func.count())
        .select_from(GenerationRun)
        .where(GenerationRun.requested_by == user.id, GenerationRun.status.in_(["queued", "running"]))
    )
    if active:
        raise HTTPException(429, "You already have a generation running. Wait for it to finish or cancel it.")
    total = db.scalar(
        select(func.count())
        .select_from(GenerationRun)
        .where(GenerationRun.status.in_(["queued", "running"]))
    )
    if total >= s.max_queued_generations:
        raise HTTPException(503, "The question generator is busy. Please try again in a few minutes.")


def validated_practice_href(
    subject: str,
    topic: str,
    difficulty: str,
    *,
    topic_id: int | None = None,
    run_id: int | None = None,
) -> str:
    params: dict[str, str] = {}
    if run_id is not None:
        params["run_id"] = str(run_id)
    if subject:
        params["subject"] = subject
    if topic:
        params["topic"] = topic
    if topic_id is not None:
        params["topic_id"] = str(topic_id)
    if difficulty:
        params["difficulty"] = difficulty
    query = urlencode(params)
    return f"/student/practice?{query}" if query else "/student/practice"


def start_practice_generation(
    db: Session,
    user: User,
    s: Settings,
    body: PracticeGenerateRequest,
    *,
    model_service,
    generation_service,
    document_store=None,
    enforce_unarchived_course: bool = False,
    allow_offline_handoff: bool = False,
    on_before_commit=None,
) -> dict:
    """Validates permissions, checks model availability, creates a Quiz+GenerationRun, and enqueues generation.

    When `allow_offline_handoff=True` and all authorization/enrollment/capacity checks pass but the model
    server is offline/unavailable, returns a validated Practice Lab navigation handoff without creating a failed run.
    """
    if user.role != "student" or not user.is_active:
        raise HTTPException(403, "This page is for students.")
    if not is_verified(user, s):
        raise HTTPException(403, f"Verify your email address first. We sent a link to {user.email}.")

    subject, topic, unit, topic_id = body.subject, body.topic, body.unit, None
    if body.topic_id is not None:
        t = db.get(Topic, body.topic_id)
        if (
            t is None
            or (enforce_unarchived_course and t.unit.subject.course.archived)
            or t.unit.subject.course_id not in perm.enrolled_course_ids(db, user)
        ):
            raise HTTPException(404, "Topic not found in your courses.")
        subject, topic, unit, topic_id = t.unit.subject.name, t.name, t.unit.name, t.id

    effective_count = body.question_count
    doc_params: dict = {"source_mode": body.source_mode}
    doc = None
    if body.source_mode == "document":
        if document_store is None:
            raise HTTPException(404, "Uploaded document was not found or expired. Upload the file again.")
        doc = document_store.get(body.document_id, user.id)
        if doc is None:
            raise HTTPException(404, "Uploaded document was not found or expired. Upload the file again.")
        if not topic:
            topic = body.document_section or Path(doc.document_name).stem or "Study material"
        if not subject:
            subject = "Study material"
        try:
            sel = select_chunks(
                doc,
                body.question_count,
                topic=body.topic or body.document_section,
                subject=body.subject or None,
                section_filter=body.document_section,
                difficulty=body.difficulty,
                min_words=s.min_document_words,
                min_words_per_q=s.min_words_per_document_question,
            )
        except DocumentError as exc:
            raise HTTPException(exc.status_code, exc.message) from exc
        effective_count = sel.effective_count
        doc_params.update({
            "document_name": doc.document_name,
            "file_type": doc.file_type,
            "document_section": body.document_section,
            "document_chunks": [c.to_param_dict() for c in sel.chunks],
            "requested_count": sel.requested_count,
            "supported_count": sel.supported_count,
            "insufficient_content_note": sel.insufficient_content_note,
        })

    key = f"t:{topic_id}" if topic_id else practice_topic_key(subject, topic)
    difficulty, note = body.difficulty, None
    if difficulty == "adaptive":
        difficulty, note = adaptive_service.recommended_difficulty(db, user.id, key)

    guard_generation_capacity(db, user, s)

    state, detail = model_service.health()
    if state != "ok":
        if allow_offline_handoff:
            return {
                "handoff": True,
                "quiz": None,
                "run": None,
                "run_status": None,
                "destination_href": validated_practice_href(subject, topic, difficulty, topic_id=topic_id),
                "message": detail or "The AI model is offline. Opened Practice Lab with your verified topic prefilled.",
            }
        raise HTTPException(503, detail or "The AI model is not available.")

    if doc is not None and document_store is not None:
        document_store.pop(body.document_id, user.id)

    quiz = Quiz(
        owner_id=user.id,
        kind="practice",
        title=f"Practice: {topic}"[:200],
        status="generating",
        graded=False,
        attempts_allowed=0,
        time_limit_min=body.time_limit_min,
        confidence_enabled=body.confidence_enabled,
        feedback_release="immediate",
    )
    db.add(quiz)
    db.flush()
    run = GenerationRun(
        requested_by=user.id,
        purpose="practice",
        total=effective_count,
        params={
            "quiz_id": quiz.id,
            "purpose": "practice",
            "subject": subject,
            "unit": unit,
            "topic": topic,
            "topic_id": topic_id,
            "topic_key": key,
            "difficulty": difficulty,
            "requested_difficulty": body.difficulty,
            "difficulty_note": note,
            "reference_text": body.reference_text,
            "marks_each": 1.0,
            **doc_params,
        },
    )
    db.add(run)
    db.flush()
    quiz.generation_run_id = run.id
    if on_before_commit is not None:
        on_before_commit(quiz, run)
    db.commit()

    generation_service.enqueue(run.id)
    status_out: RunStatus = run_status(db, run, queue_position(db, run))
    return {
        "handoff": False,
        "quiz": quiz,
        "run": run,
        "run_status": status_out,
        "destination_href": validated_practice_href(subject, topic, difficulty, topic_id=topic_id, run_id=run.id),
        "message": f"Started {difficulty} practice generation for {topic}.",
    }
