"""Schemas for Stage 1 (read-only preview) and Stage 2 (persistent HITL) of the LangGraph Personalized Learning Agent."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProposedActionOut(BaseModel):
    label: str
    action_type: Literal[
        "navigate_revision",
        "prefill_practice",
        "open_quiz",
        "open_profile",
        "open_courses",
        "practice_lab",
        "start_practice",
        "start_revision",
        "open_assessment",
    ]
    target_href: str
    prefill: dict | None = None
    read_only_preview: bool = True
    requires_approval: bool = False


class LearningPlanItemOut(BaseModel):
    rank: int = Field(ge=1)
    activity_id: str
    kind: Literal[
        "revisit_incorrect",
        "prerequisite",
        "practice_topic",
        "gather_evidence",
        "try_harder",
        "upcoming_assessment",
        "diagnostic_start",
        "maintain",
    ]
    topic_key: str
    topic: str
    subject: str
    course_id: int | None = None
    topic_id: int | None = None
    quiz_id: int | None = None
    status: str
    mastery_label: str
    mastery_score_pct: int | None = None
    evidence_sufficient: bool
    unique_questions: int = 0
    min_evidence: int = 5
    recommended_difficulty: str
    priority: float
    estimated_minutes: int = Field(ge=0)
    estimated_hours: float | None = None
    reason: str
    due_revision_count: int = 0
    prerequisite_of: list[str] = Field(default_factory=list)
    blocked_by_prerequisite: str | None = None
    next_action: ProposedActionOut


class DeferredTopicOut(BaseModel):
    topic_key: str
    topic: str
    subject: str
    kind: str
    reason: str


class LearningPlanSummaryOut(BaseModel):
    headline: str
    rationale: str
    weekly_study_hours: int | None = None
    weekly_hours_source: Literal["profile", "preview_override", "unset"] = "unset"
    budget_status: Literal["allocated", "unconfigured", "zero_hours", "empty"]
    allocated_minutes: int = 0
    allocated_hours: float = 0.0
    due_revision_total: int = 0
    upcoming_revision_total: int = 0
    insufficient_evidence_topics: int = 0
    weak_prerequisite_topics: int = 0
    sufficient_evidence_topics: int = 0
    empty_reason: str | None = None


class GraphEdgeStepOut(BaseModel):
    from_node: str
    condition: str
    to_node: str
    reason: str


class GraphTraceOut(BaseModel):
    nodes_visited: list[str]
    edges_taken: list[GraphEdgeStepOut]


class LearningPlanPreviewOut(BaseModel):
    agent: Literal["personalized_learning"] = "personalized_learning"
    stage: Literal[1] = 1
    mode: Literal["deterministic_preview"] = "deterministic_preview"
    llm_used: Literal[False] = False
    read_only: Literal[True] = True
    graph_version: str
    policy_versions: dict[str, str]
    generated_at: datetime
    scenario: str
    scenarios: list[str]
    routing_mode: str
    summary: LearningPlanSummaryOut
    items: list[LearningPlanItemOut]
    deferred_topics: list[DeferredTopicOut]
    proposed_next_actions: list[ProposedActionOut]
    warnings: list[str]
    graph_trace: GraphTraceOut


# ---------------- Stage 2: Persistent HITL Schemas ----------------

def _clean_opt_text(v: str | None) -> str | None:
    if v is None:
        return None
    s = " ".join(v.split()).strip()
    return s or None


class LearningPlanCreateRequest(BaseModel):
    weekly_hours: int | None = Field(default=None, ge=0, le=80)
    max_items: int = Field(default=6, ge=1, le=12)
    course_id: int | None = Field(default=None, ge=1)


class LearningPlanApproveRequest(BaseModel):
    activity_id: str | None = Field(default=None, min_length=1, max_length=320)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("activity_id", "idempotency_key")
    @classmethod
    def _clean_ids(cls, v: str | None) -> str | None:
        return _clean_opt_text(v)


class LearningPlanDecisionRequest(BaseModel):
    activity_id: str | None = Field(default=None, min_length=1, max_length=320)
    note: str | None = Field(default=None, max_length=300)
    postpone_days: int = Field(default=2, ge=1, le=30)
    scope: Literal["item", "plan"] = "item"

    @field_validator("activity_id", "note")
    @classmethod
    def _clean_fields(cls, v: str | None) -> str | None:
        return _clean_opt_text(v)


class LearningPlanRefreshRequest(BaseModel):
    weekly_hours: int | None = Field(default=None, ge=0, le=80)
    note: str | None = Field(default=None, max_length=300)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        return _clean_opt_text(v)


class ExecutionResultOut(BaseModel):
    action_type: Literal["start_practice", "start_revision", "open_assessment", "dismiss", "postpone", "none"]
    execution_status: Literal["started", "reused_existing", "handoff", "recorded", "failed"]
    activity_id: str | None = None
    quiz_id: int | None = None
    session_id: int | None = None
    generation_run_id: int | None = None
    destination_href: str | None = None
    reused_existing: bool = False
    message: str
    executed_at: datetime


class LearningPlanStage2ItemOut(LearningPlanItemOut):
    id: int
    revision_epoch: int = 1
    change_status: Literal["initial", "new", "updated", "unchanged"] = "initial"
    is_refreshed_new: bool = False
    item_status: Literal[
        "pending",
        "approved",
        "in_progress",
        "completed",
        "dismissed",
        "postponed",
        "superseded",
        "failed",
    ]
    approval_status: Literal[
        "awaiting_approval",
        "approved",
        "executed",
        "handoff",
        "dismissed",
        "postponed",
        "superseded",
        "failed",
    ]
    approved_action_type: Literal["start_practice", "start_revision", "open_assessment"] | None = None
    can_approve: bool = False
    can_dismiss: bool = False
    can_postpone: bool = False
    postponed_until: datetime | None = None
    decision_note: str | None = None
    execution_ref: ExecutionResultOut | None = None
    completed_at: datetime | None = None


class PlanProgressOut(BaseModel):
    total_items: int = 0
    pending_items: int = 0
    in_progress_items: int = 0
    completed_items: int = 0
    dismissed_items: int = 0
    postponed_items: int = 0
    completion_pct: int = 0


class PendingApprovalOut(BaseModel):
    awaiting_approval: bool = False
    default_activity_id: str | None = None
    actionable_activity_ids: list[str] = Field(default_factory=list)
    prompt: str = ""


class LearningPlanOut(BaseModel):
    id: int
    agent: Literal["personalized_learning"] = "personalized_learning"
    stage: Literal[2] = 2
    mode: Literal["persistent_hitl"] = "persistent_hitl"
    llm_used: Literal[False] = False
    graph_version: str
    policy_versions: dict[str, str]
    status: Literal[
        "proposed",
        "awaiting_approval",
        "in_progress",
        "completed",
        "dismissed",
        "expired",
        "failed",
    ]
    action_approval_status: str
    selected_activity_id: str | None = None
    generation_seq: int = 1
    last_refreshed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    scenario: str
    scenarios: list[str]
    routing_mode: str
    scope_course_ids: list[int] = Field(default_factory=list)
    summary: LearningPlanSummaryOut
    progress: PlanProgressOut
    pending_approval: PendingApprovalOut
    items: list[LearningPlanStage2ItemOut]
    previous_items: list[LearningPlanStage2ItemOut] = Field(default_factory=list)
    deferred_topics: list[DeferredTopicOut]
    proposed_next_actions: list[ProposedActionOut]
    warnings: list[str]
    last_execution: ExecutionResultOut | None = None
    graph_trace: GraphTraceOut
