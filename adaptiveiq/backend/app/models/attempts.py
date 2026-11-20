from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import UTCDateTime, utcnow


class QuizSession(Base):
    """One attempt by one student at one quiz."""
    __tablename__ = "quiz_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)  # in_progress | submitted
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime)    # time limit or close time, earliest
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    submitted_by: Mapped[str | None] = mapped_column(String(20))         # student | time_limit
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    question_order: Mapped[list] = mapped_column(JSON)                   # question ids in display order
    option_order: Mapped[dict] = mapped_column(JSON, default=dict)       # question id -> option ids in order

    answers: Mapped[list["StudentAnswer"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    result: Mapped["QuizResult | None"] = relationship(back_populates="session", uselist=False,
                                                       cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("quiz_id", "student_id", "attempt_no", name="uq_session_attempt"),)


class StudentAnswer(Base):
    __tablename__ = "student_answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    selected_option_id: Mapped[int | None] = mapped_column(ForeignKey("answer_options.id", ondelete="SET NULL"))
    confidence: Mapped[int | None] = mapped_column(Integer)              # 1 guess, 2 unsure, 3 sure (optional)
    time_spent_s: Mapped[float | None] = mapped_column(Float)            # time on the question, client-measured
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # practice: answer revealed, now locked
    is_correct: Mapped[bool | None] = mapped_column(Boolean)             # set at submission
    session: Mapped[QuizSession] = relationship(back_populates="answers")
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_answer_once"),)


class QuizResult(Base):
    __tablename__ = "quiz_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"), unique=True)
    raw_score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)
    percentage: Mapped[float] = mapped_column(Float)
    late_penalty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    final_percentage: Mapped[float] = mapped_column(Float)              # after any late penalty
    contribution_earned: Mapped[float | None] = mapped_column(Float)    # points of the subject's internal grade
    correct: Mapped[int] = mapped_column(Integer)
    incorrect: Mapped[int] = mapped_column(Integer)
    unanswered: Mapped[int] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    algorithm_version: Mapped[str] = mapped_column(String(200))
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    session: Mapped[QuizSession] = relationship(back_populates="result")


class TopicMasterySnapshot(Base):
    """A mastery estimate at one moment. Rows are never updated, so history can be charted."""
    __tablename__ = "topic_mastery_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic_key: Mapped[str] = mapped_column(String(300))
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    subject_label: Mapped[str] = mapped_column(String(160))
    topic_label: Mapped[str] = mapped_column(String(160))
    score: Mapped[float] = mapped_column(Float)                     # posterior mean, 0..1
    lower: Mapped[float] = mapped_column(Float)                     # 80% credible interval
    upper: Mapped[float] = mapped_column(Float)
    evidence: Mapped[float] = mapped_column(Float)                  # effective number of answers after weighting
    answers: Mapped[int] = mapped_column(Integer)
    unique_questions: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(30))
    next_difficulty: Mapped[str] = mapped_column(String(10))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(200))
    trigger_session_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="SET NULL"))
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (Index("ix_mastery_student_topic_time", "student_id", "topic_key", "computed_at"),)


class LearningRecommendation(Base):
    __tablename__ = "learning_recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))       # practice_topic | revisit_incorrect | prerequisite | retry_later
    topic_key: Mapped[str] = mapped_column(String(300))
    subject_label: Mapped[str] = mapped_column(String(160))
    topic_label: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(String(400))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)   # open | done | dismissed | superseded
    algorithm_version: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RevisionSchedule(Base):
    """Leitner-style spaced revision for one missed question."""
    __tablename__ = "revision_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    topic_key: Mapped[str] = mapped_column(String(300))
    box: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    reviews: Mapped[int] = mapped_column(Integer, default=0)
    last_correct: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="active")   # active | retired
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("student_id", "question_id", name="uq_revision_item"),)
