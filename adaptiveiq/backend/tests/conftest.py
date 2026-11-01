"""Test setup. Uses SQLite by default; set TEST_DATABASE_URL to run the same tests on PostgreSQL.
The model is the TEST-ONLY fake server in tests/fake_model_server.py, never the real Qwen model."""
import os
import socket
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import Base
from app.main import create_app
from tests import fake_model_server

INVITE = "lecturer-code-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def model_port():
    port = _free_port()
    srv = fake_model_server.start(port)
    yield port
    srv.shutdown()


@pytest.fixture
def settings(tmp_path, model_port):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    return Settings(_env_file=None, environment="test", database_url=url, model_base_url=f"http://127.0.0.1:{model_port}",
                    lecturer_invite_code=INVITE, secret_key="test-secret-" + "x" * 40, math_check=True,
                    require_email_verification=False)


@pytest.fixture
def app(settings):
    a = create_app(settings)
    Base.metadata.drop_all(a.state.db.engine)
    Base.metadata.create_all(a.state.db.engine)
    fake_model_server.STATE.update(mode="normal", n=0)
    yield a
    a.state.db.engine.dispose()


def _client(app) -> TestClient:
    c = TestClient(app)
    c.headers.update({"X-Requested-With": "AdaptiveIQ"})
    return c


@pytest.fixture
def make_client(app):
    clients = []

    def make():
        c = _client(app).__enter__()
        clients.append(c)
        return c
    yield make
    for c in clients:
        c.__exit__(None, None, None)


def register(c: TestClient, role="student", email=None, name=None, password="Passw0rd!"):
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@gmail.com"
    body = {"email": email, "password": password, "full_name": name or f"Test {role.title()}", "role": role}
    if role == "lecturer":
        body["invite_code"] = INVITE
    r = c.post("/api/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def wait_run(c: TestClient, run_id: int, timeout=30.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        r = c.get(f"/api/generation/{run_id}").json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(0.05)
    raise AssertionError("generation did not finish")


@pytest.fixture
def course_setup(make_client):
    """A lecturer with a course > subject > unit > topic, and an enrolled student."""
    lec = make_client()
    register(lec, "lecturer", name="Dr Lecturer")
    course = lec.post("/api/lecturer/courses", json={"code": "CS301", "title": "Operating Systems"}).json()
    subj = lec.post(f"/api/lecturer/courses/{course['id']}/subjects", json={"name": "Operating Systems",
                                                                            "quiz_weight_cap_pct": 20}).json()
    unit = lec.post(f"/api/lecturer/subjects/{subj['id']}/units", json={"name": "Unit 2: Scheduling"}).json()
    topic = lec.post(f"/api/lecturer/units/{unit['id']}/topics", json={"name": "CPU Scheduling"}).json()
    st = make_client()
    me = register(st, "student", name="Student One")
    r = st.post("/api/student/courses/join", json={"join_code": course["join_code"]})
    assert r.status_code == 200, r.text
    return {"lec": lec, "st": st, "student": me, "course": course, "subject": subj, "unit": unit, "topic": topic,
            "make_client": make_client}
