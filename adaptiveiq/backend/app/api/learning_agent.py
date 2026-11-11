"""Student-only endpoints for Stage 1 (read-only preview) and Stage 2 (persistent HITL) Personalized Learning Agent."""
from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_student
from app.models import User
from app.schemas.learning_agent import (
    LearningPlanApproveRequest,
    LearningPlanCreateRequest,
    LearningPlanDecisionRequest,
    LearningPlanOut,
    LearningPlanPreviewOut,
    LearningPlanRefreshRequest,
)
from app.services.learning_agent_service import (
    apply_plan_decision,
    approve_plan_action,
    create_learning_plan,
    get_current_learning_plan,
    get_learning_plan_by_id,
    preview_learning_plan,
    refresh_learning_plan,
)

# Router-level require_student guarantees auth/role enforcement (401/403) before path/body parsing
router = APIRouter(
    prefix="/api/student",
    tags=["learning agent"],
    dependencies=[Depends(require_student)],
)


@router.get("/learning-plan/preview", response_model=LearningPlanPreviewOut)
def get_learning_plan_preview(
    weekly_hours: int | None = Query(
        default=None,
        ge=0,
        le=80,
        description="Optional non-persisted weekly study hours override for previewing time allocation.",
    ),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Return a deterministic, read-only Stage 1 personalized study-plan preview for the signed-in student."""
    return preview_learning_plan(db, user, s, weekly_hours=weekly_hours)


@router.post("/learning-plan", response_model=LearningPlanOut, status_code=201)
def create_persistent_learning_plan(
    request: Request,
    body: LearningPlanCreateRequest = Body(default_factory=LearningPlanCreateRequest),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Generate and persist a student-owned Stage 2 learning plan paused cleanly before action execution."""
    return create_learning_plan(
        db,
        user,
        s,
        request.app.state.learning_checkpointer,
        body,
    )


@router.get("/learning-plan/current", response_model=LearningPlanOut | None)
def read_current_learning_plan(
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Return the signed-in student's current active persistent learning plan (or latest historical plan), if any."""
    return get_current_learning_plan(db, user, s)


@router.get("/learning-plan/{plan_id}", response_model=LearningPlanOut)
def read_learning_plan(
    plan_id: int,
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Return one persistent learning plan owned by the signed-in student with reconciled completion status."""
    return get_learning_plan_by_id(db, user, plan_id, s)


@router.post("/learning-plan/{plan_id}/approve", response_model=LearningPlanOut)
def approve_learning_plan_action(
    plan_id: int,
    request: Request,
    body: LearningPlanApproveRequest = Body(default_factory=LearningPlanApproveRequest),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Explicit student HITL approval resuming the checkpointed LangGraph thread to start an allowlisted action."""
    return approve_plan_action(
        db,
        user,
        plan_id,
        body.activity_id,
        body.idempotency_key,
        s,
        request.app.state.learning_checkpointer,
        model_service=request.app.state.model,
        generation_service=request.app.state.generation,
        document_store=request.app.state.documents,
    )


@router.post("/learning-plan/{plan_id}/dismiss", response_model=LearningPlanOut)
def dismiss_learning_plan_item_or_plan(
    plan_id: int,
    request: Request,
    body: LearningPlanDecisionRequest = Body(default_factory=LearningPlanDecisionRequest),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Dismiss a single recommendation or the whole learning plan without modifying mastery or quiz marks."""
    return apply_plan_decision(
        db,
        user,
        plan_id,
        "dismiss",
        body,
        s,
        request.app.state.learning_checkpointer,
    )


@router.post("/learning-plan/{plan_id}/postpone", response_model=LearningPlanOut)
def postpone_learning_plan_item(
    plan_id: int,
    request: Request,
    body: LearningPlanDecisionRequest = Body(default_factory=LearningPlanDecisionRequest),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Postpone a recommended activity without marking it completed or altering mastery/quiz scores."""
    return apply_plan_decision(
        db,
        user,
        plan_id,
        "postpone",
        body,
        s,
        request.app.state.learning_checkpointer,
    )


@router.post("/learning-plan/{plan_id}/refresh", response_model=LearningPlanOut)
def refresh_persistent_learning_plan(
    plan_id: int,
    request: Request,
    body: LearningPlanRefreshRequest = Body(default_factory=LearningPlanRefreshRequest),
    user: User = Depends(require_student),
    db: Session = Depends(get_db),
    s: Settings = Depends(get_settings_dep),
):
    """Re-evaluate mastery, prerequisites, revisions, and quiz availability cleanly without auto-executing."""
    return refresh_learning_plan(
        db,
        user,
        plan_id,
        body,
        s,
        request.app.state.learning_checkpointer,
    )
