"""Stage 2 Personalized Learning Agent plans, HITL executions, and durable LangGraph checkpoints.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

import app.models.base

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=120), nullable=False),
        sa.Column("graph_version", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("scenario", sa.String(length=60), nullable=False),
        sa.Column("scenarios", sa.JSON(), nullable=False),
        sa.Column("routing_mode", sa.String(length=60), nullable=False),
        sa.Column("weekly_study_hours", sa.Integer(), nullable=True),
        sa.Column("weekly_hours_source", sa.String(length=30), nullable=False),
        sa.Column("scope_course_ids", sa.JSON(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("deferred_topics", sa.JSON(), nullable=False),
        sa.Column("proposed_next_actions", sa.JSON(), nullable=False),
        sa.Column("graph_trace", sa.JSON(), nullable=False),
        sa.Column("selected_activity_id", sa.String(length=320), nullable=True),
        sa.Column("action_approval_status", sa.String(length=30), nullable=False),
        sa.Column("last_execution_ref", sa.JSON(), nullable=True),
        sa.Column("generation_seq", sa.Integer(), nullable=False),
        sa.Column("refreshed_from_plan_id", sa.Integer(), nullable=True),
        sa.Column("last_refreshed_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("expires_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["refreshed_from_plan_id"], ["learning_plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(op.f("ix_learning_plans_student_id"), "learning_plans", ["student_id"], unique=False)
    op.create_index(op.f("ix_learning_plans_status"), "learning_plans", ["status"], unique=False)
    op.create_index("ix_lp_student_status_updated", "learning_plans", ["student_id", "status", "updated_at"], unique=False)

    op.create_table(
        "learning_plan_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.String(length=320), nullable=False),
        sa.Column("revision_epoch", sa.Integer(), nullable=False),
        sa.Column("change_status", sa.String(length=20), nullable=False),
        sa.Column("is_refreshed_new", sa.Boolean(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("topic_key", sa.String(length=300), nullable=False),
        sa.Column("topic_label", sa.String(length=160), nullable=False),
        sa.Column("subject_label", sa.String(length=160), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("quiz_id", sa.Integer(), nullable=True),
        sa.Column("topic_status", sa.String(length=40), nullable=False),
        sa.Column("mastery_label", sa.String(length=40), nullable=False),
        sa.Column("mastery_score_pct", sa.Integer(), nullable=True),
        sa.Column("evidence_sufficient", sa.Boolean(), nullable=False),
        sa.Column("unique_questions", sa.Integer(), nullable=False),
        sa.Column("min_evidence", sa.Integer(), nullable=False),
        sa.Column("recommended_difficulty", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_hours", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("due_revision_count", sa.Integer(), nullable=False),
        sa.Column("prerequisite_of", sa.JSON(), nullable=False),
        sa.Column("blocked_by_prerequisite", sa.String(length=160), nullable=True),
        sa.Column("proposed_action", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approved_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=400), nullable=True),
        sa.Column("postponed_until", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("execution_ref", sa.JSON(), nullable=True),
        sa.Column("completed_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["learning_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_plan_items_plan_id"), "learning_plan_items", ["plan_id"], unique=False)
    op.create_index(op.f("ix_learning_plan_items_activity_id"), "learning_plan_items", ["activity_id"], unique=False)
    op.create_index(op.f("ix_learning_plan_items_status"), "learning_plan_items", ["status"], unique=False)
    op.create_index("ix_lp_item_plan_epoch", "learning_plan_items", ["plan_id", "revision_epoch"], unique=False)

    op.create_table(
        "learning_plan_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.String(length=320), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("generation_run_id", sa.Integer(), nullable=True),
        sa.Column("destination_href", sa.String(length=500), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=400), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("finished_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["learning_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["learning_plan_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["quiz_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "activity_id", "idempotency_key", name="uq_lp_exec_idempotency"),
    )
    op.create_index(op.f("ix_learning_plan_executions_plan_id"), "learning_plan_executions", ["plan_id"], unique=False)
    op.create_index(op.f("ix_learning_plan_executions_item_id"), "learning_plan_executions", ["item_id"], unique=False)
    op.create_index(op.f("ix_learning_plan_executions_student_id"), "learning_plan_executions", ["student_id"], unique=False)

    op.create_table(
        "lg_checkpoints",
        sa.Column("thread_id", sa.String(length=120), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=120), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=120), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(length=120), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=True),
        sa.Column("checkpoint", sa.LargeBinary(), nullable=False),
        sa.Column("metadata_type", sa.String(length=40), nullable=True),
        sa.Column("metadata_blob", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_index("ix_lg_cp_thread_ns_id", "lg_checkpoints", ["thread_id", "checkpoint_ns", "checkpoint_id"], unique=False)

    op.create_table(
        "lg_checkpoint_blobs",
        sa.Column("thread_id", sa.String(length=120), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version"),
    )

    op.create_table(
        "lg_checkpoint_writes",
        sa.Column("thread_id", sa.String(length=120), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=120), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=120), nullable=False),
        sa.Column("task_id", sa.String(length=120), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=True),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.String(length=300), nullable=False),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
    )


def downgrade() -> None:
    op.drop_table("lg_checkpoint_writes")
    op.drop_table("lg_checkpoint_blobs")
    op.drop_index("ix_lg_cp_thread_ns_id", table_name="lg_checkpoints")
    op.drop_table("lg_checkpoints")

    op.drop_index(op.f("ix_learning_plan_executions_student_id"), table_name="learning_plan_executions")
    op.drop_index(op.f("ix_learning_plan_executions_item_id"), table_name="learning_plan_executions")
    op.drop_index(op.f("ix_learning_plan_executions_plan_id"), table_name="learning_plan_executions")
    op.drop_table("learning_plan_executions")

    op.drop_index("ix_lp_item_plan_epoch", table_name="learning_plan_items")
    op.drop_index(op.f("ix_learning_plan_items_status"), table_name="learning_plan_items")
    op.drop_index(op.f("ix_learning_plan_items_activity_id"), table_name="learning_plan_items")
    op.drop_index(op.f("ix_learning_plan_items_plan_id"), table_name="learning_plan_items")
    op.drop_table("learning_plan_items")

    op.drop_index("ix_lp_student_status_updated", table_name="learning_plans")
    op.drop_index(op.f("ix_learning_plans_status"), table_name="learning_plans")
    op.drop_index(op.f("ix_learning_plans_student_id"), table_name="learning_plans")
    op.drop_table("learning_plans")
