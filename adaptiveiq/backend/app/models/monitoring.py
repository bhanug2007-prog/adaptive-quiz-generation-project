"""Assessment integrity monitoring: one monitoring session per monitored attempt and the events the browser
recorded during it. Only events are stored, never video or audio."""
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UTCDateTime, utcnow


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"), unique=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)        # what was monitored, copied at consent
    consented_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    camera: Mapped[str] = mapped_column(String(20), default="not_requested")       # granted | denied | unavailable | not_requested
    microphone: Mapped[str] = mapped_column(String(20), default="not_requested")
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    dropped_events: Mapped[int] = mapped_column(Integer, default=0)   # rejected for bad time or over the cap
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    review: Mapped[str | None] = mapped_column(String(20))            # lecturer's outcome: no_concern | follow_up
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MonitoringEvent(Base):
    __tablename__ = "monitoring_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    monitoring_session_id: Mapped[int] = mapped_column(ForeignKey("monitoring_sessions.id", ondelete="CASCADE"),
                                                       index=True)
    seq: Mapped[int] = mapped_column(Integer)                         # browser's counter; repeats are ignored
    kind: Mapped[str] = mapped_column(String(30))
    client_at: Mapped[datetime] = mapped_column(UTCDateTime)          # when it happened, by the browser's clock
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("monitoring_session_id", "seq", name="uq_monitoring_event_seq"),)
