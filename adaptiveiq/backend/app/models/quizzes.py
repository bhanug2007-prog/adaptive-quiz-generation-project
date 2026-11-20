from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import UTCDateTime, utcnow


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    variant: Mapped[str] = mapped_column(String(20))                 # finetuned | base
    base_model: Mapped[str] = mapped_column(String(200))
    adapter: Mapped[str | None] = mapped_column(String(200))
    quantization: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("name", "variant", "base_model", "adapter", "quantization",
                                       name="uq_model_version"),)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))                 # lecturer_draft | practice | regenerate
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    params: Mapped[dict] = mapped_column(JSON)                       # subject, topic, counts, difficulty plan...
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(200), default="Waiting to start")
    ready: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[dict] = mapped_column(JSON, default=dict)
    grounded_on: Mapped[str | None] = mapped_column(String(30))     # reference_text | generated_notes
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    avg_question_s: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[dict | None] = mapped_column(JSON)               # AI review use, difficulty mix check, kept failures


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), index=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    objective_id: Mapped[int | None] = mapped_column(ForeignKey("learning_objectives.id", ondelete="SET NULL"))
    topic_key: Mapped[str] = mapped_column(String(300), index=True)  # t:<id> or p:<subject>|<topic>
    subject_label: Mapped[str] = mapped_column(String(160))
    unit_label: Mapped[str | None] = mapped_column(String(160))
    topic_label: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(10))              # easy | medium | hard
    source_type: Mapped[str] = mapped_column(String(30))             # reference_text | generated_notes | manual
    source_excerpt: Mapped[str | None] = mapped_column(Text)         # the context passage the model used
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"))
    review_status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft|approved|rejected|personal
    validation: Mapped[dict] = mapped_column(JSON, default=dict)     # math_verified, grounding overlap, ...
    derived_from_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    options: Mapped[list["AnswerOption"]] = relationship(back_populates="question", cascade="all, delete-orphan",
                                                         order_by="AnswerOption.position")


class AnswerOption(Base):
    __tablename__ = "answer_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(1))                    # A-D
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[Question] = relationship(back_populates="options")
    __table_args__ = (UniqueConstraint("question_id", "label", name="uq_option_label"),)


class QuestionEvaluation(Base):
    """One quality check of one generated question (or of a rejected attempt, which has no question row).
    Every attempt is logged, so the run's decisions can be audited later."""
    __tablename__ = "question_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"),
                                                          index=True)
    slot: Mapped[int | None] = mapped_column(Integer)                # question number in the run (1-based)
    attempt: Mapped[int | None] = mapped_column(Integer)             # 1-based try for that slot
    evaluator: Mapped[str] = mapped_column(String(20))               # grok | rules (Python checks only)
    evaluator_model: Mapped[str | None] = mapped_column(String(120))
    requested_difficulty: Mapped[str | None] = mapped_column(String(10))
    passed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(40))           # first failed check, e.g. quality_incorrect
    quality_score: Mapped[float | None] = mapped_column(Float)       # 0-100, AI review only
    checks: Mapped[dict] = mapped_column(JSON, default=dict)         # Python check results + AI assessments
    feedback: Mapped[str | None] = mapped_column(Text)
    regeneration_instructions: Mapped[str | None] = mapped_column(Text)
    ai_error: Mapped[str | None] = mapped_column(Text)               # why the AI review was not used
    snapshot: Mapped[dict | None] = mapped_column(JSON)              # the attempt's text when it was not stored
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AgentRun(Base):
    """One run of an agent (question_quality or lecturer_insights): what it was asked and how it ended."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)       # question_quality | lecturer_insights
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), index=True)
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"),
                                                          index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | done | partial | failed | cancelled
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON)
    llm: Mapped[str | None] = mapped_column(String(60))              # LLM used for decisions/wording, if any
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AgentStep(Base):
    """One tool call or decision inside an agent run, in order."""
    __tablename__ = "agent_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))                    # tool | decision | llm
    name: Mapped[str] = mapped_column(String(60))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class QuestionReviewRecord(Base):
    __tablename__ = "question_review_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(20))                  # edited | approved | rejected | regenerated
    note: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))                    # assessment | practice
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft | published | archived
    graded: Mapped[bool] = mapped_column(Boolean, default=True)
    max_marks: Mapped[float] = mapped_column(Float, default=0.0)
    attempts_allowed: Mapped[int] = mapped_column(Integer, default=1)
    opens_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    closes_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # last moment a late submission is accepted
    time_limit_min: Mapped[int | None] = mapped_column(Integer)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_release: Mapped[str] = mapped_column(String(20), default="immediate")  # immediate | after_due | manual
    feedback_released: Mapped[bool] = mapped_column(Boolean, default=False)          # for manual
    late_policy: Mapped[str] = mapped_column(String(20), default="none")             # none | allow | penalty
    late_penalty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    contribution_pct: Mapped[float] = mapped_column(Float, default=0.0)  # share of the subject's internal assessment
    confidence_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    target_duration_min: Mapped[int | None] = mapped_column(Integer)
    # Integrity monitoring (assessments only; all off by default). See docs/MONITORING.md.
    monitor_tab: Mapped[bool] = mapped_column(Boolean, default=False)
    monitor_fullscreen: Mapped[str] = mapped_column(String(10), default="off")      # off | record | required
    monitor_camera: Mapped[bool] = mapped_column(Boolean, default=False)
    monitor_microphone: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    items: Mapped[list["QuizQuestion"]] = relationship(back_populates="quiz", cascade="all, delete-orphan",
                                                       order_by="QuizQuestion.position")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="RESTRICT"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    marks: Mapped[float] = mapped_column(Float, default=1.0)
    quiz: Mapped[Quiz] = relationship(back_populates="items")
    question: Mapped[Question] = relationship()
    __table_args__ = (UniqueConstraint("quiz_id", "question_id", name="uq_quiz_question"),)


class QuizAssignment(Base):
    __tablename__ = "quiz_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)  # None = whole course
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (Index("ix_assignment_quiz_student", "quiz_id", "student_id"),)
