"""Persistent Stage 2 Personalized Learning Plans, HITL decisions/executions, and LangGraph checkpoint storage."""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Float, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import UTCDateTime, utcnow


class LearningPlan(Base):
    """Durable student-owned Personalized Learning Plan backed by a LangGraph checkpoint thread."""
    __tablename__ = "learning_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[str] = mapped_column(String(120), unique=True)
    graph_version: Mapped[str] = mapped_column(String(60), default="langgraph-plan-v2")
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    scenario: Mapped[str] = mapped_column(String(60), default="no_eligible_material")
    scenarios: Mapped[list] = mapped_column(JSON, default=list)
    routing_mode: Mapped[str] = mapped_column(String(60), default="no_eligible_material")
    weekly_study_hours: Mapped[int | None] = mapped_column(Integer)
    weekly_hours_source: Mapped[str] = mapped_column(String(30), default="unset")
    scope_course_ids: Mapped[list] = mapped_column(JSON, default=list)
    policy_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    deferred_topics: Mapped[list] = mapped_column(JSON, default=list)
    proposed_next_actions: Mapped[list] = mapped_column(JSON, default=list)
    graph_trace: Mapped[dict] = mapped_column(JSON, default=dict)
    selected_activity_id: Mapped[str | None] = mapped_column(String(320))
    action_approval_status: Mapped[str] = mapped_column(String(30), default="pending")
    last_execution_ref: Mapped[dict | None] = mapped_column(JSON)
    generation_seq: Mapped[int] = mapped_column(Integer, default=1)
    refreshed_from_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="SET NULL")
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    items: Mapped[list["LearningPlanItem"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="LearningPlanItem.revision_epoch.desc(), LearningPlanItem.rank.asc(), LearningPlanItem.id.asc()",
    )
    executions: Mapped[list["LearningPlanExecution"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="LearningPlanExecution.id.desc()",
    )

    __table_args__ = (
        Index("ix_lp_student_status_updated", "student_id", "status", "updated_at"),
    )


class LearningPlanItem(Base):
    """One prioritized recommendation inside a persistent LearningPlan (epoch-versioned on refresh)."""
    __tablename__ = "learning_plan_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("learning_plans.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[str] = mapped_column(String(320), index=True)
    revision_epoch: Mapped[int] = mapped_column(Integer, default=1)
    change_status: Mapped[str] = mapped_column(String(20), default="initial")  # initial | new | updated | unchanged
    is_refreshed_new: Mapped[bool] = mapped_column(Boolean, default=False)
    rank: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    topic_key: Mapped[str] = mapped_column(String(300))
    topic_label: Mapped[str] = mapped_column(String(160))
    subject_label: Mapped[str] = mapped_column(String(160))
    course_id: Mapped[int | None] = mapped_column(Integer)
    topic_id: Mapped[int | None] = mapped_column(Integer)
    quiz_id: Mapped[int | None] = mapped_column(Integer)
    topic_status: Mapped[str] = mapped_column(String(40))
    mastery_label: Mapped[str] = mapped_column(String(40))
    mastery_score_pct: Mapped[int | None] = mapped_column(Integer)
    evidence_sufficient: Mapped[bool] = mapped_column(Boolean, default=False)
    unique_questions: Mapped[int] = mapped_column(Integer, default=0)
    min_evidence: Mapped[int] = mapped_column(Integer, default=5)
    recommended_difficulty: Mapped[str] = mapped_column(String(20))
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    due_revision_count: Mapped[int] = mapped_column(Integer, default=0)
    prerequisite_of: Mapped[list] = mapped_column(JSON, default=list)
    blocked_by_prerequisite: Mapped[str | None] = mapped_column(String(160))
    proposed_action: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    approval_status: Mapped[str] = mapped_column(String(30), default="awaiting_approval")
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_note: Mapped[str | None] = mapped_column(String(400))
    postponed_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    execution_ref: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    plan: Mapped[LearningPlan] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_lp_item_plan_epoch", "plan_id", "revision_epoch"),
    )


class LearningPlanExecution(Base):
    """Idempotent execution ledger for approved HITL actions and decisions."""
    __tablename__ = "learning_plan_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("learning_plans.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("learning_plan_items.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[str] = mapped_column(String(320))
    action_type: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="executing")
    quiz_id: Mapped[int | None] = mapped_column(ForeignKey("quizzes.id", ondelete="SET NULL"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="SET NULL"))
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"))
    destination_href: Mapped[str | None] = mapped_column(String(500))
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    plan: Mapped[LearningPlan] = relationship(back_populates="executions")

    __table_args__ = (
        UniqueConstraint("plan_id", "activity_id", "idempotency_key", name="uq_lp_exec_idempotency"),
    )


class LangGraphCheckpoint(Base):
    """SQLAlchemy-backed LangGraph checkpoint state compatible with both SQLite and PostgreSQL."""
    __tablename__ = "lg_checkpoints"

    thread_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(120), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(120))
    type: Mapped[str | None] = mapped_column(String(40))
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_type: Mapped[str | None] = mapped_column(String(40))
    metadata_blob: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        Index("ix_lg_cp_thread_ns_id", "thread_id", "checkpoint_ns", "checkpoint_id"),
    )


class LangGraphCheckpointBlob(Base):
    """Serialized channel values referenced by LangGraphCheckpoint."""
    __tablename__ = "lg_checkpoint_blobs"

    thread_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(120), primary_key=True, default="")
    channel: Mapped[str] = mapped_column(String(160), primary_key=True)
    version: Mapped[str] = mapped_column(String(120), primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    blob: Mapped[bytes | None] = mapped_column(LargeBinary)


class LangGraphCheckpointWrite(Base):
    """Intermediate task writes (including __interrupt__ / __resume__) for LangGraph resumption."""
    __tablename__ = "lg_checkpoint_writes"

    thread_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(120), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(160))
    type: Mapped[str | None] = mapped_column(String(40))
    blob: Mapped[bytes] = mapped_column(LargeBinary)
    task_path: Mapped[str] = mapped_column(String(300), default="")
