"""Assessment integrity monitoring: quiz settings, monitoring sessions and monitoring events.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

import app.models.base

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

QUIZ_COLUMNS = ("monitor_tab", "monitor_fullscreen", "monitor_camera", "monitor_microphone")


def upgrade() -> None:
    # Existing quizzes get monitoring switched off.
    op.add_column("quizzes", sa.Column("monitor_tab", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("quizzes", sa.Column("monitor_fullscreen", sa.String(length=10), nullable=False, server_default="off"))
    op.add_column("quizzes", sa.Column("monitor_camera", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("quizzes", sa.Column("monitor_microphone", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "monitoring_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("consented_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("camera", sa.String(length=20), nullable=False),
        sa.Column("microphone", sa.String(length=20), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("dropped_events", sa.Integer(), nullable=False),
        sa.Column("last_event_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("review", sa.String(length=20), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["quiz_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(op.f("ix_monitoring_sessions_quiz_id"), "monitoring_sessions", ["quiz_id"], unique=False)
    op.create_index(op.f("ix_monitoring_sessions_student_id"), "monitoring_sessions", ["student_id"], unique=False)
    op.create_table(
        "monitoring_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("monitoring_session_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("client_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("received_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["monitoring_session_id"], ["monitoring_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("monitoring_session_id", "seq", name="uq_monitoring_event_seq"),
    )
    op.create_index(op.f("ix_monitoring_events_monitoring_session_id"), "monitoring_events",
                    ["monitoring_session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_monitoring_events_monitoring_session_id"), table_name="monitoring_events")
    op.drop_table("monitoring_events")
    op.drop_index(op.f("ix_monitoring_sessions_student_id"), table_name="monitoring_sessions")
    op.drop_index(op.f("ix_monitoring_sessions_quiz_id"), table_name="monitoring_sessions")
    op.drop_table("monitoring_sessions")
    with op.batch_alter_table("quizzes") as b:      # batch mode so SQLite can drop columns too
        for c in reversed(QUIZ_COLUMNS):
            b.drop_column(c)
