"""Email verification, CSRF origin check, server-side logout, invite-code limits, production settings."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import Base
from app.main import create_app
from tests.conftest import INVITE, register


@pytest.fixture
def vapp(settings):
    """Same as the normal test app, but with email verification required."""
    a = create_app(settings.model_copy(update={"require_email_verification": True}))
    Base.metadata.drop_all(a.state.db.engine)
    Base.metadata.create_all(a.state.db.engine)
    yield a
    a.state.db.engine.dispose()


def client(app):
    c = TestClient(app)
    c.headers.update({"X-Requested-With": "AdaptiveIQ"})
    return c


def link_token(app, email):
    msg = [m for m in app.state.mailer.outbox if m["to"] == email][-1]
    return msg["body"].split("token=")[1].split()[0]


def test_unverified_account_is_limited_until_link_opened(vapp):
    with client(vapp) as lec, client(vapp) as st:
        me = register(lec, "lecturer", email="lec@example.edu")
        assert me["email_verified"] is False and me["verification_required"] is True
        r = lec.post("/api/lecturer/courses", json={"code": "CS1", "title": "Course"})
        assert r.status_code == 403 and "Verify your email" in r.json()["detail"]
        assert lec.post("/api/auth/verify-email", json={"token": link_token(vapp, "lec@example.edu")}).json()["email_verified"]
        course = lec.post("/api/lecturer/courses", json={"code": "CS1", "title": "Course"}).json()

        register(st, "student", email="st@example.edu")
        assert st.get("/api/student/courses").status_code == 200                       # can look around
        assert st.post("/api/student/courses/join", json={"join_code": course["join_code"]}).status_code == 403
        st.post("/api/auth/verify-email", json={"token": link_token(vapp, "st@example.edu")})
        assert st.post("/api/student/courses/join", json={"join_code": course["join_code"]}).status_code == 200


def test_verification_tokens_cannot_be_swapped_with_sessions(vapp):
    with client(vapp) as c:
        register(c, "student", email="swap@example.edu")
        session = c.cookies.get(vapp.state.settings.cookie_name)
        assert c.post("/api/auth/verify-email", json={"token": session}).status_code == 400
        assert c.post("/api/auth/verify-email", json={"token": "x" * 40}).status_code == 400
        verify = link_token(vapp, "swap@example.edu")
    with client(vapp) as other:
        other.cookies.set(vapp.state.settings.cookie_name, verify)
        assert other.get("/api/auth/me").status_code == 401


def test_resend_is_rate_limited(vapp):
    with client(vapp) as c:
        register(c, "student", email="resend@example.edu")
        assert c.post("/api/auth/resend-verification").status_code == 204
        assert c.post("/api/auth/resend-verification").status_code == 429
        assert len([m for m in vapp.state.mailer.outbox if m["to"] == "resend@example.edu"]) == 2


def test_logout_invalidates_the_session_on_the_server(make_client, app):
    c = make_client()
    register(c, "student")
    token = c.cookies.get(app.state.settings.cookie_name)
    assert c.post("/api/auth/logout").status_code == 204
    with client(app) as thief:
        thief.cookies.set(app.state.settings.cookie_name, token)
        assert thief.get("/api/auth/me").status_code == 401


def test_cross_site_origin_is_refused(make_client):
    c = make_client()
    register(c, "student")
    assert c.patch("/api/auth/me", json={"full_name": "New Name"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.patch("/api/auth/me", json={"full_name": "New Name"},
                   headers={"Referer": "https://evil.example/page"}).status_code == 403
    assert c.patch("/api/auth/me", json={"full_name": "New Name"}, headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert c.get("/api/auth/me", headers={"Origin": "https://evil.example"}).status_code == 200   # reads are not state changes


def test_invite_code_guessing_is_limited(make_client):
    c = make_client()
    for _ in range(5):
        r = c.post("/api/auth/register", json={"email": "g@example.edu", "password": "Passw0rd1", "full_name": "Guess",
                                               "role": "lecturer", "invite_code": "wrong"})
        assert r.status_code == 403
    r = c.post("/api/auth/register", json={"email": "g@example.edu", "password": "Passw0rd1", "full_name": "Guess",
                                           "role": "lecturer", "invite_code": INVITE})
    assert r.status_code == 429                         # blocked even with the right code until the window passes
    assert "invite" not in str(c.get("/api/auth/config").json()).lower().replace("lecturer_signup_enabled", "")


def test_production_settings_refuse_unsafe_values():
    base = dict(_env_file=None, environment="production", secret_key="s" * 40, cookie_secure=True,
                smtp_host="smtp.example.edu", smtp_from="noreply@example.edu")
    Settings(**base, database_url="postgresql+psycopg://u:p@db/adaptiveiq")
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(**base, database_url="sqlite:///x.db")
    with pytest.raises(ValueError, match="SMTP"):
        Settings(**{**base, "smtp_host": ""}, database_url="postgresql+psycopg://u:p@db/adaptiveiq")


def test_health_reports_active_database(make_client):
    h = make_client().get("/api/health").json()
    assert h["database_engine"] in ("sqlite", "postgresql") and "email" in h


def test_env_example_parses_to_clean_values():
    """Inline comments in a .env file would become part of the value (an invite code of '# empty ...')."""
    from pathlib import Path
    s = Settings(_env_file=str(Path(__file__).resolve().parents[1] / ".env.example"))
    assert not {k: v for k, v in s.model_dump().items() if isinstance(v, str) and "#" in v}
    assert s.lecturer_invite_code == "" and s.model_api_key == ""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, environment="production", secret_key="change-me-to-a-long-random-value-xx",
                 cookie_secure=True, database_url="postgresql+psycopg://u:p@db/x", require_email_verification=False)


def test_csrf_layers_each_hold_on_their_own(make_client, app):
    c = make_client()
    register(c, "student")
    body = {"full_name": "New Name"}
    # sandboxed iframes and data: pages send Origin "null": refused
    assert c.patch("/api/auth/me", json=body, headers={"Origin": "null"}).status_code == 403
    # right origin but no custom header (what a plain cross-site HTML form would send): refused
    with TestClient(app) as bare:
        bare.cookies.update(c.cookies)
        assert bare.patch("/api/auth/me", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 403
    # the session cookie is SameSite=Lax and HttpOnly, so other sites' pages neither send nor read it
    with client(app) as c2:
        r = c2.post("/api/auth/register", json={"email": "cookie.check@example.com", "password": "Passw0rd!",
                                                "full_name": "Cookie Check", "role": "student"})
        cookie = r.headers.get("set-cookie", "").lower()
    assert "samesite=lax" in cookie and "httponly" in cookie


def test_logout_signs_out_every_copy_of_the_session(make_client, app):
    """The JWT carries a token version; logout bumps the stored version, so every earlier token for that
    user is rejected on the server, not just the cookie in this browser."""
    a = make_client()
    register(a, "student", email="two.devices@example.com")
    b = make_client()
    assert b.post("/api/auth/login", json={"email": "two.devices@example.com", "password": "Passw0rd!"}).status_code == 200
    assert a.post("/api/auth/logout").status_code == 204
    assert b.get("/api/auth/me").status_code == 401


def test_production_never_logs_email_links(caplog):
    from app.services.mailer import Mailer
    s = Settings(environment="production", secret_key="x" * 40, cookie_secure=True,
                 database_url="postgresql+psycopg://u:p@localhost/db", require_email_verification=False)
    m = Mailer(s)
    with caplog.at_level("WARNING"):
        m.send("a@example.com", "Verify", "Open https://app/verify-email?token=SECRET")
    assert "SECRET" not in caplog.text and not m.outbox
