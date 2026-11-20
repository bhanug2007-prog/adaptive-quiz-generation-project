from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import UTCDateTime, utcnow


class ExternalIntegration(Base):
    """One user's connection to an outside service. Tokens are stored encrypted (see integrations/crypto.py)."""
    __tablename__ = "external_integrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))               # google_forms
    status: Mapped[str] = mapped_column(String(20))                 # connected | expired | revoked
    scopes: Mapped[str] = mapped_column(Text)
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_integration_user_provider"),)


class FormExport(Base):
    __tablename__ = "form_exports"
    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))                 # created | partial | failed
    form_id: Mapped[str | None] = mapped_column(String(200))
    responder_url: Mapped[str | None] = mapped_column(Text)
    edit_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
