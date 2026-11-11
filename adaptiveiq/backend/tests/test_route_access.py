"""Phase 7: every API route is checked for who may call it, so a new route without a role check is caught.
Path ids are 1; the role check must answer before the id, the body or the query is even looked at."""
import re

from tests.conftest import register

PUBLIC = {                                   # no sign-in needed
    ("GET", "/api/health"), ("POST", "/api/auth/register"), ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/verify-email"),                   # the emailed link carries its own token
    ("POST", "/api/auth/forgot-password"),                # public password reset request
    ("POST", "/api/auth/reset-password/verify"),          # public single-use token check
    ("POST", "/api/auth/reset-password"),                 # public single-use token consumption
    ("GET", "/api/auth/config"),                          # sign-up options shown on the register page
    ("GET", "/api/integrations/google/callback"),         # Google's redirect; checked by the signed state
}


def _routes(app):
    for path, ops in app.openapi()["paths"].items():           # every route the app serves
        if path.startswith("/api/"):
            for m in ops:
                yield m.upper(), path, re.sub(r"\{[^}]+\}", "1", path)


def _call(c, method, url):
    return c.request(method, url, json={}) if method in ("POST", "PUT", "PATCH") else c.request(method, url)


def test_signed_out_callers_get_401_everywhere_but_public_routes(app, make_client):
    c = make_client()
    wrong, checked = [], 0
    for m, path, url in _routes(app):
        if (m, path) in PUBLIC:
            continue
        checked += 1
        code = _call(c, m, url).status_code
        if code != 401:
            wrong.append(f"{m} {path} -> {code}")
    assert checked > 90
    assert not wrong, "\n".join(wrong)


def test_students_cannot_call_lecturer_routes_and_lecturers_cannot_call_student_routes(app, make_client):
    st, lec = make_client(), make_client()
    register(st, "student")
    register(lec, "lecturer")
    wrong, checked = [], 0
    for m, path, url in _routes(app):
        if path.startswith("/api/lecturer/") or path.startswith("/api/questions"):
            who, code = "student", _call(st, m, url).status_code
        elif path.startswith("/api/student/"):
            who, code = "lecturer", _call(lec, m, url).status_code
        else:
            continue
        checked += 1
        if code != 403:
            wrong.append(f"{who}: {m} {path} -> {code}")
    assert checked > 60
    assert not wrong, "\n".join(wrong)
