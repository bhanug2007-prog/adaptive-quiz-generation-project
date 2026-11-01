from fastapi.testclient import TestClient

from tests.conftest import INVITE, register


def test_register_login_logout_me(make_client):
    c = make_client()
    me = register(c, "student", email="Sanjay.Teja@Gmail.com")
    assert me["email"] == "sanjay.teja@gmail.com" and me["role"] == "student"
    assert c.get("/api/auth/me").json()["id"] == me["id"]
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401
    r = c.post("/api/auth/login", json={"email": "sanjay.teja@gmail.com", "password": "Passw0rd!"})
    assert r.status_code == 200
    assert c.get("/api/auth/me").status_code == 200


def test_session_cookie_is_httponly(make_client):
    c = make_client()
    r = c.post("/api/auth/register", json={"email": "a@gmail.com", "password": "Passw0rd!", "full_name": "A B"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_password_rules_and_duplicate_email(make_client):
    c = make_client()
    for bad in ("short1", "allletters", "12345678"):
        r = c.post("/api/auth/register", json={"email": "x@gmail.com", "password": bad, "full_name": "X Y"})
        assert r.status_code == 422, bad
    register(c, email="dup@gmail.com")
    r = c.post("/api/auth/register", json={"email": "DUP@gmail.com", "password": "Passw0rd!", "full_name": "X Y"})
    assert r.status_code == 409


def test_wrong_password_same_message_and_rate_limit(make_client):
    c = make_client()
    register(c, email="rl@gmail.com")
    c.post("/api/auth/logout")
    r1 = c.post("/api/auth/login", json={"email": "rl@gmail.com", "password": "wrong-pass1"})
    r2 = c.post("/api/auth/login", json={"email": "nobody@gmail.com", "password": "wrong-pass1"})
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()
    for _ in range(5):
        c.post("/api/auth/login", json={"email": "rl@gmail.com", "password": "wrong-pass1"})
    r = c.post("/api/auth/login", json={"email": "rl@gmail.com", "password": "Passw0rd!"})
    assert r.status_code == 429


def test_lecturer_needs_invite_code(make_client):
    c = make_client()
    body = {"email": "lec@gmail.com", "password": "Passw0rd!", "full_name": "Dr L", "role": "lecturer"}
    assert c.post("/api/auth/register", json=body).status_code == 403
    assert c.post("/api/auth/register", json={**body, "invite_code": "wrong"}).status_code == 403
    assert c.post("/api/auth/register", json={**body, "invite_code": INVITE}).status_code == 201


def test_email_domain_restriction(app, settings, make_client):
    settings.allowed_email_domains = "gmail.com"
    c = make_client()
    r = c.post("/api/auth/register", json={"email": "a@yahoo.com", "password": "Passw0rd!", "full_name": "A B"})
    assert r.status_code == 422 and "@gmail.com" in r.json()["detail"]
    assert c.post("/api/auth/register", json={"email": "a@gmail.com", "password": "Passw0rd!",
                                              "full_name": "A B"}).status_code == 201


def test_csrf_header_required(app):
    with TestClient(app) as c:                       # no X-Requested-With header
        r = c.post("/api/auth/register", json={"email": "a@gmail.com", "password": "Passw0rd!", "full_name": "A B"})
        assert r.status_code == 403


def test_change_password_signs_out_other_sessions(make_client):
    a = make_client()
    register(a, email="cp@gmail.com")
    b = make_client()
    assert b.post("/api/auth/login", json={"email": "cp@gmail.com", "password": "Passw0rd!"}).status_code == 200
    r = a.post("/api/auth/change-password", json={"current_password": "Passw0rd!", "new_password": "N3wPassword"})
    assert r.status_code == 204
    assert a.get("/api/auth/me").status_code == 200       # this device got a fresh cookie
    assert b.get("/api/auth/me").status_code == 401       # the other device is signed out


def test_role_separation(make_client):
    s = make_client()
    register(s, "student")
    assert s.get("/api/lecturer/courses").status_code == 403
    lec = make_client()
    register(lec, "lecturer")
    assert lec.get("/api/student/quizzes/assigned").status_code == 403
