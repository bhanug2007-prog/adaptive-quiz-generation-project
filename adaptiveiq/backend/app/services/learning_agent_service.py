"""Service facade for Stage 1 (read-only preview) and Stage 2 (persistent HITL) Personalized Learning Agent."""
from __future__ import annotations

from datetime import datetime, timedelta
import uuid

from fastapi import HTTPException
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.personalized_learning import (
    ALLOWED_ACTION_BY_KIND,
    STAGE2_GRAPH_VERSION,
    _recompute_plan_status_from_db,
    _resolve_plan_item_for_action,
    compile_learning_plan_graph,
    compile_persistent_learning_plan_graph,
)
from app.agents.recorder import Recorder
from app.core.config import Settings
from app.models import (
    Course,
    GenerationRun,
    LearningPlan,
    LearningPlanExecution,
    LearningPlanItem,
    Question,
    Quiz,
    QuizSession,
    StudentAnswer,
    User,
)
from app.models.base import utcnow
from app.schemas.learning_agent import (
    ExecutionResultOut,
    LearningPlanCreateRequest,
    LearningPlanDecisionRequest,
    LearningPlanOut,
    LearningPlanPreviewOut,
    LearningPlanRefreshRequest,
    LearningPlanStage2ItemOut,
    PendingApprovalOut,
    PlanProgressOut,
)
from app.services import permissions as perm

ACTIVE_PLAN_STATUSES = ("awaiting_approval", "in_progress", "proposed")
TERMINAL_PLAN_STATUSES = ("completed", "dismissed", "expired", "failed")


def preview_learning_plan(
    db: Session,
    user: User,
    settings: Settings,
    *,
    weekly_hours: int | None = None,
    now: datetime | None = None,
    max_items: int = 6,
) -> LearningPlanPreviewOut:
    """Runs the deterministic Stage 1 LangGraph workflow for `user` in strictly read-only mode."""
    if user.role != "student" or not user.is_active:
        raise HTTPException(403, "This page is for students.")

    graph = compile_learning_plan_graph()
    initial_state = {
        "student_id": user.id,
        "has_hours_override": weekly_hours is not None,
        "weekly_study_hours_override": weekly_hours,
        "max_items": max_items,
        "node_history": [],
        "routing_history": [],
    }
    config = {
        "configurable": {
            "db": db,
            "settings": settings,
            "now": now or utcnow(),
        }
    }
    final_state = graph.invoke(initial_state, config=config)
    if not final_state.get("authorized"):
        raise HTTPException(403, final_state.get("auth_error") or "Student authorization required.")
    return LearningPlanPreviewOut.model_validate(final_state["plan_preview"])


# ---------------- Stage 2: Persistent HITL Operations ----------------

def _require_active_student(user: User) -> None:
    if user.role != "student" or not user.is_active:
        raise HTTPException(403, "This page is for students.")


def _get_own_plan(db: Session, user: User, plan_id: int) -> LearningPlan:
    plan = db.get(LearningPlan, plan_id)
    if plan is None or plan.student_id != user.id:
        raise perm.not_found("Learning plan")
    return plan


def _has_pending_interrupt(graph, config: dict) -> bool:
    try:
        snap = graph.get_state(config)
    except Exception:
        return False
    if not snap or not getattr(snap, "tasks", None):
        return False
    return any(bool(getattr(t, "interrupts", None)) for t in snap.tasks)


def sync_plan_progress_from_db(db: Session, plan: LearningPlan, user: User, now: datetime) -> bool:
    """Reconciles real submitted QuizSession completion evidence onto active-epoch plan items.

    Never marks an item completed without an actual submitted QuizSession in the database.
    Commits immediately if changes were applied so no SQLite write lock stays open before graph calls.
    """
    changed = False
    if plan.expires_at and plan.expires_at <= now and plan.status in ("proposed", "awaiting_approval"):
        plan.status = "expired"
        changed = True

    active_items = [i for i in plan.items if i.revision_epoch == plan.generation_seq]
    for item in active_items:
        if item.status != "in_progress":
            continue
        ref = dict(item.execution_ref or {})
        action_type = ref.get("action_type") or ALLOWED_ACTION_BY_KIND.get(item.kind)
        submitted_sess: QuizSession | None = None

        session_id = ref.get("session_id")
        quiz_id = ref.get("quiz_id")
        run_id = ref.get("generation_run_id")

        if session_id:
            sess = db.get(QuizSession, int(session_id))
            if sess is not None and sess.student_id == user.id and sess.status == "submitted":
                submitted_sess = sess
        if submitted_sess is None and quiz_id:
            submitted_sess = db.scalar(
                select(QuizSession)
                .where(
                    QuizSession.quiz_id == int(quiz_id),
                    QuizSession.student_id == user.id,
                    QuizSession.status == "submitted",
                )
                .order_by(QuizSession.submitted_at.desc())
                .limit(1)
            )
        if submitted_sess is None and run_id:
            run = db.get(GenerationRun, int(run_id))
            q_id = (run.params or {}).get("quiz_id") if run else None
            if q_id:
                submitted_sess = db.scalar(
                    select(QuizSession)
                    .where(
                        QuizSession.quiz_id == int(q_id),
                        QuizSession.student_id == user.id,
                        QuizSession.status == "submitted",
                    )
                    .order_by(QuizSession.submitted_at.desc())
                    .limit(1)
                )
        if submitted_sess is None and action_type == "start_practice" and ref.get("execution_status") == "handoff":
            since = item.approved_at or item.created_at
            submitted_sess = db.scalar(
                select(QuizSession)
                .join(Quiz, Quiz.id == QuizSession.quiz_id)
                .join(StudentAnswer, StudentAnswer.session_id == QuizSession.id)
                .join(Question, Question.id == StudentAnswer.question_id)
                .where(
                    QuizSession.student_id == user.id,
                    QuizSession.status == "submitted",
                    Quiz.kind == "practice",
                    Question.topic_key == item.topic_key,
                    QuizSession.submitted_at >= since,
                )
                .order_by(QuizSession.submitted_at.desc())
                .limit(1)
            )

        if submitted_sess is not None:
            item.status = "completed"
            item.completed_at = submitted_sess.submitted_at or now
            ref["session_id"] = submitted_sess.id
            ref["quiz_id"] = submitted_sess.quiz_id
            item.execution_ref = ref
            changed = True

    if changed:
        plan.status = _recompute_plan_status_from_db(db, plan)
        db.commit()
        db.refresh(plan)
    return changed


def _serialize_item(item: LearningPlanItem, plan_status: str) -> LearningPlanStage2ItemOut:
    plan_closed = plan_status in ("dismissed", "expired", "failed")
    is_current_epoch = item.status != "superseded"
    approved_type = ALLOWED_ACTION_BY_KIND.get(item.kind) if is_current_epoch else None
    can_approve = bool(
        not plan_closed
        and is_current_epoch
        and item.status in ("pending", "postponed")
        and approved_type is not None
    )
    can_dismiss = bool(
        not plan_closed
        and is_current_epoch
        and item.status in ("pending", "postponed", "in_progress")
    )
    can_postpone = bool(
        not plan_closed
        and is_current_epoch
        and item.status == "pending"
    )
    exec_ref = None
    if item.execution_ref:
        exec_ref = ExecutionResultOut.model_validate(item.execution_ref)

    return LearningPlanStage2ItemOut(
        id=item.id,
        rank=item.rank,
        revision_epoch=item.revision_epoch,
        change_status=item.change_status if item.change_status in ("initial", "new", "updated", "unchanged") else "initial",
        is_refreshed_new=bool(item.is_refreshed_new),
        activity_id=item.activity_id,
        kind=item.kind,
        topic_key=item.topic_key,
        topic=item.topic_label,
        subject=item.subject_label,
        course_id=item.course_id,
        topic_id=item.topic_id,
        quiz_id=item.quiz_id,
        status=item.topic_status,
        mastery_label=item.mastery_label,
        mastery_score_pct=item.mastery_score_pct,
        evidence_sufficient=bool(item.evidence_sufficient),
        unique_questions=int(item.unique_questions or 0),
        min_evidence=int(item.min_evidence or 5),
        recommended_difficulty=item.recommended_difficulty,
        priority=float(item.priority or 0.0),
        estimated_minutes=int(item.estimated_minutes or 0),
        estimated_hours=item.estimated_hours,
        reason=item.reason,
        due_revision_count=int(item.due_revision_count or 0),
        prerequisite_of=list(item.prerequisite_of or []),
        blocked_by_prerequisite=item.blocked_by_prerequisite,
        next_action=item.proposed_action,
        item_status=item.status,
        approval_status=item.approval_status,
        approved_action_type=approved_type,
        can_approve=can_approve,
        can_dismiss=can_dismiss,
        can_postpone=can_postpone,
        postponed_until=item.postponed_until,
        decision_note=item.decision_note,
        execution_ref=exec_ref,
        completed_at=item.completed_at,
    )


def _serialize_plan(plan: LearningPlan, override_last_exec: dict | None = None) -> LearningPlanOut:
    current_raw = sorted(
        [i for i in plan.items if i.revision_epoch == plan.generation_seq],
        key=lambda x: (x.rank, x.id),
    )
    previous_raw = sorted(
        [i for i in plan.items if i.revision_epoch < plan.generation_seq],
        key=lambda x: (-x.revision_epoch, x.rank, x.id),
    )

    items = [_serialize_item(i, plan.status) for i in current_raw]
    prev_items = [_serialize_item(i, plan.status) for i in previous_raw]

    total = len(items)
    pending_c = sum(1 for i in items if i.item_status == "pending")
    in_prog_c = sum(1 for i in items if i.item_status in ("in_progress", "approved"))
    comp_c = sum(1 for i in items if i.item_status == "completed")
    dism_c = sum(1 for i in items if i.item_status == "dismissed")
    post_c = sum(1 for i in items if i.item_status == "postponed")
    active_denom = max(0, total - dism_c)
    pct = round(100 * comp_c / active_denom) if active_denom > 0 else (100 if comp_c > 0 else 0)

    actionable_ids = [i.activity_id for i in items if i.can_approve]
    awaiting = bool(plan.status in ("awaiting_approval", "in_progress") and actionable_ids)
    default_id = next((i.activity_id for i in items if i.item_status == "pending" and i.can_approve), None)
    if default_id is None and actionable_ids:
        default_id = actionable_ids[0]

    if awaiting:
        first_item = next((i for i in items if i.activity_id == default_id), items[0])
        prompt = f"Approve next step: {first_item.topic} ({first_item.next_action.label}) — or postpone, dismiss, or refresh."
    elif in_prog_c > 0:
        prompt = "An approved activity is in progress. Complete it and refresh your plan when ready."
    elif plan.status == "completed":
        prompt = "All active recommendations in this plan are completed. Refresh to compute next goals."
    elif plan.status == "dismissed":
        prompt = "This learning plan was dismissed. Create or refresh a plan whenever you want new suggestions."
    else:
        prompt = "No activities await approval right now. Refresh after joining a course or completing a quiz."

    exec_dict = override_last_exec if override_last_exec is not None else plan.last_execution_ref
    last_exec = ExecutionResultOut.model_validate(exec_dict) if exec_dict else None

    return LearningPlanOut(
        id=plan.id,
        graph_version=plan.graph_version,
        policy_versions=dict(plan.policy_versions or {}),
        status=plan.status,
        action_approval_status=plan.action_approval_status,
        selected_activity_id=plan.selected_activity_id,
        generation_seq=int(plan.generation_seq or 1),
        last_refreshed_at=plan.last_refreshed_at,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        scenario=plan.scenario,
        scenarios=list(plan.scenarios or []),
        routing_mode=plan.routing_mode,
        scope_course_ids=list(plan.scope_course_ids or []),
        summary=plan.summary,
        progress=PlanProgressOut(
            total_items=total,
            pending_items=pending_c,
            in_progress_items=in_prog_c,
            completed_items=comp_c,
            dismissed_items=dism_c,
            postponed_items=post_c,
            completion_pct=pct,
        ),
        pending_approval=PendingApprovalOut(
            awaiting_approval=awaiting,
            default_activity_id=default_id,
            actionable_activity_ids=actionable_ids,
            prompt=prompt,
        ),
        items=items,
        previous_items=prev_items,
        deferred_topics=list(plan.deferred_topics or []),
        proposed_next_actions=list(plan.proposed_next_actions or []),
        warnings=list(plan.warnings or []),
        last_execution=last_exec,
        graph_trace=plan.graph_trace or {"nodes_visited": [], "edges_taken": []},
    )


def _create_plan_items_for_epoch(
    db: Session,
    plan: LearningPlan,
    plan_items_data: list[dict],
    epoch: int,
    prior_by_activity: dict[str, LearningPlanItem] | None = None,
) -> list[LearningPlanItem]:
    created: list[LearningPlanItem] = []
    for raw in plan_items_data:
        change_status = "initial"
        is_new = False
        if epoch > 1 and prior_by_activity is not None:
            prev = prior_by_activity.get(raw["activity_id"])
            if prev is None:
                change_status = "new"
                is_new = True
            else:
                changed = (
                    prev.recommended_difficulty != raw["recommended_difficulty"]
                    or int(prev.due_revision_count or 0) != int(raw.get("due_revision_count") or 0)
                    or prev.reason != raw["reason"]
                    or prev.topic_status != raw["status"]
                    or prev.rank != int(raw["rank"])
                    or prev.blocked_by_prerequisite != raw.get("blocked_by_prerequisite")
                    or abs(float(prev.priority or 0) - float(raw["priority"])) >= 0.05
                )
                change_status = "updated" if changed else "unchanged"
                is_new = changed

        it = LearningPlanItem(
            plan_id=plan.id,
            activity_id=raw["activity_id"],
            revision_epoch=epoch,
            change_status=change_status,
            is_refreshed_new=is_new,
            rank=int(raw["rank"]),
            kind=raw["kind"],
            topic_key=raw["topic_key"],
            topic_label=raw["topic"],
            subject_label=raw["subject"],
            course_id=raw.get("course_id"),
            topic_id=raw.get("topic_id"),
            quiz_id=raw.get("quiz_id"),
            topic_status=raw["status"],
            mastery_label=raw["mastery_label"],
            mastery_score_pct=raw.get("mastery_score_pct"),
            evidence_sufficient=bool(raw["evidence_sufficient"]),
            unique_questions=int(raw.get("unique_questions") or 0),
            min_evidence=int(raw.get("min_evidence") or 5),
            recommended_difficulty=raw["recommended_difficulty"],
            priority=float(raw["priority"]),
            estimated_minutes=int(raw.get("estimated_minutes") or 0),
            estimated_hours=raw.get("estimated_hours"),
            reason=raw["reason"],
            due_revision_count=int(raw.get("due_revision_count") or 0),
            prerequisite_of=list(raw.get("prerequisite_of") or []),
            blocked_by_prerequisite=raw.get("blocked_by_prerequisite"),
            proposed_action=dict(raw["next_action"]),
            status="pending",
            approval_status="awaiting_approval",
        )
        db.add(it)
        created.append(it)
    return created


def create_learning_plan(
    db: Session,
    user: User,
    settings: Settings,
    checkpointer,
    body: LearningPlanCreateRequest,
    *,
    now: datetime | None = None,
) -> LearningPlanOut:
    """Creates a durable student-owned LearningPlan paused at LangGraph HITL interrupt before any action."""
    _require_active_student(user)
    now = now or utcnow()

    if body.course_id is not None:
        enrolled = set(perm.enrolled_course_ids(db, user))
        course = db.get(Course, body.course_id)
        if course is None or course.archived or body.course_id not in enrolled:
            raise perm.not_found("Course")

    thread_id = f"lp-s{user.id}-{uuid.uuid4().hex[:16]}"
    plan = LearningPlan(
        student_id=user.id,
        thread_id=thread_id,
        graph_version=STAGE2_GRAPH_VERSION,
        status="proposed",
        action_approval_status="pending",
        generation_seq=1,
        expires_at=now + timedelta(days=settings.learning_agent_plan_ttl_days),
    )
    db.add(plan)
    # Commit placeholder early to obtain plan.id AND release any SQLite write lock before checkpointer.put runs.
    db.commit()
    db.refresh(plan)

    graph = compile_persistent_learning_plan_graph(checkpointer)
    initial_state = {
        "plan_id": plan.id,
        "student_id": user.id,
        "weekly_study_hours_override": body.weekly_hours,
        "has_hours_override": body.weekly_hours is not None,
        "max_items": body.max_items,
        "scope_course_id": body.course_id,
        "generation_seq": 1,
        "plan_status": "proposed",
        "last_action_error": None,
        "node_history": [],
        "routing_history": [],
    }
    config = {
        "configurable": {
            "thread_id": thread_id,
            "db": db,
            "settings": settings,
            "expected_student_id": user.id,
            "now": now,
        }
    }
    try:
        state = graph.invoke(initial_state, config=config)
    except Exception:
        db.rollback()
        orphan = db.get(LearningPlan, plan.id)
        if orphan is not None:
            db.delete(orphan)
            db.commit()
        raise

    if not state.get("authorized"):
        db.delete(plan)
        db.commit()
        raise HTTPException(403, state.get("auth_error") or "Student authorization required.")

    # Populate persistent fields & epoch-1 items from deterministic graph output (zero auto-execution)
    plan_items_data = list(state.get("plan_items") or [])
    summary = dict(state.get("plan_summary") or {})
    plan.status = state.get("plan_status") or ("awaiting_approval" if plan_items_data else "proposed")
    plan.scenario = state.get("primary_scenario") or "no_eligible_material"
    plan.scenarios = list(state.get("scenarios") or ["no_eligible_material"])
    plan.routing_mode = state.get("post_validation_route") or state.get("candidate_route") or "no_eligible_material"
    plan.weekly_study_hours = state.get("weekly_study_hours")
    plan.weekly_hours_source = state.get("weekly_hours_source") or "unset"
    plan.scope_course_ids = (
        [body.course_id] if body.course_id is not None else list(state.get("enrolled_course_ids") or [])
    )
    plan.policy_versions = dict(summary.get("policy_versions") or {})
    if not plan.policy_versions:
        from app.agents.personalized_learning import POLICY_VERSIONS
        plan.policy_versions = dict(POLICY_VERSIONS)
    plan.summary = summary
    plan.warnings = list(state.get("warnings") or [])
    plan.deferred_topics = list(state.get("deferred_topics") or [])
    plan.proposed_next_actions = list(state.get("proposed_next_actions") or [])
    plan.graph_trace = {
        "nodes_visited": list(state.get("node_history") or []),
        "edges_taken": list(state.get("routing_history") or []),
    }
    plan.selected_activity_id = plan_items_data[0]["activity_id"] if plan_items_data else None
    plan.action_approval_status = "pending"

    _create_plan_items_for_epoch(db, plan, plan_items_data, epoch=1)

    rec = Recorder.start(
        db,
        agent="personalized_learning",
        user_id=user.id,
        course_id=body.course_id,
        input={"action": "create_plan", "plan_id": plan.id, "weekly_hours": body.weekly_hours},
    )
    rec.decide(
        "pause_for_approval",
        "Created personalized learning plan and paused at LangGraph HITL interrupt before any execution.",
        plan_id=plan.id,
        items_count=len(plan_items_data),
        scenario=plan.scenario,
    )
    rec.finish("done", output={"plan_id": plan.id, "status": plan.status, "items": len(plan_items_data)})

    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)


def get_current_learning_plan(
    db: Session,
    user: User,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> LearningPlanOut | None:
    """Returns the student's latest active plan (or latest historical plan if none active), or None."""
    _require_active_student(user)
    now = now or utcnow()
    plan = db.scalar(
        select(LearningPlan)
        .where(LearningPlan.student_id == user.id, LearningPlan.status.in_(ACTIVE_PLAN_STATUSES))
        .order_by(LearningPlan.id.desc())
        .limit(1)
    )
    if plan is None:
        plan = db.scalar(
            select(LearningPlan)
            .where(LearningPlan.student_id == user.id)
            .order_by(LearningPlan.id.desc())
            .limit(1)
        )
    if plan is None:
        return None
    sync_plan_progress_from_db(db, plan, user, now)
    return _serialize_plan(plan)


def get_learning_plan_by_id(
    db: Session,
    user: User,
    plan_id: int,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> LearningPlanOut:
    _require_active_student(user)
    now = now or utcnow()
    plan = _get_own_plan(db, user, plan_id)
    sync_plan_progress_from_db(db, plan, user, now)
    return _serialize_plan(plan)


def approve_plan_action(
    db: Session,
    user: User,
    plan_id: int,
    body_activity_id: str | None,
    idempotency_key: str | None,
    settings: Settings,
    checkpointer,
    *,
    model_service,
    generation_service,
    document_store=None,
    now: datetime | None = None,
) -> LearningPlanOut:
    """Resumes the student's LangGraph thread with explicit approval and executes via allowlisted services."""
    _require_active_student(user)
    now = now or utcnow()
    plan = _get_own_plan(db, user, plan_id)
    sync_plan_progress_from_db(db, plan, user, now)

    if plan.status in ("dismissed", "expired", "failed"):
        raise HTTPException(409, f"Cannot approve an action on a {plan.status} plan.")

    item = _resolve_plan_item_for_action(db, plan, body_activity_id)
    if item.status == "completed":
        raise HTTPException(409, "This activity has already been completed.")
    if item.status == "dismissed":
        raise HTTPException(409, "This dismissed recommendation cannot be started unless the plan is refreshed.")

    graph = compile_persistent_learning_plan_graph(checkpointer)
    cfg = {
        "configurable": {
            "thread_id": plan.thread_id,
            "db": db,
            "settings": settings,
            "expected_student_id": user.id,
            "now": now,
            "model_service": model_service,
            "generation_service": generation_service,
            "document_store": document_store,
        }
    }

    resume_payload = {
        "decision_type": "approve",
        "activity_id": item.activity_id,
        "idempotency_key": idempotency_key,
    }

    # Check whether the checkpoint is currently paused at interrupt OR needs idempotent fast-path / recovery
    has_interrupt = _has_pending_interrupt(graph, cfg)
    if not has_interrupt:
        # Check if there's an existing execution for this item or idempotency key; otherwise fail cleanly
        if idempotency_key:
            prev = db.scalar(
                select(LearningPlanExecution).where(
                    LearningPlanExecution.plan_id == plan.id,
                    LearningPlanExecution.activity_id == item.activity_id,
                    LearningPlanExecution.idempotency_key == idempotency_key,
                )
            )
            if prev and prev.status in ("executed", "handoff"):
                return _serialize_plan(plan, override_last_exec={
                    "action_type": prev.action_type,
                    "execution_status": "reused_existing",
                    "activity_id": item.activity_id,
                    "quiz_id": prev.quiz_id,
                    "session_id": prev.session_id,
                    "generation_run_id": prev.generation_run_id,
                    "destination_href": prev.destination_href,
                    "reused_existing": True,
                    "message": (prev.result_payload or {}).get("message") or "Returned previous execution.",
                    "executed_at": (prev.finished_at or prev.created_at or now).isoformat(),
                })
        raise HTTPException(409, "This plan is not currently awaiting approval. Refresh the plan first.")

    state = graph.invoke(Command(resume=resume_payload), config=cfg)
    action_err = state.get("last_action_error")
    if action_err:
        raise HTTPException(
            int(action_err.get("status_code") or 409),
            action_err.get("detail") or "This activity could not be started right now.",
        )
    last_exec = state.get("last_execution_result")

    # Sync latest graph trace & audit log (DB writes already committed cleanly inside action node)
    db.refresh(plan)
    plan.graph_trace = {
        "nodes_visited": list(state.get("node_history") or []),
        "edges_taken": list(state.get("routing_history") or []),
    }
    rec = Recorder.start(
        db,
        agent="personalized_learning",
        user_id=user.id,
        course_id=item.course_id,
        generation_run_id=(last_exec or {}).get("generation_run_id"),
        input={"action": "approve_action", "plan_id": plan.id, "activity_id": item.activity_id},
    )
    rec.decide(
        "approved_execution",
        f"Executed approved '{(last_exec or {}).get('action_type')}' for {item.topic_label}.",
        execution_status=(last_exec or {}).get("execution_status"),
        reused_existing=(last_exec or {}).get("reused_existing", False),
    )
    rec.finish("done", output=last_exec or {})
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan, override_last_exec=last_exec)


def apply_plan_decision(
    db: Session,
    user: User,
    plan_id: int,
    decision_type: str,
    body: LearningPlanDecisionRequest,
    settings: Settings,
    checkpointer,
    *,
    now: datetime | None = None,
) -> LearningPlanOut:
    """Handles explicit student dismiss or postpone via LangGraph Command(resume=...)."""
    _require_active_student(user)
    now = now or utcnow()
    plan = _get_own_plan(db, user, plan_id)
    sync_plan_progress_from_db(db, plan, user, now)

    if plan.status in ("dismissed", "expired"):
        if decision_type == "dismiss" and body.scope == "plan" and plan.status == "dismissed":
            return _serialize_plan(plan)
        raise HTTPException(409, f"Cannot modify a {plan.status} learning plan.")

    target_activity_id = None
    if not (decision_type == "dismiss" and body.scope == "plan"):
        item = _resolve_plan_item_for_action(db, plan, body.activity_id)
        if item.status == "completed":
            raise HTTPException(409, "Completed activities cannot be dismissed or postponed.")
        target_activity_id = item.activity_id

    graph = compile_persistent_learning_plan_graph(checkpointer)
    cfg = {
        "configurable": {
            "thread_id": plan.thread_id,
            "db": db,
            "settings": settings,
            "expected_student_id": user.id,
            "now": now,
        }
    }
    if not _has_pending_interrupt(graph, cfg):
        raise HTTPException(409, "This plan is not currently awaiting input. Refresh the plan first.")

    resume_payload = {
        "decision_type": decision_type,
        "scope": body.scope,
        "activity_id": target_activity_id,
        "note": body.note,
        "postpone_days": body.postpone_days,
    }
    state = graph.invoke(Command(resume=resume_payload), config=cfg)
    action_err = state.get("last_action_error")
    if action_err:
        raise HTTPException(
            int(action_err.get("status_code") or 409),
            action_err.get("detail") or "This activity could not be started right now.",
        )
    last_exec = state.get("last_execution_result")

    db.refresh(plan)
    plan.graph_trace = {
        "nodes_visited": list(state.get("node_history") or []),
        "edges_taken": list(state.get("routing_history") or []),
    }
    rec = Recorder.start(
        db,
        agent="personalized_learning",
        user_id=user.id,
        input={"action": f"{decision_type}_{body.scope}", "plan_id": plan.id, "activity_id": target_activity_id},
    )
    rec.decide(decision_type, (last_exec or {}).get("message") or f"Recorded {decision_type}.", note=body.note)
    rec.finish("done", output=last_exec or {})
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan, override_last_exec=last_exec)


def refresh_learning_plan(
    db: Session,
    user: User,
    plan_id: int,
    body: LearningPlanRefreshRequest,
    settings: Settings,
    checkpointer,
    *,
    now: datetime | None = None,
) -> LearningPlanOut:
    """Reloads latest mastery/revision/course evidence on the student's plan without auto-executing actions."""
    _require_active_student(user)
    now = now or utcnow()
    plan = _get_own_plan(db, user, plan_id)
    sync_plan_progress_from_db(db, plan, user, now)

    prev_epoch = int(plan.generation_seq or 1)
    prior_items = [i for i in plan.items if i.revision_epoch == prev_epoch]
    prior_by_activity = {i.activity_id: i for i in prior_items}

    # Determine hours setting to apply on refresh
    if body.weekly_hours is not None:
        has_override = True
        hours_override = body.weekly_hours
    elif plan.weekly_hours_source == "preview_override":
        has_override = True
        hours_override = plan.weekly_study_hours
    else:
        has_override = False
        hours_override = None

    # Reload across all active enrolled courses so newly joined courses appear on refresh
    scope_cid = None

    graph = compile_persistent_learning_plan_graph(checkpointer)
    cfg = {
        "configurable": {
            "thread_id": plan.thread_id,
            "db": db,
            "settings": settings,
            "expected_student_id": user.id,
            "now": now,
        }
    }

    if _has_pending_interrupt(graph, cfg):
        state = graph.invoke(
            Command(
                resume={
                    "decision_type": "refresh",
                    "has_hours_override": has_override,
                    "weekly_hours": hours_override,
                    "note": body.note,
                }
            ),
            config=cfg,
        )
    else:
        state = graph.invoke(
            {
                "plan_id": plan.id,
                "student_id": user.id,
                "weekly_study_hours_override": hours_override,
                "has_hours_override": has_override,
                "max_items": 6,
                "scope_course_id": scope_cid,
                "generation_seq": prev_epoch + 1,
                "plan_status": "proposed",
                "last_execution_result": None,
                "last_action_error": None,
                "node_history": [],
                "routing_history": [],
            },
            config=cfg,
        )

    if not state.get("authorized"):
        raise HTTPException(403, state.get("auth_error") or "Student authorization required.")

    new_epoch = int(state.get("generation_seq") or (prev_epoch + 1))
    plan_items_data = list(state.get("plan_items") or [])
    summary = dict(state.get("plan_summary") or {})

    # Preserve completed & dismissed prior-epoch records; mark unfinished prior-epoch items superseded
    for old_item in prior_items:
        if old_item.status in ("pending", "postponed", "in_progress"):
            old_item.status = "superseded"
            old_item.approval_status = "superseded"

    plan.generation_seq = new_epoch
    plan.last_refreshed_at = now
    plan.expires_at = now + timedelta(days=settings.learning_agent_plan_ttl_days)
    plan.status = state.get("plan_status") or ("awaiting_approval" if plan_items_data else "proposed")
    plan.action_approval_status = "pending"
    plan.last_execution_ref = None
    plan.scenario = state.get("primary_scenario") or "no_eligible_material"
    plan.scenarios = list(state.get("scenarios") or ["no_eligible_material"])
    plan.routing_mode = state.get("post_validation_route") or state.get("candidate_route") or "no_eligible_material"
    plan.weekly_study_hours = state.get("weekly_study_hours")
    plan.weekly_hours_source = state.get("weekly_hours_source") or "unset"
    plan.scope_course_ids = list(state.get("enrolled_course_ids") or [])
    plan.summary = summary
    plan.warnings = list(state.get("warnings") or [])
    plan.deferred_topics = list(state.get("deferred_topics") or [])
    plan.proposed_next_actions = list(state.get("proposed_next_actions") or [])
    plan.graph_trace = {
        "nodes_visited": list(state.get("node_history") or []),
        "edges_taken": list(state.get("routing_history") or []),
    }
    plan.selected_activity_id = plan_items_data[0]["activity_id"] if plan_items_data else None

    _create_plan_items_for_epoch(db, plan, plan_items_data, epoch=new_epoch, prior_by_activity=prior_by_activity)

    rec = Recorder.start(
        db,
        agent="personalized_learning",
        user_id=user.id,
        input={"action": "refresh_plan", "plan_id": plan.id, "from_epoch": prev_epoch, "to_epoch": new_epoch},
    )
    rec.decide(
        "refreshed_recommendations",
        "Refreshed learning plan from updated mastery and revision evidence without executing actions.",
        new_epoch=new_epoch,
        items_count=len(plan_items_data),
    )
    rec.finish("done", output={"plan_id": plan.id, "generation_seq": new_epoch, "items": len(plan_items_data)})

    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)
