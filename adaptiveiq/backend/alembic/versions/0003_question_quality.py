"""Question quality evaluations and the run-level quality summary.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

import app.models.base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("generation_run_id", sa.Integer(), nullable=True),
        sa.Column("slot", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=True),
        sa.Column("evaluator", sa.String(length=20), nullable=False),
        sa.Column("evaluator_model", sa.String(length=120), nullable=True),
        sa.Column("requested_difficulty", sa.String(length=10), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("regeneration_instructions", sa.Text(), nullable=True),
        sa.Column("ai_error", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["generation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_question_evaluations_question_id"), "question_evaluations", ["question_id"], unique=False)
    op.create_index(op.f("ix_question_evaluations_generation_run_id"), "question_evaluations", ["generation_run_id"],
                    unique=False)
    with op.batch_alter_table("generation_runs") as batch:
        batch.add_column(sa.Column("quality", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_runs") as batch:
        batch.drop_column("quality")
    op.drop_index(op.f("ix_question_evaluations_generation_run_id"), table_name="question_evaluations")
    op.drop_index(op.f("ix_question_evaluations_question_id"), table_name="question_evaluations")
    op.drop_table("question_evaluations")
