"""Cryptographic single-use password reset tokens and a dev-only local outbox.

Security properties:
- Plaintext tokens are generated with ``secrets.token_urlsafe(32)`` and never stored in the database.
- Only the SHA-256 hex digest is persisted on ``password_reset_tokens``.
- Reset tokens expire after ``Settings.reset_token_minutes`` (default 15) and are burned atomically via
  ``UPDATE ... WHERE used_at IS NULL AND expires_at > :now``.
- When SMTP is unavailable outside production, reset links are written ONLY to ``DevResetOutbox`` (never to
  application logs, never exposed on any HTTP route, and explicitly blocked in production).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models import PasswordResetToken, User
from app.models.base import utcnow
from app.services.mailer import Mailer

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DEV_OUTBOX_PATH = _BACKEND_DIR / ".dev_reset_outbox.json"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_well_formed_token(token: str | None) -> bool:
    return bool(token and _TOKEN_RE.fullmatch(token))


@dataclass(frozen=True)
class ResetCheckResult:
    status: Literal["valid", "invalid", "expired"]
    user: User | None = None


class DevResetOutbox:
    """Thread-safe development/test outbox for password-reset links when SMTP is disabled.

    Never writes anything in ``production``, and never logs tokens, links, or emails.
    In ``development``, persists active (non-expired) entries to ``.dev_reset_outbox.json`` so a local
    developer CLI command (``python -m scripts.dev_reset_outbox``) can read them without exposing any HTTP route.
    """

    def __init__(self, settings: Settings, file_path: Path | None = None):
        self.s = settings
        self.enabled = settings.environment != "production"
        if file_path is not None:
            self.file_path: Path | None = Path(file_path) if self.enabled else None
        elif settings.environment == "development":
            self.file_path = DEFAULT_DEV_OUTBOX_PATH
        else:
            self.file_path = None
        self._lock = threading.Lock()
        self._entries: deque[dict] = deque(maxlen=50)

    def _is_active_entry(self, entry: dict, now: datetime) -> bool:
        try:
            exp = datetime.fromisoformat(entry["expires_at"])
        except Exception:
            return False
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > now

    def _read_file_entries(self, now: datetime) -> list[dict]:
        if not self.file_path or not self.file_path.exists():
            return []
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        return [e for e in raw if isinstance(e, dict) and self._is_active_entry(e, now)]

    def _write_file_entries(self, entries: list[dict]) -> None:
        if not self.file_path:
            return
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(entries[-50:], indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.file_path.parent), prefix=".dev_reset_outbox_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            if os.name == "posix":
                os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.file_path)
            if os.name == "posix":
                os.chmod(self.file_path, 0o600)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    def record(self, *, email: str, role: str, reset_link: str, expires_at: datetime) -> None:
        if not self.enabled:
            return
        now = utcnow()
        entry = {
            "email": email,
            "role": role,
            "reset_link": reset_link,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "created_at": now.isoformat(),
        }
        with self._lock:
            active_mem = [e for e in self._entries if self._is_active_entry(e, now)]
            # Keep only the newest link per email in dev view
            active_mem = [e for e in active_mem if e.get("email") != email]
            active_mem.append(entry)
            self._entries.clear()
            self._entries.extend(active_mem[-50:])

            if self.file_path is not None:
                active_file = [e for e in self._read_file_entries(now) if e.get("email") != email]
                active_file.append(entry)
                self._write_file_entries(active_file)

    def purge_for_email(self, email: str) -> None:
        if not self.enabled:
            return
        now = utcnow()
        norm = email.strip().lower()
        with self._lock:
            active_mem = [e for e in self._entries if self._is_active_entry(e, now) and e.get("email") != norm]
            self._entries.clear()
            self._entries.extend(active_mem)
            if self.file_path is not None and self.file_path.exists():
                active_file = [e for e in self._read_file_entries(now) if e.get("email") != norm]
                self._write_file_entries(active_file)

    def list_active(self, email: str | None = None) -> list[dict]:
        if not self.enabled:
            raise RuntimeError("Development reset outbox is disabled in production.")
        now = utcnow()
        norm = email.strip().lower() if email else None
        with self._lock:
            if self.file_path is not None and self.file_path.exists():
                entries = self._read_file_entries(now)
            else:
                entries = [e for e in self._entries if self._is_active_entry(e, now)]
        if norm:
            entries = [e for e in entries if e.get("email") == norm]
        return list(entries)


def read_dev_outbox_cli(settings: Settings, email: str | None = None, file_path: Path | None = None) -> list[dict]:
    """Local CLI reader; strictly refuses production environments."""
    if settings.environment == "production":
        raise RuntimeError("Refusing to read development reset outbox in production environment.")
    path = Path(file_path) if file_path is not None else DEFAULT_DEV_OUTBOX_PATH
    if not path.exists():
        return []
    outbox = DevResetOutbox(settings, file_path=path)
    return outbox.list_active(email=email)


def issue_reset_token(db: Session, user: User, expires_minutes: int) -> tuple[str, datetime]:
    """Invalidate earlier unused tokens for this user and create a fresh single-use hashed token."""
    now = utcnow()
    expires_at = now + timedelta(minutes=expires_minutes)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_reset_token(raw_token)

    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    return raw_token, expires_at


def deliver_password_reset(
    *,
    settings: Settings,
    mailer: Mailer,
    outbox: DevResetOutbox,
    user: User,
    raw_token: str,
    expires_at: datetime,
) -> None:
    link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={raw_token}"
    if settings.smtp_configured:
        mailer.send_password_reset_smtp(user.email, user.full_name, link, settings.reset_token_minutes)
        return
    if settings.environment == "production":
        return
    outbox.record(email=user.email, role=user.role, reset_link=link, expires_at=expires_at)


def check_reset_token(db: Session, raw_token: str) -> ResetCheckResult:
    """Inspect whether a token can still be used without consuming it."""
    if not is_well_formed_token(raw_token):
        return ResetCheckResult("invalid")
    now = utcnow()
    token_hash = hash_reset_token(raw_token)
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    if row is None or row.used_at is not None:
        return ResetCheckResult("invalid")
    if row.expires_at <= now:
        return ResetCheckResult("expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return ResetCheckResult("invalid")
    return ResetCheckResult("valid", user=user)


def consume_and_reset_password(db: Session, raw_token: str, new_password: str) -> ResetCheckResult:
    """Atomically burn a single-use token, update password hash, bump token_version, and invalidate siblings."""
    if not is_well_formed_token(raw_token):
        return ResetCheckResult("invalid")
    now = utcnow()
    token_hash = hash_reset_token(raw_token)

    claimed = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    if claimed.rowcount != 1:
        db.rollback()
        existing = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
        if existing is not None and existing.used_at is None and existing.expires_at <= now:
            owner = db.get(User, existing.user_id)
            if owner is not None and owner.is_active:
                return ResetCheckResult("expired")
        return ResetCheckResult("invalid")

    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    user = db.get(User, row.user_id) if row is not None else None
    if user is None or not user.is_active:
        db.commit()  # keep token burned so it can never be retried
        return ResetCheckResult("invalid")

    user.password_hash = hash_password(new_password)
    user.token_version += 1
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.id != row.id,
        )
        .values(used_at=now)
    )
    db.commit()
    return ResetCheckResult("valid", user=user)
