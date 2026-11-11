"""Security, functional, rate-limit, and log-hygiene tests for Forgot Password / Reset Password."""
import hashlib
import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import Base
from app.core.security import verify_password
from app.main import create_app
from app.models import PasswordResetToken, User
from app.models.base import utcnow
from app.services.password_reset import DevResetOutbox, hash_reset_token, read_dev_outbox_cli
from scripts import dev_reset_outbox as outbox_cli
from tests.conftest import register


def _extract_reset_token(app, email: str) -> str:
    entries = app.state.reset_outbox.list_active(email=email)
    assert len(entries) == 1, f"Expected 1 outbox entry for {email}, got {entries}"
    query = parse_qs(urlsplit(entries[0]["reset_link"]).query)
    return query["token"][0]


def test_forgot_password_identical_response_and_hashed_storage(make_client, app):
    c = make_client()
    register(c, "student", email="Student.Reset@Gmail.com")
    register(make_client(), "student", email="inactive.reset@gmail.com")
    with app.state.db.session() as db:
        inactive = db.scalar(select(User).where(User.email == "inactive.reset@gmail.com"))
        inactive.is_active = False
        db.commit()

    r_real = c.post("/api/auth/forgot-password", json={"email": "  student.reset@gmail.com "})
    r_missing = c.post("/api/auth/forgot-password", json={"email": "does.not.exist@gmail.com"})
    r_inactive = c.post("/api/auth/forgot-password", json={"email": "inactive.reset@gmail.com"})

    assert r_real.status_code == r_missing.status_code == r_inactive.status_code == 200
    assert r_real.json() == r_missing.json() == r_inactive.json()
    assert "exists" in r_real.json()["message"]

    raw_token = _extract_reset_token(app, "student.reset@gmail.com")
    assert len(raw_token) >= 32
    assert app.state.reset_outbox.list_active(email="does.not.exist@gmail.com") == []
    assert app.state.reset_outbox.list_active(email="inactive.reset@gmail.com") == []

    with app.state.db.session() as db:
        rows = db.scalars(select(PasswordResetToken)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.token_hash != raw_token
        assert row.token_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert row.used_at is None
        delta_minutes = (row.expires_at - row.created_at).total_seconds() / 60.0
        assert 14.5 <= delta_minutes <= 15.5


@pytest.mark.parametrize("role", ["student", "lecturer"])
def test_reset_password_succeeds_for_student_and_lecturer_and_is_single_use(make_client, app, role):
    email = f"{role}.recovery@gmail.com"
    reg = make_client()
    register(reg, role, email=email, password="OldPassword1")

    pub = make_client()
    assert pub.post("/api/auth/forgot-password", json={"email": email}).status_code == 200
    token = _extract_reset_token(app, email)

    # Verification succeeds without consuming the single-use token
    v1 = pub.post("/api/auth/reset-password/verify", json={"token": token})
    assert v1.status_code == 200 and v1.json() == {"valid": True}
    assert pub.post("/api/auth/reset-password/verify", json={"token": token}).status_code == 200

    # Consume token
    r_reset = pub.post("/api/auth/reset-password", json={"token": token, "new_password": "N3wPassword9!"})
    assert r_reset.status_code == 204
    assert app.state.reset_outbox.list_active(email=email) == []

    # Old password fails; new password logs in cleanly with bcrypt hash
    assert pub.post("/api/auth/login", json={"email": email, "password": "OldPassword1"}).status_code == 401
    login_ok = pub.post("/api/auth/login", json={"email": email, "password": "N3wPassword9!"})
    assert login_ok.status_code == 200
    assert login_ok.json()["role"] == role

    with app.state.db.session() as db:
        u = db.scalar(select(User).where(User.email == email))
        assert verify_password("N3wPassword9!", u.password_hash)

    # Single-use: verifying or reusing the same token again is rejected
    v_reused = pub.post("/api/auth/reset-password/verify", json={"token": token})
    r_reused = pub.post("/api/auth/reset-password", json={"token": token, "new_password": "AnotherPassword2!"})
    assert v_reused.status_code == 400 and "invalid" in v_reused.json()["detail"].lower()
    assert r_reused.status_code == 400 and "invalid" in r_reused.json()["detail"].lower()


def test_reset_password_invalidates_all_active_sessions_and_clears_login_lockout(make_client, app):
    email = "sessions.reset@gmail.com"
    dev_a = make_client()
    register(dev_a, "student", email=email, password="StartPass1")
    dev_b = make_client()
    assert dev_b.post("/api/auth/login", json={"email": email, "password": "StartPass1"}).status_code == 200

    # Lock out dev_c on login attempts before recovery
    dev_c = make_client()
    for _ in range(5):
        dev_c.post("/api/auth/login", json={"email": email, "password": "WrongPass1"})
    assert dev_c.post("/api/auth/login", json={"email": email, "password": "StartPass1"}).status_code == 429

    assert dev_c.post("/api/auth/forgot-password", json={"email": email}).status_code == 200
    token = _extract_reset_token(app, email)
    assert dev_c.post("/api/auth/reset-password", json={"token": token, "new_password": "RecoveredPass2"}).status_code == 204

    # Both previously authenticated sessions are rejected because token_version bumped
    assert dev_a.get("/api/auth/me").status_code == 401
    assert dev_b.get("/api/auth/me").status_code == 401
    # User can immediately sign in with new password
    assert dev_c.post("/api/auth/login", json={"email": email, "password": "RecoveredPass2"}).status_code == 200


def test_new_request_and_change_password_invalidate_prior_tokens(make_client, app):
    email = "rotate.reset@gmail.com"
    c = make_client()
    register(c, "student", email=email, password="FirstPass1")

    c.post("/api/auth/forgot-password", json={"email": email})
    tok1 = _extract_reset_token(app, email)

    c.post("/api/auth/forgot-password", json={"email": email})
    tok2 = _extract_reset_token(app, email)
    assert tok1 != tok2

    # Earlier token invalidated when newer token issued
    assert c.post("/api/auth/reset-password/verify", json={"token": tok1}).status_code == 400
    assert c.post("/api/auth/reset-password", json={"token": tok1, "new_password": "SecondPass2"}).status_code == 400

    # Password change while logged in also invalidates outstanding reset token
    assert c.post("/api/auth/change-password",
                  json={"current_password": "FirstPass1", "new_password": "ChangedPass3"}).status_code == 204
    assert c.post("/api/auth/reset-password/verify", json={"token": tok2}).status_code == 400
    assert c.post("/api/auth/reset-password", json={"token": tok2, "new_password": "ThirdPass4"}).status_code == 400


def test_expired_and_malformed_tokens_fail(make_client, app):
    email = "edge.reset@gmail.com"
    c = make_client()
    register(c, "student", email=email, password="InitPass1")
    session_jwt = c.cookies.get(app.state.settings.cookie_name)

    c.post("/api/auth/forgot-password", json={"email": email})
    expired_tok = _extract_reset_token(app, email)
    with app.state.db.session() as db:
        row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_reset_token(expired_tok)))
        row.expires_at = utcnow() - timedelta(seconds=5)
        db.commit()

    v_exp = c.post("/api/auth/reset-password/verify", json={"token": expired_tok})
    r_exp = c.post("/api/auth/reset-password", json={"token": expired_tok, "new_password": "NewValidPass9"})
    assert v_exp.status_code == 400 and "expired" in v_exp.json()["detail"].lower()
    assert r_exp.status_code == 400 and "expired" in r_exp.json()["detail"].lower()
    assert c.post("/api/auth/login", json={"email": email, "password": "InitPass1"}).status_code == 200

    # Malformed & non-reset JWT tokens rejected with 400 (kept under verify rate limit of 10)
    for bad in ("short", "x" * 40, "contains space and ! chars " * 2, session_jwt):
        assert c.post("/api/auth/reset-password/verify", json={"token": bad}).status_code == 400
        assert c.post("/api/auth/reset-password", json={"token": bad, "new_password": "NewValidPass9"}).status_code == 400


def test_deactivated_user_tokens_fail_without_leaking_expiry(make_client, app):
    email = "deactivated.reset@gmail.com"
    c = make_client()
    register(c, "student", email=email, password="InitPass1")

    c.post("/api/auth/forgot-password", json={"email": email})
    active_tok = _extract_reset_token(app, email)

    with app.state.db.session() as db:
        u = db.scalar(select(User).where(User.email == email))
        u.is_active = False
        db.commit()

    v1 = c.post("/api/auth/reset-password/verify", json={"token": active_tok})
    r1 = c.post("/api/auth/reset-password", json={"token": active_tok, "new_password": "BlockedPass9"})
    assert v1.status_code == 400 and "invalid" in v1.json()["detail"].lower()
    assert r1.status_code == 400 and "invalid" in r1.json()["detail"].lower()

    # Even if an unexpired token later expires after account deactivation, it still reports generic invalid
    c2 = make_client()
    email2 = "deactivated2.reset@gmail.com"
    register(c2, "lecturer", email=email2, password="InitPass1")
    c2.post("/api/auth/forgot-password", json={"email": email2})
    tok2 = _extract_reset_token(app, email2)
    with app.state.db.session() as db:
        u2 = db.scalar(select(User).where(User.email == email2))
        u2.is_active = False
        row2 = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_reset_token(tok2)))
        row2.expires_at = utcnow() - timedelta(seconds=5)
        db.commit()
    r2 = c2.post("/api/auth/reset-password", json={"token": tok2, "new_password": "BlockedPass9"})
    assert r2.status_code == 400 and "expired" not in r2.json()["detail"].lower()


def test_weak_password_validation_preserves_valid_reset_token(make_client, app):
    email = "policy.reset@gmail.com"
    c = make_client()
    register(c, "student", email=email, password="InitPass1")
    c.post("/api/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(app, email)

    for weak in ("short1", "onlyletters", "12345678", "é" * 37 + "1"):
        r = c.post("/api/auth/reset-password", json={"token": token, "new_password": weak})
        assert r.status_code == 422

    # Token is still valid after 422 validation failures
    assert c.post("/api/auth/reset-password/verify", json={"token": token}).status_code == 200
    assert c.post("/api/auth/reset-password", json={"token": token, "new_password": "StrongPass9"}).status_code == 204


def test_rate_limits_forgot_password_and_token_verification(make_client, app):
    c = make_client()
    register(c, "student", email="ratelimit@gmail.com")

    # Per-email rate limit applies identically to existing and nonexistent accounts
    for target in ("ratelimit@gmail.com", "nonexistent@gmail.com"):
        for i in range(app.state.settings.reset_request_max):
            r = c.post("/api/auth/forgot-password", json={"email": target})
            assert r.status_code == 200, f"failed on {target} #{i}: {r.text}"
        blocked = c.post("/api/auth/forgot-password", json={"email": target})
        assert blocked.status_code == 429

    # IP-level rate limit across distinct emails
    app.state.reset_request_limiter.fails.clear()
    app.state.reset_ip_limiter.fails.clear()
    for i in range(app.state.settings.reset_ip_max):
        assert c.post("/api/auth/forgot-password", json={"email": f"u{i}@gmail.com"}).status_code == 200
    assert c.post("/api/auth/forgot-password", json={"email": "overflow@gmail.com"}).status_code == 429

    # Verify / reset brute-force protection
    app.state.reset_ip_limiter.fails.clear()
    c.post("/api/auth/forgot-password", json={"email": "ratelimit@gmail.com"})
    real_tok = _extract_reset_token(app, "ratelimit@gmail.com")
    for _ in range(app.state.settings.reset_verify_max):
        assert c.post("/api/auth/reset-password/verify", json={"token": "A" * 43}).status_code == 400
    assert c.post("/api/auth/reset-password/verify", json={"token": real_tok}).status_code == 429
    assert c.post("/api/auth/reset-password", json={"token": real_tok, "new_password": "NewStrong9"}).status_code == 429


def test_no_tokens_passwords_or_links_in_logs_and_outbox_safe(make_client, app, caplog, tmp_path):
    email = "loghygiene@gmail.com"
    secret_pw = "SuperSecretReset99!"
    c = make_client()
    register(c, "student", email=email, password="InitPass1")

    with caplog.at_level(logging.DEBUG):
        c.post("/api/auth/forgot-password", json={"email": email})
        tok = _extract_reset_token(app, email)
        c.post("/api/auth/reset-password/verify", json={"token": tok})
        c.post("/api/auth/reset-password", json={"token": tok, "new_password": secret_pw})
        c.post("/api/auth/reset-password", json={"token": tok, "new_password": secret_pw})

    assert tok not in caplog.text
    assert secret_pw not in caplog.text
    assert "reset-password?token=" not in caplog.text
    assert not app.state.mailer.outbox  # mailer.send() is never used for reset links

    # Dev outbox file & CLI work in development mode and strip expired entries
    dev_settings = Settings(_env_file=None, environment="development", secret_key="d" * 40)
    outbox_file = tmp_path / ".dev_reset_outbox.json"
    dev_outbox = DevResetOutbox(dev_settings, file_path=outbox_file)
    dev_outbox.record(
        email="expired@gmail.com",
        role="student",
        reset_link="http://localhost:5173/reset-password?token=expired",
        expires_at=utcnow() - timedelta(minutes=1),
    )
    dev_outbox.record(
        email="active@gmail.com",
        role="lecturer",
        reset_link="http://localhost:5173/reset-password?token=active_secret_tok",
        expires_at=utcnow() + timedelta(minutes=15),
    )
    active = read_dev_outbox_cli(dev_settings, file_path=outbox_file)
    assert [e["email"] for e in active] == ["active@gmail.com"]

    # Production strictly refuses outbox storage and CLI access
    prod_settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="p" * 40,
        cookie_secure=True,
        database_url="postgresql+psycopg://u:p@db/adaptiveiq",
        smtp_host="smtp.example.edu",
        smtp_from="noreply@example.edu",
    )
    prod_file = tmp_path / ".prod_outbox.json"
    prod_outbox = DevResetOutbox(prod_settings, file_path=prod_file)
    prod_outbox.record(
        email="x@example.com",
        role="student",
        reset_link="https://app/reset-password?token=SHOULD_NOT_BE_WRITTEN",
        expires_at=utcnow() + timedelta(minutes=15),
    )
    assert not prod_file.exists()
    with pytest.raises(RuntimeError, match="production"):
        prod_outbox.list_active()
    with pytest.raises(RuntimeError, match="production"):
        read_dev_outbox_cli(prod_settings, file_path=outbox_file)

    assert outbox_cli.main.__name__ == "main"


def test_smtp_delivery_never_logs_or_writes_dev_outbox(settings, caplog, monkeypatch):
    smtp_settings = settings.model_copy(
        update={"smtp_host": "127.0.0.1", "smtp_port": 1, "smtp_from": "noreply@example.edu"}
    )
    a = create_app(smtp_settings)
    Base.metadata.drop_all(a.state.db.engine)
    Base.metadata.create_all(a.state.db.engine)
    sent: list[tuple[str, str, str, int]] = []
    monkeypatch.setattr(
        a.state.mailer,
        "send_password_reset_smtp",
        lambda to, name, link, mins: sent.append((to, name, link, mins)),
    )
    try:
        with TestClient(a) as c:
            c.headers.update({"X-Requested-With": "AdaptiveIQ"})
            register(c, "student", email="smtp.user@gmail.com")
            with caplog.at_level(logging.DEBUG):
                assert c.post("/api/auth/forgot-password", json={"email": "smtp.user@gmail.com"}).status_code == 200
        assert len(sent) == 1 and "token=" in sent[0][2]
        tok = parse_qs(urlsplit(sent[0][2]).query)["token"][0]
        assert tok not in caplog.text
        assert a.state.reset_outbox.list_active() == []
    finally:
        a.state.db.engine.dispose()


def test_csrf_and_origin_enforced_on_recovery_endpoints(app):
    with TestClient(app) as bare:
        assert bare.post("/api/auth/forgot-password", json={"email": "a@gmail.com"}).status_code == 403
        assert bare.post("/api/auth/reset-password/verify", json={"token": "x" * 40}).status_code == 403
        assert bare.post(
            "/api/auth/reset-password", json={"token": "x" * 40, "new_password": "Passw0rd!"}
        ).status_code == 403

    with TestClient(app) as evil:
        evil.headers.update({"X-Requested-With": "AdaptiveIQ", "Origin": "https://evil.example"})
        assert evil.post("/api/auth/forgot-password", json={"email": "a@gmail.com"}).status_code == 403
